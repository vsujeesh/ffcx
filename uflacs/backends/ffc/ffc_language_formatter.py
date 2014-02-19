
from ufl.common import component_to_index
from ufl.permutation import build_component_numbering
from ufl.algorithms import MultiFunction

from uflacs.utils.log import uflacs_assert, warning, error

# TODO: The organization of code utilities is a bit messy...
from uflacs.codeutils.cpp_format import CppFormatterRulesCollection
from uflacs.geometry.default_names import names
from uflacs.backends.ffc.ffc_statement_formatter import langfmt
from uflacs.backends.ffc.ffc_statement_formatter import (format_element_table_access, format_entity_name)
from uflacs.analysis.table_utils import derivative_listing_to_counts, flatten_component


class FFCLanguageFormatter(MultiFunction, CppFormatterRulesCollection):
    """FFC specific cpp formatter class."""
    def __init__(self, dependency_handler, ir):
        MultiFunction.__init__(self)
        CppFormatterRulesCollection.__init__(self)

        # An object used to track who depends on what
        self._dependency_handler = dependency_handler

        # The rest of the FFC representation dict, flexible way to work for now,
        # maybe replace with whatever we need more specifically later
        self._ir = ir

        self._entitytype = ir["entitytype"]
        self._gdim = ir["cell"].geometric_dimension()

        # HACK! FIXME: Handle different quadrature rules!
        self._num_points, = ir["quadrature_weights"].keys()

        self._using_names = set()
        self._includes = set(("#include <cstring>",
                              "#include <cmath>"))

    def add_using(self, name):
        self._using_names.add(name)

    def add_include(self, name):
        self._includes.add(name)

    def get_using_statements(self):
        return ["using %s;" % name for name in sorted(self._using_names)]

    def get_includes(self):
        return sorted(self._includes)

    def geometric_quantity(self, o, component=(), derivatives=(), restriction=None):
        "Generic rendering of variable names for all piecewise constant geometric quantities."
        uflacs_assert(not derivatives,
                      "Compiler should be able to simplify derivatives of geometry.")

        # Simply using the UFL str to define the name in the generated code, ensures consistency
        name = str(o)
        if restriction:
            name = name + restriction

        # Indexing if there is a shape
        sh = o.shape()
        if sh:
            uflacs_assert(component, "Missing component for nonscalar %r." % o)
            code = langfmt.array_access(name, component_to_index(component, sh))
        else:
            uflacs_assert(component == (), "Component specified for scalar %r." % o)
            code = name

        # Make a record of dependency
        self._dependency_handler.require(o, component, derivatives, restriction, code)

        return code

    def facet_area(self, o, component=(), derivatives=(), restriction=None):
        uflacs_assert(restriction is None, "Assuming facet_area is not restricted.")
        return self.geometric_quantity(o, component, derivatives, restriction)

    def _piecewise_constant_coefficient(self, o, component, derivatives, restriction):
        uflacs_assert(not derivatives,
                      "Not expecting derivatives of constant coefficients!")

        # Map component to flat index
        vi2si, si2vi = build_component_numbering(o.shape(), o.element().symmetry())
        flat_component = vi2si[component]
        size = len(si2vi)

        # Offset index if on second cell in interior facet integral
        if restriction == "-":
            flat_component += size

        # Return direct reference to dof array
        return langfmt.array_access(names.w, o.count(), flat_component)

    def _computed_form_argument_name(self, o, component, derivatives, restriction, basename):

        if derivatives:
            # Change format of derivatives tuple, counting instead of enumerating
            gdim = self._gdim
            derivative_counts = derivative_listing_to_counts(derivatives, gdim)
            # Add derivatives to name
            der = "_d%s" % ''.join(map(str,derivative_counts))
        else:
            der = ""

        if o.shape():
            # Add flattened component to name
            flat_component = flatten_component(component, o.shape(), o.element().symmetry())
            comp = "_c%d" % flat_component
        else:
            comp = ""

        # Add restriction to name
        res = names.restriction_postfix[restriction]

        # Format base coefficient (derivative) name
        code = "%s%d%s%s%s" % (basename, o.number(), der, comp, res)

        return code

    def coefficient(self, o, component=(), derivatives=(), restriction=None):
        dh = self._dependency_handler

        o = dh.form_argument_mapping.get(o, o)
        uflacs_assert(o.count() >= 0,
            "Expecting positive count, provide a renumbered form argument mapping.")

        if o.is_cellwise_constant():
            return self._piecewise_constant_coefficient(o, component, derivatives, restriction)
        else:
            code = self._computed_form_argument_name(o, component, derivatives, restriction, names.wbase)
            dh.require(o, component, derivatives, restriction, code)
            return code

    def argument(self, o, component=(), derivatives=(), restriction=None):
        dh = self._dependency_handler

        uflacs_assert(o.number() >= 0,
            "Expecting positive count, provide a renumbered form argument mapping.")

        if derivatives:
            code = self._computed_form_argument_name(o, component, derivatives, restriction, names.vbase)
            dh.require(o, component, derivatives, restriction, code)
        else:
            # Pick entity index variable name, following ufc argument names
            entity = format_entity_name(self._entitytype, restriction)

            idof = "%s%d" % (names.ia, o.number()) # FIXME: Make reusable function

            element = o.element()

            flat_component = flatten_component(component, element.value_shape(), element.symmetry())

            # No need to store basis function value in its own variable, just get table value directly
            code = format_element_table_access(self._ir, self._entitytype, self._num_points,
                                               element, flat_component, (), entity, idof, True)

        return code
