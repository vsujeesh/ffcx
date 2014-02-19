
# TODO: Attach data from ffc to target_formatter for element generation?
# TODO: Move integrate to be a target_formatter property?

from ufl.common import product
from ufl.classes import Argument, FormArgument
from ufl.algorithms import extract_unique_elements

from uflacs.utils.log import uflacs_assert

from uflacs.analysis.dependency_handler import DependencyHandler
from uflacs.analysis.table_utils import (generate_psi_table_name,
                                         get_ffc_table_values,
                                         strip_table_zeros,
                                         build_unique_tables,
                                         derivative_listing_to_counts,
                                         flatten_component)

from uflacs.codeutils.format_code_structure import format_code_structure, Indented, ArrayDecl

from uflacs.generation.compiler import compile_expression_partitions
from uflacs.generation.generate import generate_code_from_ssa, generate_expression_body

from uflacs.backends.ffc.ffc_language_formatter import FFCLanguageFormatter
from uflacs.backends.ffc.ffc_statement_formatter import FFCStatementFormatter

from uflacs.params import default_parameters

def build_element_counter_map(integrals_dict, element_replace_map):
    element_counter_map = {}
    for num_points in sorted(integrals_dict.keys()):
        element_counter_map[num_points] = {}
        ecm = element_counter_map[num_points]

        # Find all elements in this integrand and map them
        integrand = integrals_dict[num_points].integrand()
        elements = [element_replace_map[e] for e in extract_unique_elements(integrand)]

        # Count the elements in a stable sorting
        for element in sorted(elements):
            if element not in ecm:
                ecm[element] = len(ecm)
    return element_counter_map

def compute_tabulate_tensor_ir(ir,
                               integrals_dict,
                               form_data,
                               parameters):
    # TODO: Hack before we get default parameters properly into ffc
    p = default_parameters()
    p.update(parameters)
    parameters = p

    # These are already inserted by ffc representation code:
    #ir["domain_type"]
    #ir["quadrature_weights"] = { num_points: (w, (x,y)) }

    ir["function_replace_map"] = form_data.function_replace_map
    ir["object_names"] = {} #form_data.object_names # TODO
    ir["cell"] = form_data.integration_domains[0].cell()

    uflacs_assert(len(integrals_dict) == 1,
                  "Assuming a single quadrature rule per integral domain for now.")
    for num_points in sorted(integrals_dict.keys()):
        integrand = integrals_dict[num_points].integrand()
        partitions_ir = compile_expression_partitions(integrand, ir["function_replace_map"], parameters)
        ir["expression_partitions"] = partitions_ir

    # Build num_points/element to counter mapping
    ir["element_map"] = build_element_counter_map(integrals_dict, form_data.element_replace_map)

    return ir


def optimize_tabulate_tensor_ir(ir, parameters):
    # Hack before we get default parameters properly into ffc
    p = default_parameters()
    p.update(parameters)
    parameters = p

    # TODO: Implement some optimization here!
    oir = ir
    return oir


