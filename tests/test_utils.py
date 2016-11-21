from rate_limit.utils import join_non_empty
import unittest


class JoinNonEmptyTestCase(unittest.TestCase):
    def test_basic(self):
        """
        should join all non empty string and non Nones with delimiter
        """

        j = join_non_empty

        self.assertEqual(j(":", "hey"), "hey")
        self.assertEqual(j(":", "hey", None), "hey")
        self.assertEqual(j(":", "", "hey", None), "hey")
        self.assertEqual(j(":", "", "hey", None, "ho"), "hey:ho")
        self.assertEqual(j(":", "hey", "ho", "lets"), "hey:ho:lets")
        self.assertEqual(j(":", 0, 1, 2), "0:1:2")
