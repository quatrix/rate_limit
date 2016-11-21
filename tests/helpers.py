from tornado.concurrent import Future
from mock import Mock
import random
import string


def mocked_future_response(*args):
    """
    returns a Future wrapped with a mock object.
    the Future result is set to args (or just first arg is there's only one)
    """
    res = Future()

    if len(args) == 1:
        res.set_result(args[0])
    else:
        res.set_result(args)

    return Mock(side_effect=lambda *_: res)


def gen_random_string():
    """
    returns a random string
    """
    return ''.join(random.choice(string.ascii_uppercase) for _ in range(5))
