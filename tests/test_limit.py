from tornado.gen import coroutine
from rate_limit.limit import Limit, RateLimitExceeded
from rate_limit.grammer import Or, And
from helpers import mocked_future_response
from tornado.testing import AsyncTestCase, gen_test


def mocked_limit(rate_limit_reached=False):
    """
    returns a monkey patched Limit instance, with the rate_limit_reached
    method returning value in 'rate_limit_reached' argument
    """
    limit = Limit(None, None)
    limit.request_limit_reached = mocked_future_response(rate_limit_reached)

    return limit


class LimitTestCase(AsyncTestCase):
    def test_get_relevant_selectors_merges_duplicates(self):
        """
        different rates on the same selector (or empty selector when
        non specified) should be merged by choosing the longest
        request span and highest allowed requests from all rules
        for the same selector
        """

        limit = Limit(None, And('5/m', Or('10/5s', '1/m')), key="vova")
        selectors = limit.get_relevant_selectors()

        self.assertEqual(selectors['vova']["allowed_requests"], 10)
        self.assertEqual(selectors['vova']["requests_span"], 60)
        self.assertEqual(len(selectors), 1)

    def test_get_relevant_selectors_ignored_empty_selectors(self):
        """
        empty selectors shouldn't be updated with new requests
        """

        rules = Or('user:10/15s', 'apikey:1/m')
        limit = Limit(None, rules, user="vova", apikey=None, key="upload")

        selectors = limit.get_relevant_selectors()

        self.assertEqual(selectors['upload:user:vova']["allowed_requests"], 10)
        self.assertEqual(selectors['upload:user:vova']["requests_span"], 15)
        self.assertEqual(len(selectors), 1)

    def test_get_relevant_selectors_multiple_selectors(self):
        """
        a more typical complete example with multiple selectors
        """

        rules = Or('user:10/15s', 'apikey:1/m')
        limit = Limit(None, rules, user="vova", apikey="my_api", key="k")

        selectors = limit.get_relevant_selectors()

        self.assertEqual(selectors['k:user:vova']["allowed_requests"], 10)
        self.assertEqual(selectors['k:user:vova']["requests_span"], 15)

        self.assertEqual(selectors['k:apikey:my_api']["allowed_requests"], 1)
        self.assertEqual(selectors['k:apikey:my_api']["requests_span"], 60)

        self.assertEqual(len(selectors), 2)

    @gen_test
    def test_basic_wrapping(self):
        """
        decorating a non coroutine function, should yield its result
        """
        returns = "helloworld"
        limit = mocked_limit()

        @limit
        def func():
            return returns

        self.assertEqual((yield func()), returns)
        self.assertEqual(limit.request_limit_reached.call_count, 1)

    @gen_test
    def test_wrapping_a_coroutine(self):
        """
        decorating a coroutine function, should identify it's a
        coroutine and returns the result of the future instead of
        the Future object itself.
        """
        returns = "goodbye world"
        limit = mocked_limit()

        @limit
        @coroutine
        def func():
            return returns

        self.assertEqual((yield func()), returns)
        self.assertEqual(limit.request_limit_reached.call_count, 1)

    @gen_test
    def test_raising_exception_when_rate_limit_reached(self):
        """
        when rate limited is reached decorator should raise an
        exception and not run the decorated function
        """

        limit = mocked_limit(rate_limit_reached=True)

        @limit
        @coroutine
        def func():
            self.fail("decorated function ran when shouldn't have")

        with self.assertRaises(RateLimitExceeded):
            yield func()

        self.assertEqual(limit.request_limit_reached.call_count, 1)

    @gen_test
    def test_contextmanager_basic(self):
        """
        test context manager expected to change ret from False to True
        """
        ret = False
        limit = mocked_limit()

        with (yield limit.cm()):
            ret = True

        self.assertTrue(ret)
        self.assertEqual(limit.request_limit_reached.call_count, 1)

    @gen_test
    def test_contextmanager_returning_itself(self):
        """
        test context manager expected to change ret from False to True
        """
        ret = False
        limit = mocked_limit()

        with (yield limit.cm()) as ctx:
            ret = True
            self.assertEqual(ctx, limit)

        self.assertTrue(ret)

    @gen_test
    def test_contextmanager_coroutine(self):
        """
        test context manager able to run coroutine code
        """
        ret = False

        with (yield mocked_limit().cm()):
            ret = yield mocked_future_response(True)()

        self.assertTrue(ret)

    @gen_test
    def test_contextmanager_raises(self):
        """
        test context manager doesn't run it's body when rate limit reached
        """
        limit = mocked_limit(rate_limit_reached=True)

        with self.assertRaises(RateLimitExceeded):
            with (yield limit.cm()):
                self.fail("decorated function ran when shouldn't have")

    def test_get_key_when_key_defined(self):
        """
        key should be the key argument if passed, if not then the name
        of the decorated function in case of decorator, or nothing.
        """
        key = "vova"

        limit = Limit(None, None, key=key)

        self.assertEqual(limit.get_key(), key)

        @limit
        def do_stuff():
            pass

        # after decorating, get_key should still return key and not func name
        self.assertEqual(limit.get_key(), key)

    def test_get_key_when_key_not_defined_but_decorated(self):
        """
        if no key was passed, and it's a decorator, key should be func name
        """
        limit = Limit(None, None)

        @limit
        def do_stuff():
            pass

        self.assertEqual(limit.get_key(), "do_stuff")

    def test_get_key_when_key_not_defined(self):
        """
        if no key was passed, and not a decorator, key should be empty string
        """
        self.assertEqual(Limit(None, None).get_key(), "")

    def test_get_selector_none_return_empty_string(self):
        self.assertEqual(Limit(None, None).get_selector(None), None)

    def test_get_selector_given_selectors(self):
        limit = Limit(None, None, api_key="pita")
        self.assertEqual(limit.get_selector("api_key"), "pita")

        limit = Limit(None, None, username=lambda: "misha")
        self.assertEqual(limit.get_selector("username"), "misha")

    def test_get_selector_given_selector_dict(self):
        selector = {
            "foo": "vova",
            "bar": lambda: "liron"
        }

        limit = Limit(None, None, selector=selector)

        self.assertEqual(limit.get_selector("foo"), "vova")
        self.assertEqual(limit.get_selector("bar"), "liron")

    def test_get_selector_given_selector_object(self):
        class Selector(object):
            def __init__(self):
                self.foo = "vova"

            def bar(self):
                return "liron"

        limit = Limit(None, None, selector=Selector())

        self.assertEqual(limit.get_selector("foo"), "vova")
        self.assertEqual(limit.get_selector("bar"), "liron")

    @gen_test
    def test_get_selector_decorating_bound_method(self):
        limit = mocked_limit()

        class API(object):
            def __init__(self):
                self.apikey = "kitties"

            def username(self):
                return "vova"

            @limit
            def get_username(self):
                return limit.get_selector("username")

            @limit
            def get_apikey(self):
                return limit.get_selector("apikey")

        self.assertEqual((yield API().get_username()), "vova")
        self.assertEqual((yield API().get_apikey()), "kitties")

    def test_get_selector_returns_none_when_underlying_returns_none(self):
        """
        the kwarg selector should take precedence over the selector
        and return None.
        """

        selector = {"api_key": "vova"}
        limit = Limit(None, None, selector=selector, api_key=None)
        self.assertEqual(limit.get_selector("api_key"), None)

    def test_get_selector_returns_none_when_not_found(self):
        """
        if a user specified a selector, and one doesn't exists
        should raise an exception
        """
        with self.assertRaises(RuntimeError):
            Limit(None, None).get_selector("no_selector")

    def test_create_identifier_basic(self):
        limit = Limit(None, None, key="pita")
        self.assertEqual(
            limit.create_identifier(None, None),
            "pita"
        )

    def test_create_identifier_with_selector(self):
        limit = Limit(None, None, key="some_key")
        self.assertEqual(
            limit.create_identifier("user", "vova"),
            "some_key:user:vova"
        )
