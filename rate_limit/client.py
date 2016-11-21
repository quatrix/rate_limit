from __future__ import absolute_import
from __future__ import division
from .utils import join_non_empty
from .limit import Limit
from tornado.gen import coroutine, Task, Return
from tornadoredis.exceptions import RedisError
from time import time


class RateLimit(object):
    """
    Distributed rate limiter over Redis
    """

    def __init__(self, redis_conn, namespace="", disable_locks=False,
                 lock_ttl=10, lock_polling_interval=0.1):
        """
        Args:
            redis_conn: a tornadoredis connection handler
            namespace: a namespace to be prefixed to all keys, to avoid
                collisions with other users using the same redis
            disable_locks: disabling locks will improve performance while
                making rate limiting less accurate (Default: False)
            lock_ttl: after how much seconds lock expires (Default: 10 sec)
            lock_polling_interval: how often to poll when waiting for a lock
                shorter poll interval means more trips to Redis.
        Returns:
            a RateLimit instance
        """

        self.redis_conn = redis_conn
        self.namespace = namespace

        self.disable_locks = disable_locks
        self.lock_ttl = lock_ttl
        self.lock_polling_interval = lock_polling_interval

        self._rules = {}
        self._keys_reached_rate_limit = {}

    @coroutine
    def is_rate_limit_reached(self, key, rule):
        """
        get the rule.allowed_requests-1 slot in the key list
        return if its timestamp greater than NOW() - rule.requests_span
        """

        response = yield Task(
            self.redis_conn.lindex,
            self.add_namespace(key),
            rule.allowed_requests - 1
        )

        if isinstance(response, RedisError):
            raise response

        if response is not None:
            if time() - int(response) < rule.requests_span:
                raise Return(True)

        raise Return(False)

    @coroutine
    def log_request(self, selectors_to_update):
        """
        for every selector in selectors_to_update dict,
        insert a new timestamp entry representing a request
        to the head a list under the selecotors key.

        then trim the list to the size of the largest amount
        of requests corresponding with that selector
        and set expiration to the amount of seconds of the
        longest requests span associated with the selector.

        e.g:
        say selector is user, and there are two rules:
        user:100/s and user:10/m,

        so longest request span for 'user' is 60 seconds
        and the requests log length will be 100
        """

        pipe = self.redis_conn.pipeline()

        for key, params in selectors_to_update.iteritems():
            key = self.add_namespace(key)

            pipe.lpush(key, int(time()))
            pipe.ltrim(key, 0, params["allowed_requests"] - 1)
            pipe.expire(key, params["requests_span"])

        response = yield Task(pipe.execute)

        if isinstance(response, RedisError):
            raise response

    def add_namespace(self, key):
        """
        prefix key with a namespace to avoid collisions with other users
        """

        return join_non_empty(":", self.namespace, key)

    @coroutine
    def get_lock(self, key):
        """
        try to get lock for key, 'block' until lock acquired or an error
        has occured.

        ignored if locking is disabled.
        """

        if self.disable_locks:
            raise Return(None)

        lock = self.redis_conn.lock(
            "lock:" + self.add_namespace(key),
            lock_ttl=self.lock_ttl,
            polling_interval=self.lock_polling_interval
        )

        result = yield Task(lock.acquire, blocking=True)

        if isinstance(result, RedisError):
            raise result

        raise Return(lock)

    @coroutine
    def release_lock(self, lock):
        """
        release the lock back to the wild,
        ignored if locking is disabled.
        """

        if self.disable_locks:
            raise Return(None)

        yield Task(lock.release)

    def limit(self, rules=None, key=None, selector=None, **selectors):
        """
        a factory for Limit instances, that can be used as decorators
        or as context managers. takes the following arguments:

        - rules, can be one of the following:
          1. simple string, like "apikey:10/s", or just '15/m'
          2. combination of And/Or object that form more complex rules
             for example And("user:5/s", "ip:10/2m").
          3. if rules not specified, you must specify the 'key' argument
             and make sure you previously created a limit with same key
             and rules. those rules will apply and the rate limit counters
             will be shared between all those with same key. so make sure
             you also have the proper selector(s) in places if needed.

        - key, if specified, uses the key as the rate_limit identifier
          when used as a decorator, decorated function name is used by default

        - selector, if specified, is an object that should have all the
          rate_limit selectors given in 'rules' argument, for example
          if the rule is 'apikey:10/s', selector should have an 'apikey'
          member/method. for decorators, when decorating a bound method,
          the 'self' of the instance is used as a selector.

        - **selectors, you could specify individual selectors, and they
          take precedence over the 'selector' argument.
        """

        if rules is None:
            rules = self._rules[key]
        elif key is not None:
            if key in self._rules:
                raise RuntimeError("Rules already defined for Key")

            self._rules[key] = rules

        return Limit(self, rules, key, selector, **selectors)
