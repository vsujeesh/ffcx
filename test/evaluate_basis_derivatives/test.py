__author__ = "Kristian B. Oelgaard (k.b.oelgaard@gmail.com)"
__date__ = "2010-01-18"
__copyright__ = "Copyright (C) 2010 Kristian B. Oelgaard"
__license__  = "GNU GPL version 3 or any later version"

# Last changed: 2010-01-18

from cppcode import evaluate_basis_derivatives_code
from ufl import FiniteElement, MixedElement

import sys, os, commands, pickle, numpy, shutil

# Elements, supported by FFC and FIAT, and their supported shape and orders
# TODO: RT order 0 gives error from FIAT, but is allowed by UFL
# TODO: Nedelec order 0 gives error from FIAT, but is allowed by UFL
single_elements = [ {"family": "Lagrange",\
                      "shapes": ["interval", "triangle", "tetrahedron"],\
                      "orders": [1, 2, 3, 4]},\
                    {"family": "Discontinuous Lagrange",\
                      "shapes": ["interval", "triangle", "tetrahedron"],\
                      "orders": [0, 1, 2, 3, 4]},\
                    {"family": "Crouzeix-Raviart",\
                      "shapes": ["triangle", "tetrahedron"],\
                      "orders": [1]},\
                    {"family": "Raviart-Thomas",\
                      "shapes": ["triangle", "tetrahedron"],\
                      "orders": [1, 2]},\
                    {"family": "Brezzi-Douglas-Marini",\
                      "shapes": ["triangle", "tetrahedron"],\
                      "orders": [1, 2, 3]},\
                    {"family": "Brezzi-Douglas-Fortin-Marini",\
                      "shapes": ["triangle", "tetrahedron"],\
                      "orders": [1, 2, 3]},\
                    {"family": "Nedelec 1st kind H(curl)",\
                      "shapes": ["triangle", "tetrahedron"],\
                      "orders": [1, 2]}]

# Create some mixed elements
dg0_tri = FiniteElement("DG", "triangle", 0)
dg1_tri = FiniteElement("DG", "triangle", 1)
cg1_tri = FiniteElement("CG", "triangle", 1)
cr1_tri = FiniteElement("CR", "triangle", 1)
rt1_tri = FiniteElement("RT", "triangle", 1)
bdm1_tri = FiniteElement("BDM", "triangle", 1)
ned1_tri = FiniteElement("N1curl", "triangle", 1)

dg0_tet = FiniteElement("DG", "tetrahedron", 0)
dg1_tet = FiniteElement("DG", "tetrahedron", 1)
cg1_tet = FiniteElement("CG", "tetrahedron", 1)
cr1_tet = FiniteElement("CR", "tetrahedron", 1)
rt1_tet = FiniteElement("RT", "tetrahedron", 1)
bdm1_tet = FiniteElement("BDM", "tetrahedron", 1)
ned1_tet = FiniteElement("N1curl", "tetrahedron", 1)

mixed_elements = [MixedElement([dg0_tri]*4), MixedElement([cg1_tri]*3), MixedElement([bdm1_tri]*2),\
                  MixedElement([dg1_tri, cg1_tri, cr1_tri, rt1_tri, bdm1_tri, ned1_tri]),\
                  MixedElement([MixedElement([rt1_tri, cr1_tri]), cg1_tri, ned1_tri]),\
                  MixedElement([ned1_tri, dg1_tri, MixedElement([rt1_tri, cr1_tri])]),\
                  MixedElement([dg0_tet]*4), MixedElement([cg1_tet]*3), MixedElement([bdm1_tet]*2),\
                  MixedElement([dg1_tet, cg1_tet, cr1_tet, rt1_tet, bdm1_tet, ned1_tet]),\
                  MixedElement([MixedElement([rt1_tet, cr1_tet]), cg1_tet, ned1_tet]),\
                  MixedElement([ned1_tet, dg1_tet, MixedElement([rt1_tet, cr1_tet])])]

ffc_failed = []
gcc_failed = []
run_failed = []

