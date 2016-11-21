
from __future__ import division
from rate_limit.rule import parse_rate_string, parse_expression
import unittest


class ParseRateTestCase(unittest.TestCase):
    def assertParseTime(self, rate_string, expected_reqs, expected_reset_secs):
        requests, reset_seconds = parse_rate_string(rate_string)

        self.assertEqual(requests, expected_reqs)
        self.assertEqual(reset_seconds, expected_reset_secs)

    def assertBadRateRaises(self, bad_rate):
        with self.assertRaises(Exception):
            parse_rate_string(bad_rate)

    def test_seconds(self):
        self.assertParseTime("5/s", 5, 1)

    def test_seconds_multiple(self):
        self.assertParseTime("5/7s", 5, 7)

    def test_minutes(self):
        self.assertParseTime("5/m", 5, 60)

    def test_multiple_minutes(self):
        self.assertParseTime("5/5m", 5, 5 * 60)

    def test_hours(self):
        self.assertParseTime("150/h", 150, 60 * 60)

    def test_multiple_hours(self):
        self.assertParseTime("3/5h", 3, 5 * 60 * 60)

    def test_bad_rate(self):
        self.assertBadRateRaises(None)
        self.assertBadRateRaises("")
        self.assertBadRateRaises("1/")
        self.assertBadRateRaises("/m")
        self.assertBadRateRaises("/")
        self.assertBadRateRaises("vova/baba")
        self.assertBadRateRaises("1/1")
        self.assertBadRateRaises("vova")


class ExpressionParserTestCase(unittest.TestCase):
    def assertParseExpression(self, expression, selector=None, rate=None):
        res = parse_expression(expression)

        self.assertEqual(res[0], selector)
        self.assertEqual(res[1], rate)

    def assertBadExpressionRaises(self, bad_rate):
        with self.assertRaises(Exception):
            parse_expression(bad_rate)

    def test_expression_with_rate_only(self):
        """
        expression without a selector, and without a bucket_interval
        should return None as a selector, the rate and None as bucket_interval

        example: 10/s
        """
        self.assertParseExpression("10/3m", rate="10/3m")

    def test_expression_with_selector_and_rate(self):
        """
        expression with selector and rate but no bucket_interval
        should return first two, and None as bucket_interval

        example: username:10/s
        """
        self.assertParseExpression("vova:10/3m", selector="vova", rate="10/3m")

    def test_invalid_expressions(self):
        """
        everything else should raise an exception
        """

        self.assertBadExpressionRaises(None)
        self.assertBadExpressionRaises("")
        self.assertBadExpressionRaises("vova")
        self.assertBadExpressionRaises(":vova:")
        self.assertBadExpressionRaises(":123:")
        self.assertBadExpressionRaises("pita::1")
        self.assertBadExpressionRaises("::1")
        self.assertBadExpressionRaises("vova:pita:1.0")
        self.assertBadExpressionRaises("hey:vova:pita:1.0")
        self.assertBadExpressionRaises("vova:15:1.0")
        self.assertBadExpressionRaises("vova:15//1:1.0")
        self.assertBadExpressionRaises("vova:15/s/:1.0")
        self.assertBadExpressionRaises("vova:15/s:-1.0")
        self.assertBadExpressionRaises("vova:15/s:2.0")
