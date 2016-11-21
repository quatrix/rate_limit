from tornado.web import Application, RequestHandler
from tornado.gen import coroutine, Return
from tornado.testing import AsyncHTTPTestCase, gen_test
from rate_limit import RateLimit, RateLimitExceeded
from helpers import gen_random_string
import tornadoredis
import pytest
import time


slow = pytest.mark.slow


class TornadoWebIntegrationTestCase(AsyncHTTPTestCase):
    def get_handler_class(self):
        redis_conn = tornadoredis.Client()
        redis_conn.connect()
        rate_limit = RateLimit(redis_conn, namespace=gen_random_string())

        class Handler(RequestHandler):
            def user(self):
                return self.request.body

            @rate_limit.limit('5/2s')
            def get(self):
                self.finish("decorator")

            @coroutine
            def post(self):
                with (yield rate_limit.limit('user:5/2s', user=self.user).cm()):
                    self.finish("contextmanager")

            def write_error(self, status_code, **kwargs):
                self.set_status(200)

                if 'exc_info' in kwargs:
                    if issubclass(kwargs['exc_info'][0], RateLimitExceeded):
                        self.finish("rate_limit_exceeded")
                    else:
                        self.finish("this shouldn't happen")

        return Handler

    def get_app(self):
        return Application([('/', self.get_handler_class())])

    @slow
    @gen_test
    def test_rate_limit_decorator(self):
        """
        rate limit for GET set to 5/2s, after 5 requests we should
        get a rate limit exceeded error
        """

        # first 4 requests should succeed
        for _ in range(5):
            res = yield self.http_client.fetch(self.get_url('/'))
            self.assertEqual(res.body, "decorator")

        res = yield self.http_client.fetch(self.get_url('/'))
        self.assertEqual(res.body, "rate_limit_exceeded")

        # since the rate limit is 5 requests for 2 seconds,
        # waiting 2 seconds should clear the limit

        time.sleep(2)

        res = yield self.http_client.fetch(self.get_url('/'))
        self.assertEqual(res.body, "decorator")

    @slow
    @gen_test
    def test_rate_limit_contextmanager_with_selector(self):
        """
        rate limit for POST set to 5/2s per user
        so first user can do 4 requests, then he's rate limited
        second user does another 4, then (on the 5th) rate limit hits.
        then we wait 2 seconds, and both users should be able to do another
        4 requests each.

        the test is setup so that the body of the post is actually the
        username.
        """

        @coroutine
        def post(user):
            res = yield self.http_client.fetch(
                self.get_url('/'),
                method="POST",
                body=user
            )

            raise Return(res.body)

        # first 4 request, fine and danddy
        for _ in range(5):
            self.assertEqual((yield post("vova")), "contextmanager")
            self.assertEqual((yield post("pita")), "contextmanager")

        # then, rate limit hits
        self.assertEqual((yield post("vova")), "rate_limit_exceeded")
        self.assertEqual((yield post("pita")), "rate_limit_exceeded")

        # but user misha, who just came, should be fine
        self.assertEqual((yield post("misha")), "contextmanager")

        # now we wait...
        time.sleep(2)

        # and BAM, rate limit was expired
        for _ in range(5):
            self.assertEqual((yield post("vova")), "contextmanager")
            self.assertEqual((yield post("pita")), "contextmanager")
