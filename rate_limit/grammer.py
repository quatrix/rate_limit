from tornado.gen import coroutine, Return


class Operator(object):
    """
    Base class for Logical Operators
    """

    def __init__(self, *args):
        self.operators = args

    @coroutine
    def run(self, callback):
        """
        runs callback on each operator in the operators list according
        to the logical relations defined in the subclass

        callback should be a predicate function.
        """

        res = self.initial_res

        for operator in self.operators:
            if isinstance(operator, Operator):
                res = yield self.logical_operator(res, operator.run, callback)
            else:
                res = yield self.logical_operator(res, callback, operator)

        raise Return(res)

    def get_all(self):
        res = set()

        for operator in self.operators:
            if isinstance(operator, Operator):
                res = res.union(operator.get_all())
            else:
                res.add(operator)

        return res

    def logical_operator(self, last_res, callback, node):
        """
        Each subclass must implement it's logical operator,
        first argument is the previous result, then function refrence
        and finally content of current node.
        """

        raise NotImplementedError


class And(Operator):
    """
    Logical And, stops running on first non True value
    """
    initial_res = True

    @coroutine
    def logical_operator(self, last_res, callback, node):
        raise Return(last_res and (yield callback(node)))


class Or(Operator):
    """
    Logical Or, stops running on first True value
    """
    initial_res = False

    @coroutine
    def logical_operator(self, last_res, callback, node):
        raise Return(last_res or (yield callback(node)))
