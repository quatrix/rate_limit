from tornado.testing import AsyncTestCase, gen_test
from tornado.gen import coroutine, Return
from rate_limit.grammer import And, Or


class GrammerTestCase(AsyncTestCase):
    @coroutine
    def assertLogic(self, stmt, expected):
        @coroutine
        def evaluate(content):
            if content is Exception:
                raise Exception

            raise Return(content)

        self.assertEqual((yield stmt.run(evaluate)), expected)

    @gen_test
    def test_and_all_true_returns_true(self):
        yield self.assertLogic(And(True), True)
        yield self.assertLogic(And(True, True), True)

    @gen_test
    def test_and_not_all_true_returns_false(self):
        yield self.assertLogic(And(True, False), False)
        yield self.assertLogic(And(False, True, False), False)
        yield self.assertLogic(And(True, False, True), False)

    @gen_test
    def test_or_all_false_returns_false(self):
        yield self.assertLogic(Or(False), False)
        yield self.assertLogic(Or(False, False), False)

    @gen_test
    def test_or_some_true_returns_true(self):
        yield self.assertLogic(Or(True), True)
        yield self.assertLogic(Or(False, False, True), True)
        yield self.assertLogic(Or(True, False, True), True)
        yield self.assertLogic(Or(True, False, False), True)

    @gen_test
    def test_combinations(self):
        yield self.assertLogic(Or(And(True, True), Or(True, False)), True)
        yield self.assertLogic(Or(And(False, True), Or(False, False)), False)
        yield self.assertLogic(And(And(False, True), Or(False, False)), False)
        yield self.assertLogic(And(And(True, True), Or(True, False)), True)

        yield self.assertLogic(Or(Or(Or(Or(Or(False, False, False), False),
                                        False), False), True), True)

        yield self.assertLogic(Or(Or(Or(Or(Or(False, False, True), False),
                                        False), False), False), True)

    @gen_test
    def test_we_need_to_go_deeper(self):
        yield self.assertLogic(
            And(
                And(True, Or(True, False), True),
                Or(True, False)
            ),
            True)

    @gen_test
    def test_things_aint_called_when_not_needed(self):
        yield self.assertLogic(And(True, False, Exception), False)
        yield self.assertLogic(Or(True, Exception), True)

    def test_get_all(self):
        """
        get_all should return a set of the content of all operators
        """

        logic = And(And("hey", Or("ho", "lets"), "go"), Or("lets", "go"))
        self.assertEqual(logic.get_all(), set(("hey", "ho", "lets", "go")))
