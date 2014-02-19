
import numpy

def int_array(size):
    return numpy.zeros(size, dtype=int)

def object_array(size):
    # TODO: Any gain in using a numpy array for object lists?
    #return numpy.array(dtype=object)
    return [None]*size

class CRS(object):
    """A compressed row storage matrix with no sparsity pattern."""
    def __init__(self, row_capacity, element_capacity, dtype):
        self.row_offsets = int_array(row_capacity+1)
        self.data = numpy.zeros(element_capacity, dtype=dtype)
        self.num_rows = 0

    def push_row(self, elements):
        n = len(elements)
        a = self.row_offsets[self.num_rows]
        b = a + n
        self.data[a:b] = elements
        self.num_rows += 1
        self.row_offsets[self.num_rows] = b

    @property
    def num_elements(self):
        return self.row_offsets[self.num_rows]

    def __getitem__(self, row):
        if row < 0 or row >= self.num_rows:
            raise IndexError("Row number out of range!")
        a = self.row_offsets[row]
        b = self.row_offsets[row+1]
        return self.data[a:b]

    def __len__(self):
        return self.num_rows

    def __str__(self):
        return "[%s]" % (', '.join(str(row) for row in self),)

def list_to_crs(elements):
    n = len(elements)
    crs = CRS(n, n, type(elements[0]))
    for i in xrange(n):
        crs.push_row((elements[i],))
    return crs

def rows_dict_to_crs(rows, num_rows, num_elements, dtype):
    crs = CRS(num_rows, num_elements, dtype)
    for i in xrange(num_rows):
        row = rows.get(i, ())
        crs.push_row(row)
    return crs

def rows_to_crs(rows, num_rows, num_elements, dtype):
    crs = CRS(num_rows, num_elements, dtype)
    for row in rows:
        crs.push_row(row)
    return crs