def build_tables(psi_tables, entitytype, element_counter_map, terminal_data):
    num_points, = element_counter_map.keys() # Assuming a single num_points value
    tables = {}
    preserve_tables = set()
    argument_tables = {}
    handled = set()
    for t, c, d, r in terminal_data:

        # Avoid duplicating tables because of restriction
        key = (t, c, d)
        if key in handled:
            continue
        handled.add(key)

        if isinstance(t, FormArgument):
            element = t.element()

            #import pdb
            #pdb.set_trace()

            element_counter = element_counter_map[num_points][element]

            # Change derivatives format for table lookup
            gdim = element.cell().geometric_dimension()
            derivatives = tuple(derivative_listing_to_counts(d, gdim))

            # Flatten component
            flat_component = flatten_component(c, t.shape(), element.symmetry())

            # Get name and values for this particular table
            name = generate_psi_table_name(element_counter, flat_component,
                                         derivatives, entitytype)
            table = get_ffc_table_values(psi_tables, entitytype, num_points,
                                         element, flat_component, derivatives)
            tables[name] = table
            if 0:
                print
                print element
                print name
                print table
                print

        if isinstance(t, Argument):
            # Avoid deleting the original table so we can loop over all dofs for arguments:
            preserve_tables.add(name)
            # Group argument tables by t,c for nonzero detection TODO: Not used yet
            if (t,c) not in argument_tables:
                argument_tables[(t,c)] = set()
            argument_tables[(t,c)].add(name)


    # FIXME: Build argument component dof ranges, here or somewhere else?
    #element_counter = element_counter_map[num_points][element]
    #gdim = element.cell().geometric_dimension()
    #derivatives = tuple(derivative_listing_to_counts(d, gdim))
    #flat_component = flatten_component(c, t.shape(), element.symmetry())
    #name = generate_psi_table_name(element_counter, flat_component,
    #                               derivatives, entitytype)
    #(uname, begin, end) = ir["table_ranges"][name]


    # Apply zero stripping to all tables
    stripped_tables = {}
    table_ranges = {}
    for name, table in tables.iteritems():
        begin, end, stable = strip_table_zeros(table)
        stripped_tables[name] = stable
        table_ranges[name] = (begin, end)

        # Preserve some tables under a modified name:
        if name in preserve_tables:
            pname = "p" + name # Hack! TODO: Make a cleaner solution!
            begin, end = 0, table.shape[-1]
            stripped_tables[pname] = table
            table_ranges[pname] = (begin, end)

    # Build unique table mapping
    unique_tables, table_mapping = build_unique_tables(stripped_tables)

    # Build mapping of constructed table names to unique names
    unique_table_names = {}
    mapping_to_name = {}
    for name in sorted(table_mapping.keys()):
        ui = table_mapping[name]
        if ui not in mapping_to_name:
            mapping_to_name[ui] = name
        uname = mapping_to_name[ui]
        unique_table_names[name] = uname

    # Build mapping of constructed table names to data: unique name, table range
    table_data = {}
    for name in sorted(table_mapping.keys()):
        uname = unique_table_names[name]
        b, e = table_ranges[name]
        table_data[name] = (uname, b, e)

    # Format unique tables into code
    tables_code = [ArrayDecl("static const double", mapping_to_name[ui],
                             table.shape, table)
                   for ui, table in enumerate(unique_tables)
                   if product(table.shape) > 0]
    return tables_code, table_data

def generate_tabulate_tensor_code(ir, parameters):
    # Create an object to track dependencies across other components
    dependency_handler = DependencyHandler(ir["terminals"], ir["function_replace_map"], ir["object_names"])

    # Analyse the psi_tables that are required by functions etc.
    tables_code, table_data = build_tables(ir["psi_tables"],
                                           ir["entitytype"],
                                           ir["element_map"],
                                           dependency_handler.terminal_data)
    ir["table_ranges"] = table_data

    # Create backend specific plugin objects
    language_formatter = FFCLanguageFormatter(dependency_handler, ir)
    statement_formatter = FFCStatementFormatter(dependency_handler, ir)

    # Generate code partitions from ir
    uflacs_assert(len(ir["expression_partitions"]) == 1,
                  "Assuming a single quadrature rule per integral domain for now.")
    for num_points in sorted(ir["expression_partitions"]):
        partitions_ir = ir["expression_partitions"] #[num_points]
        partition_codes, final_variable_names = generate_code_from_ssa(partitions_ir, language_formatter)

    # Generate full code from snippets
    expression_body = generate_expression_body(statement_formatter,
                                               partition_codes,
                                               final_variable_names,
                                               ir["num_registers"])

    # Format uflacs specific code structures into a single
    # string and place in dict before returning to ffc
    body = format_code_structure(Indented([language_formatter.get_using_statements(),
                                           tables_code, expression_body]))
    code = {
        "tabulate_tensor": body,
        "additional_includes_set": language_formatter.get_includes(),
        }
    return code

def compile_tabulate_tensor_code(form, optimize=True):
    "Compile_code is a joining of compute_ir, optimize_ir, and generate_ir, FOR TESTING."
    from ffc.cpp import set_float_formatting
    from ffc.uflacsrepr import compute_integral_ir, optimize_integral_ir, generate_integral_code

    # Fake the initialization necessary to get this running through
    set_float_formatting(8)
    parameters = { "optimize": optimize }
    prefix = "uflacs_testing"
    form_id = 0

    # Apply ufl preprocessing
    form_data = form.compute_form_data()

    tt_codes = []
    for itg_data in form_data.integral_data:
        # Just make a fixed choice of cubic default quadrature rule
        itg_data.metadata["quadrature_degree"] = itg_data.metadata.get("quadrature_degree", 3)
        itg_data.metadata["quadrature_rule"] = itg_data.metadata.get("quadrature_rule", "default")

        # Call uflacs representation functions from ffc, which again calls the matching uflacs functions
        ir = compute_integral_ir(itg_data, form_data, form_id, parameters)
        if optimize:
            ir = optimize_integral_ir(ir, parameters)
        code = generate_integral_code(ir, prefix, parameters)

        # Store just the tabulate tensor part generated by uflacs
        tt_codes.append(code["tabulate_tensor"])

    # Just joint the tabulate tensor bodies and return
    code = ('\n' + '/'*60 + '\n').join(tt_codes)
    return code
