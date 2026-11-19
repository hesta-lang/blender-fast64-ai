import unittest
from server.validation import finite_vector, safe_filename, validate_mesh_data

class ValidationTests(unittest.TestCase):
    def test_vector(self):
        self.assertEqual(finite_vector([1, 2, 3]), [1.0, 2.0, 3.0])
    def test_nan_rejected(self):
        with self.assertRaises(ValueError): finite_vector([0, float("nan"), 1])
    def test_filename(self):
        self.assertEqual(safe_filename("Steve.fbx"), "Steve.fbx")
        with self.assertRaises(ValueError): safe_filename("../Steve.fbx")
    def test_mesh(self):
        v, f = validate_mesh_data([[0,0,0],[1,0,0],[0,1,0]], [[0,1,2]])
        self.assertEqual(len(v), 3)
        self.assertEqual(f, [[0,1,2]])

if __name__ == "__main__": unittest.main()