def check_results(values, reference):
    "Check results and print summary."

    missing_refs = []
    diffs = []
    num_ok = 0
    print ""
    for element, deriv_orders in values.items():
        print "\nResults for %s:" % element

        for deriv_order, vals in deriv_orders.items():
            if vals is None:
                print "Error"
                continue

            # Get reference values
            if not element in reference or not deriv_order in reference[element]:
                missing_refs.append(element + "order %d" % deriv_order)
                print "Missing reference"
                continue

            refs = reference[element][deriv_order]
            tol = 1e-12

            e = max(abs(vals - refs))
            if e < tol:
                num_ok += 1
                print "Derivative order: %d, OK: (diff = %g)" % (deriv_order, e)
            else:
                print "*** (Derivative order: %d, diff = %g)" % (deriv_order, e)
                diffs.append(element + "order %d" % deriv_order)

    if ffc_failed == gcc_failed == run_failed == missing_refs == diffs:
        print "\nAll %d elements verified OK" % len(reference)
        return 0
    if len(ffc_failed) > 0:
        print "\n*** FFC compilation failed for the following elements:\n" + "\n".join(ffc_failed)
    if len(gcc_failed) > 0:
        print "\n*** g++ compilation failed for the following elements:\n" + "\n".join(gcc_failed)
    if len(run_failed) > 0:
        print "\n*** Evaluation failed (seg. fault?) for the following elements:\n" + "\n".join(run_failed)
    if len(missing_refs) > 0:
        print "\n*** No reference values were found for the following elements:\n" + "\n".join(missing_refs)
    if len(diffs) > 0:
        print "\n*** Difference in values were found for the following elements:\n" + "\n".join(diffs)
    return 1

def compile_element(ufl_element):
    "Create UFL form file with a single element in it and compile it with FFC"
    f = open("test.ufl", "w")
    if isinstance(ufl_element, (FiniteElement, MixedElement)):
        f.write("element = " + repr(ufl_element))
    f.close()
    error, out = commands.getstatusoutput("ffc test.ufl")
    if error:
        ffc_failed.append(repr(ufl_element))
    return error

def get_element_name(ufl_element):
    "Extract relevant element name from header file."
    f = open("test.h")
    lines = f.readlines()
    f.close()

    signature = repr(ufl_element)
    name = None
    for e, l in enumerate(lines):
        if "class" in l and "finite_element" in l:
            name = l
        if signature in l:
            break
    if name is None:
        raise RuntimeError("No finite element class found")
    return name.split()[1][:-1]

def compute_values(ufl_element, deriv_order):
    "Compute values of basis functions for given element."

    # Get relevant element name
    element_name = get_element_name(ufl_element)

    # Create g++ code
    num_derivs = ufl_element.cell().topological_dimension()**deriv_order
    options = {"element": element_name, "derivative_order":deriv_order, "num_derivatives":num_derivs}
    code = evaluate_basis_derivatives_code % options
    f = open("evaluate_basis_derivatives.cpp", "w")
    f.write(code)
    f.close()

    # Compile g++ code
    c = "g++ `pkg-config --cflags ufc-1` -Wall -Werror -o evaluate_basis_derivatives evaluate_basis_derivatives.cpp"
    error, output = commands.getstatusoutput(c)
    if error:
        gcc_failed.append(repr(ufl_element))
        return None

    # Run compiled code and get values
    error, output = commands.getstatusoutput("./evaluate_basis_derivatives")
    if error:
        run_failed.append(repr(ufl_element))
        return None
    values = [float(value) for value in output.split(" ") if len(value) > 0]
    return numpy.array(values)

def print_refs():
    if os.path.isfile("reference.pickle"):
        reference = pickle.load(open("reference.pickle", "r"))
        for elem, derivs in reference.items():
            for deriv_order, vals in derivs.items():
                print
                print elem
                print deriv_order
                print vals
    else:
        raise RuntimeError("No references to print")

def main(args):
    "Call evaluate basis derivatives for a range of different elements."

    if "refs" in args:
        print_refs()
        return 0

    # Change to temporary folder and copy form files
    if not os.path.isdir("tmp"):
        os.mkdir("tmp")
    os.chdir("tmp")

    values = {}
    # Evaluate basis for single elements
    print "\nComputing evaluate_basis_derivatives for single elements"
    for element in single_elements:
        for shape in element["shapes"]:
            for order in element["orders"]:
                ufl_element = FiniteElement(element["family"], shape, order)
                print "Compiling element: ", str(ufl_element)
                error = compile_element(ufl_element)
                if error:
                    continue
                print "Computing values"
                values[repr(ufl_element)] = {}
                for deriv_order in range(1,4):
                    values[repr(ufl_element)][deriv_order] = compute_values(ufl_element, deriv_order)

    # Evaluate basis for single elements
    print "\nComputing evaluate_basis_derivatives for mixed elements"
    for ufl_element in mixed_elements:
        print "Compiling element: ", str(ufl_element)
        error = compile_element(ufl_element)
        if error:
            continue
        print "Computing values"
        values[repr(ufl_element)] = {}
        for deriv_order in range(1,4):
            values[repr(ufl_element)][deriv_order] = compute_values(ufl_element, deriv_order)

    # Load or update reference values
    os.chdir(os.pardir)
    if os.path.isfile("reference.pickle"):
        reference = pickle.load(open("reference.pickle", "r"))
    else:
        print "Unable to find reference values, storing current values."
        pickle.dump(values, open("reference.pickle", "w"))
        return 0

    # Check results
    error = check_results(values, reference)

    if not error:
        # Remove temporary directory
        shutil.rmtree("tmp")
    return error

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))