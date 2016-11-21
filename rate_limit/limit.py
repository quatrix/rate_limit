from tornado.concurrent import TracebackFuture
from tornado.gen import coroutine, Return
from functools import wraps
from contextlib import contextmanager
from rate_limit.utils import join_non_empty
from rate_limit.rule import Rule
from six import string_types


class RateLimitExceeded(RuntimeError):
    pass


def is_empty(expr):
    return expr is None or expr == ""


def set_max(res, identifier, rule, key):
    res[identifier][key] = max(getattr(rule, key), res[identifier][key])


def handle_callables(member):
    """
    if a member is callable, calls it, other wise just returns it
    """

    if hasattr(member, '__call__'):
        return member()
    return member


class Limit(object):
    """
    Limit class used to create decorators and context managers,
    it's created by RateLimit().limit factory function and shouldn't
    be instantiated manually.
    """

    def __init__(self, client, rules, key=None, selector=None, **selectors):
        self.client = client
        self.rules = rules

        self.key = key
        self.selector = selector
        self.selectors = selectors

        self.func_name = None
        self.func_args = None

    @coroutine
    def request_limit_reached(self):
        """
        predicate returning True or False based on the following algorithm:

        1. get_lock for key.
        2. run rule logic, for each rule, go to the key+selector list
           and get the slot corresponding with rule.allowed_requests-1
           if its timestamp is greater than NOW() - rule.requests_span means
           limit has reached, set result to False and skip next step.
        3. if limit didn't exceed on any rule, log a new request into
           the requests list for relevant selector
        4. relase lock and return result.
        """

        lock = yield self.client.get_lock(self.get_key())

        try:
            if ((yield self.rate_limit_reached())):
                raise Return(True)

            yield self.log_request()
        finally:
            yield self.client.release_lock(lock)

        raise Return(False)

    @coroutine
    def rate_limit_reached(self):
        """
        traverses the rule tree and stops on first rule for which
        rate limit has exceeded.

        skips rules that indicate selectors but their selectors return None.
        """

        if isinstance(self.rules, string_types):
            res = yield self.is_rule_rate_limit_reached(self.rules)
        else:
            res = yield self.rules.run(self.is_rule_rate_limit_reached)

        raise Return(res)

    @coroutine
    def is_rule_rate_limit_reached(self, rule):
        """
        a predicate that takes a rule and returns if rate
        limit reached for this rule.
        """

        rule = Rule(rule)

        selector_value = self.get_selector(rule.selector)

        if rule.selector is not None and is_empty(selector_value):
            raise Return(False)

        res = yield self.client.is_rate_limit_reached(
            self.create_identifier(rule.selector, selector_value),
            rule,
        )

        raise Return(res)

    def get_rules(self):
        """
        returns a list of Rule objects, single instance of each rule,
        e.g Or('5/m', And('1/s', '5/m') will returns Rule objects for
        5/m and 1/s.
        """

        if isinstance(self.rules, string_types):
            return [Rule(self.rules)]

        return [Rule(rule) for rule in self.rules.get_all()]

    def get_relevant_selectors(self):
        """
        returns a dict with are selectors:selector value
        and the values are the maximum allowed request and span
        according to the rules governing that selector

        i.e given this empty selector, 1/m and 10/s, the maximum
        allowed requests is 10, and the maximum span is 60 seconds.
        """

        res = {}

        for rule in self.get_rules():
            selector_value = self.get_selector(rule.selector)

            if rule.selector is not None and is_empty(selector_value):
                continue

            identifier = self.create_identifier(rule.selector, selector_value)

            if identifier in res:
                set_max(res, identifier, rule, "requests_span")
                set_max(res, identifier, rule, "allowed_requests")
            else:
                res[identifier] = {
                    "requests_span": rule.requests_span,
                    "allowed_requests": rule.allowed_requests
                }

        return res

    @coroutine
    def log_request(self):
        """
        log request to relevant selectors lists
        """

        yield self.client.log_request(self.get_relevant_selectors())

    def get_key(self):
        """
        returns key argument if were passed, if not, returns func_name
        if it is set.
        """
        return self.key or self.func_name or ""

    def _find_selector(self, selector):
        """
        looking for the selector, in order specified at get_selector,
        this extra function is needed so not to write handle_callables
        on everyline
        """

        if selector in self.selectors:
            return self.selectors[selector]

        if self.selector is not None:
            if hasattr(self.selector, selector):
                return getattr(self.selector, selector)

            if selector in self.selector:
                return self.selector[selector]

        # check if func_args are set, and look in the first argument
        # if it has the selector we're looking for.
        if self.func_args and hasattr(self.func_args[0], selector):
            return getattr(self.func_args[0], selector)

        raise RuntimeError("Selector was specified but not found")

    def get_selector(self, selector):
        """
        Figures out what selector to return.

        1. if selector is None, returns None
        2. if selector found in self.selectors, it takes priority,
        3. if not found, look in selector object, if was passed
        4. if not found/no selector object, see if we're decorating a bound
            method with a self, and look into that self (heh) for the selector.
        5. if selector not found, raise an exception

        if selector found, and it's a callable, call it, otherwise use its
        string representation.

        """
        if selector is None:
            return None

        return handle_callables(self._find_selector(selector))

    def create_identifier(self, selector, selector_value):
        """
        a limit identifier consists of the following:

        1. key (function name, or passed key kwarg)
        2. selector name, such as "user", "apikey", whatever
        3. selector content, "vova", "apikey123"

        empty and None values are ignored, others joined by : sign.

        * NOTE: it is assumed that if selector isn't None, selector_value
          isn't empty/None too. this function shouldn't even be entered
          if that's not the case.
        """

        key = self.get_key()
        return join_non_empty(":", key, selector, selector_value)

    @coroutine
    def cm(self):
        """
        returns a context manager, that will raise an exception when
        rate limit is reached and not run the body code.

        since it's a coroutine, you use it like so:

        with (yield Limit(...).cm()) as ctx:
            do_stuff()
        """

        if (yield self.request_limit_reached()):
            raise RateLimitExceeded

        @contextmanager
        def func():
            yield self

        raise Return(func())

    def __call__(self, func):
        """
        decorates func with a context manager that guards the rate limit
        func can either be a regular function, or a function that returns
        a Future, the Future will be ran for you.

        also, remembers the decorated function name, to be used as the
        rate limit identifier

        this also wraps func in a coroutine, so decorated functions
        should be ran with yield, e.g:

        res = yield decorated_function()
        """
        self.func_name = func.__name__

        @wraps(func)
        @coroutine
        def wrapper(*args, **kwargs):
            """
            remembers function args, to inspect for 'self', to be used as
            a selector object.
            """
            self.func_args = args

            with (yield self.cm()):
                res = func(*args, **kwargs)

                if isinstance(res, TracebackFuture):
                    res = yield res

                raise Return(res)

        return wrapper
