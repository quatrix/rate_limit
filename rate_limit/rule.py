from __future__ import division
import re

_MODIFIERS = {
    's': 1,
    'm': 60,
    'h': 60 * 60
}

# Some people, when confronted with a problem, think "I know, I'll use
# regular expressions." Now they have two problems.
_EXPRESSION_RE = re.compile(r"^(?:(\w+):)?(\d+/\w+){1}$")


def to_seconds(fmt_time):
    """
    takes formated time like s, 10s, m, 5m
    and returns it in seconds
    """
    modifier = _MODIFIERS[fmt_time[-1]]
    amount = int(fmt_time[:-1] or 1)

    return modifier * amount


def parse_rate_string(rate):
    """
    takes a rate string, like 10/15m or 5/s
    and returns:
    1. maximum number of requests
    2. seconds from now when requests counter resets

    valid time modifiers:
    s - seconds
    m - minutes
    h - hours
    """

    requests, time_to_reset = rate.split("/")

    return int(requests), to_seconds(time_to_reset)


def parse_expression(expression):
    """
    takes expressions like 'vova:10/s' and returns selector and rate.
    raises an exception on malformed rules.
    """

    try:
        return _EXPRESSION_RE.match(expression).groups()
    except Exception:
        raise SyntaxError("Malformed rule")


class Rule(object):
    def __init__(self, rule):
        selector, rate = parse_expression(rule)
        allowed_requests, requests_span = parse_rate_string(rate)

        self.selector = selector
        self.rate = rate
        self.allowed_requests = allowed_requests
        self.requests_span = requests_span
