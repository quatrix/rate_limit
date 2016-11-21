from rate_limit import RateLimit, RateLimitExceeded, Or
import tornadoredis
import tornado.ioloop
import tornado.web
import tornado.gen


redis_conn = tornadoredis.Client()
redis_conn.connect()

rl = RateLimit(redis_conn, namespace="example.com")


class MainHandler(tornado.web.RequestHandler):
    def user(self):
        """
        should return the current user or None
        """
        return "vova"

    @rl.limit(Or('100/s', 'user:50/h'))
    def get(self):
        """
        this method is limited to 100 calls a seconds
        or 50 times per hour per user
        """

        self.finish("Heya, world")

    def write_error(self, status_code, **kwargs):
        if issubclass(kwargs['exc_info'][0], RateLimitExceeded):
            """
            what to do when on rate limit exceeded
            """

            self.finish("rate_limit_exceeded")


application = tornado.web.Application([
    (r"/", MainHandler),
])

if __name__ == "__main__":
    application.listen(8888)
    tornado.ioloop.IOLoop.instance().start()
