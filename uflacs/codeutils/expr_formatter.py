
from uflacs.utils.log import uflacs_assert, info, warning, error

import ufl
from ufl.algorithms.transformations import Transformer

from uflacs.codeutils.precedence import build_precedence_map


class ExprFormatter(Transformer):
    """Language independent formatting class containing rules for
    handling indexing operators such that value and derivative
    indices are propagated to terminal handlers to be implemented
    for a particular language and target."""

    def __init__(self, language_formatter, variables):
        super(ExprFormatter, self).__init__()
        self.language_formatter = language_formatter
        self.variables = variables
        self.precedence = build_precedence_map()
        self.max_precedence = max(self.precedence.itervalues())

    def expr(self, o):
        # Check variable cache
        v = self.variables.get(o)
        if v is not None:
            return v

        # Visit children and wrap in () if necessary.
        # This could be improved by considering the
        # parsing order to avoid some (), but that
        # may be language dependent? (usually left-right).
        # Keeping it simple and safe for now at least.
        ops = []
        for op in o.operands():
            opc = self.visit(op)
            # Skip () around variables
            if not op in self.variables:
                po = self.precedence[o._uflclass]
                pop = self.precedence[op._uflclass]
                # Ignore left-right rule and just add
                # slightly more () than strictly necessary
                if po < self.max_precedence and pop <= po:
                    opc = '(' + opc + ')'
            ops.append(opc)

        # Delegate formatting
        return self.language_formatter(o, *ops)

    def terminal(self, o):
        # Check variable cache
        v = self.variables.get(o)
        if v is not None:
            return v
        # Delegate formatting
        return self.language_formatter(o)

    def multi_index(self, o):
        "Expecting expand_indices to have been applied, so all indices are fixed."
        return tuple(map(int, o))

    def indexed(self, o):
        """Gets value indices and passes on control to either
        grad_component or a target specific terminal formatter."""

        # TODO: Test variables/component/derivatives combos more!

        # Use eventual given variable.
        # Note that we do not want to look for a variable for
        # A, but rather for the specific component of A.
        # By only using scalar variables we keep the variables construct simple.
        v = self.variables.get(o)
        if v is not None:
            return v

        # o is A[ci]
        A, ci = o.operands()
        component = self.multi_index(ci)

        if isinstance(A, ufl.classes.Terminal):
            # o is the component of a terminal A
            # Ask the formatter to make the string
            return self.language_formatter(A, component)

        elif isinstance(A, ufl.classes.Grad):
            # A is grad(f)  <->  o is grad(f)[ci]
            # Pass on control to derivative annotation
            return self.grad_component(A, component)

        elif isinstance(A, ufl.classes.Restricted):
            # A is f('r')  <->  o is f('r')[ci]
            # Pass on control to restriction annotation
            return self.restricted_component(A, component)

        else:
            error("Invalid type %s in indexed formatter, "\
                  "have you applied expand_derivatives?" % type(A))

    def grad_component(self, o, component, derivatives=()):
        """Render the component of a grad.

        Note that a grad may not occur on its own, it is always inside
        an indexed because we're only handling scalar expressions here."""

        # TODO: Test variables/component/derivatives combos more!

        # Use eventual given variable.
        # Note that we do not want to look for a variable for f,
        # since o represents the value of the derivative of f, not f itself.
        v = self.variables.get(o)
        if v is not None:
            return v

        # o is grad(f)
        f, = o.operands()

        # Sorting derivative indices, can do this because the derivatives commute
        cj, cd = component[:-1], component[-1]
        derivatives = sorted(list(derivatives) + [component[-1]])

        if isinstance(f, ufl.classes.Terminal):
            # o is the derivative of a terminal expression f
            return self.language_formatter(f, cj, derivatives)

        elif isinstance(f, ufl.classes.Grad):
            # o is the grad of a grad, handle recursively
            return self.grad_component(f, cj, derivatives)

        elif isinstance(f, ufl.classes.Restricted):
            # o is the grad of a restricted something, handle recursively
            return self.restricted_component(f, cj, derivatives)

        else:
            error("Invalid type %s in grad formatter, "\
                  "have you applied expand_derivatives?" % type(f))

    def restricted(self, o):
        "If we hit a restricted directly, it is not inside an indexed or grad."
        uflacs_assert(o.shape() == (), "Expecting only scalar restricted here.")
        return self.restricted_component(o)

    def restricted_component(self, o, component=(), derivatives=()):
        restriction = o._side

        uflacs_assert(not isinstance(component, str), "EH?")

        A, = o.operands()
        uflacs_assert(isinstance(A, ufl.classes.Terminal),
                      "Assuming restrictions have been propagated all the way to the terminals!")

        return self.language_formatter(A, component, derivatives, restriction)
