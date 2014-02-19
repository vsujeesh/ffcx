
from uflacs.codeutils.format_code_structure import Block

def build_loops(loops, definitions, partitions):
    """Build code for a nested loop structure with
    partitions and glue code provided separately.
    The returned code should be formatted with
    format_code_structure. Example code structures:

    definitions[0]
    partitions[0]
    loops[1]
    {
        definitions[1]
        partitions[1]
    }

    loops[0]
    {
        definitions[0]
        partitions[0]
        loops[1]
        {
            definitions[1]
            partitions[1]
        }
    }

    definitions[0] # Geometry and coefficient functions
    partitions[0]  # Partition independent of x and test/trial f.
    loops[1]       # Quadrature loop over x
    {
        definitions[1] # Evaluation of geometry/coefficients
        partitions[1]  # Partition independent of test/trial f.
        loops[2]       # Loop over trial functions
        {
            definitions[2] # Evaluation of trial functions
            partitions[2]  # Partition independent of test f.
            loop[3]        # Loop over test functions
            {
                definitions[3] # Evaluation of test functions
                partitions[3]  # Assignment to element matrix
            }
        }
    }
    """
    code = []
    # Start with the inner loop and work out
    num_partitions = len(partitions)
    for p in range(num_partitions-1, -1, -1):
        # Put definitions before partition code
        body = [definitions[p],
                partitions[p]]
        # Recursively insert inner loops in outer loop bodies
        if code:
            body.append(code)
        # Create a loop with a block iff we have a loop header
        loop = loops[p]
        if loop:
            code = [loop, Block(body)]
        else:
            code = body
    return code

