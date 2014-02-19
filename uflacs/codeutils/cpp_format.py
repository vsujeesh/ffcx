
from uflacs.utils.log import uflacs_assert, error

import ufl


class CppFormatterErrorRules(object):
    "Error rules catching groups of missing types by their superclasses."

    # Generic fallback error messages for missing rules:
    def expr(self, o):
        error("Missing C++ formatting rule for expr type %s." % o._uflclass)

    def terminal(self, o):
        error("Missing C++ formatting rule for terminal type %s." % o._uflclass)

    # These should be implemented in target specific subclass:
    def geometric_quantity(self, o, component=(), derivatives=(), restriction=None):
        error("Missing C++ formatting rule for geometric quantity type %s." % o._uflclass)

    def form_argument(self, o, component=(), derivatives=(), restriction=None):
        error("Missing C++ formatting rule for form argument type %s." % o._uflclass)

    # Unexcepted type checks:
    def variable(self, o, *ops):
        error("Expecting variables to be removed before formatting C++ code.")
        return ops[0] # or just do this if necessary

    def invalid_request(self, o, *ops):
        error("Invalid request for C++ formatting of a %s." % o._uflclass)
    wrapper_type = invalid_request
    index_sum = invalid_request
    indexed = invalid_request
    derivative = invalid_request
    restricted = invalid_request


class CppLiteralFormatterRules(object):
    "Formatting rules for literal constants."

    def constant_value(self, o, component=(), derivatives=(), restriction=None):
        error("Missing C++ rule for constant value type %s." % o._uflclass)

    def zero(self, o, component=(), derivatives=(), restriction=None):
        return "0"

    def int_value(self, o, component=(), derivatives=(), restriction=None):
        if derivatives:
            return self.zero(None)
        else:
            return "%d" % int(o)

    def float_value(self, o, component=(), derivatives=(), restriction=None):
        # Using configurable precision parameter from ufl
        if derivatives:
            return self.zero(None)
        else:
            return ufl.constantvalue.format_float(float(o))

    def identity(self, o, component=(), derivatives=(), restriction=None):
        if derivatives:
            return self.zero(None)
        else:
            return "1" if component[0] == component[1] else "0"


class CppArithmeticFormatterRules(object):
    "Formatting rules for arithmetic operations."

    def sum(self, o, *ops):
        return " + ".join(ops)

    def product(self, o, *ops):
        return " * ".join(ops)

    def division(self, o, a, b):
        return "%s / %s" % (a, b)

class CppCmathFormatterRules(object):
    "Formatting rules for <cmath> functions."

    def add_include(self, include):
        "Callback to be implemented by subclass for recording includes needed."
        pass

    def add_using(self, using):
        "Callback to be implemented by subclass for recording using symbols needed."
        pass

    def _cmath(self, name, op):
        self.add_using("std::%s" % name)
        return "%s(%s)" % (name, op)

    def math_function(self, o, op):
        return self._cmath(o._name, op)

    def power(self, o, a, b):
        self.add_using("std::pow")
        return "pow(%s, %s)" % (a, b)

    def sqrt(self, o, op):
        return self._cmath("sqrt", op)

    def ln(self, o, op):
        return self._cmath("log", op)

    def exp(self, o, op):
        return self._cmath("exp", op)

    def abs(self, o, op):
        return "fabs(%s)" % (op,)

    def cos(self, o, op):
        return self._cmath("cos", op)

    def sin(self, o, op):
        return self._cmath("sin", op)

    def tan(self, o, op):
        return self._cmath("tan", op)

    def cosh(self, o, op):
        return self._cmath("cosh", op)

    def sinh(self, o, op):
        return self._cmath("sinh", op)

    def tanh(self, o, op):
        return self._cmath("tanh", op)

    def acos(self, o, op):
        return self._cmath("acos", op)

    def asin(self, o, op):
        return self._cmath("asin", op)

    def atan(self, o, op):
        return self._cmath("atan", op)

    def erf(self, o, op):
        return "erf(%s)" % (op,)

    def _bessel(self, o, n, v, name):
        self.add_include("#include <boost/math/special_functions.hpp>")
        self.add_using("boost::math::%s" % name)
        return "%s(%s, %s)" % (name, n, v)

    def bessel_i(self, o, n, v):
        return self._bessel(o, n, v, "cyl_bessel_i")

    def bessel_j(self, o, n, v):
        return self._bessel(o, n, v, "cyl_bessel_j")

    def bessel_k(self, o, n, v):
        return self._bessel(o, n, v, "cyl_bessel_k")

    def bessel_y(self, o, n, v):
        return self._bessel(o, n, v, "cyl_neumann")


class CppConditionalFormatterRules(object):
    "Formatting rules for conditional expressions."

    def conditional(self, o, c, t, f):
        return "%s ? %s: %s" % (c, t, f)

    def eq(self, o, a, b):
        return " == ".join((a, b))

    def ne(self, o, a, b):
        return " != ".join((a, b))

    def le(self, o, a, b):
        return " <= ".join((a, b))

    def ge(self, o, a, b):
        return " >= ".join((a, b))

    def lt(self, o, a, b):
        return " < ".join((a, b))

    def gt(self, o, a, b):
        return " > ".join((a, b))

    def and_condition(self, o, a, b):
        return " && ".join((a, b))

    def or_condition(self, o, a, b):
        return " || ".join((a, b))

    def not_condition(self, o, a):
        return "!%s" % a


class CppFormatterRulesCollection(CppFormatterErrorRules,
                                  CppLiteralFormatterRules,
                                  CppArithmeticFormatterRules,
                                  CppCmathFormatterRules,
                                  CppConditionalFormatterRules):
    """C++ formatting rules collection.

    This is the base class for target specific cpp formatter class.
    See DefaultCppFormatter below for example of how to specialise
    for a particular target."""
    def __init__(self):
        pass


from ufl.algorithms import MultiFunction
class ExampleCppFormatter(MultiFunction, CppFormatterRulesCollection):
    """Example C++ formatter class."""
    def __init__(self):
        MultiFunction.__init__(self)
        CppFormatterRulesCollection.__init__(self)
    # TODO: Add some default rules for geometry and form arguments?
