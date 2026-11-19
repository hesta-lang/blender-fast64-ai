import unittest
from server.validation import (
    finite_vector, safe_filename, safe_texture_filename, validate_mesh_data,
    validate_bones, validate_weights, validate_color, validate_scalar,
)


class ValidationTests(unittest.TestCase):
    def test_vector(self):
        self.assertEqual(finite_vector([1, 2, 3]), [1.0, 2.0, 3.0])

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            finite_vector([0, float("nan"), 1])

    def test_boolean_vector_rejected(self):
        with self.assertRaises(ValueError):
            finite_vector([True, 0, 1])

    def test_filename(self):
        self.assertEqual(safe_filename("Steve.fbx"), "Steve.fbx")
        with self.assertRaises(ValueError):
            safe_filename("../Steve.fbx")

    def test_texture_filename(self):
        self.assertEqual(safe_texture_filename("skin.png"), "skin.png")
        with self.assertRaises(ValueError):
            safe_texture_filename("malware.py")

    def test_mesh(self):
        vertices, faces = validate_mesh_data([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]])
        self.assertEqual(len(vertices), 3)
        self.assertEqual(faces, [[0, 1, 2]])

    def test_mesh_rejects_bad_index(self):
        with self.assertRaises(ValueError):
            validate_mesh_data([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 3]])

    def test_bones_and_parent(self):
        bones = validate_bones([
            {"name": "Root", "head": [0, 0, 0], "tail": [0, 0, 1]},
            {"name": "Head", "head": [0, 0, 1], "tail": [0, 0, 2], "parent": "Root"},
        ])
        self.assertEqual(bones[1]["parent"], "Root")

    def test_bone_flags_must_be_boolean(self):
        with self.assertRaises(ValueError):
            validate_bones([{"name": "Root", "head": [0, 0, 0], "tail": [0, 0, 1], "use_deform": "false"}])

    def test_bone_cycle_rejected(self):
        with self.assertRaises(ValueError):
            validate_bones([
                {"name": "A", "head": [0, 0, 0], "tail": [0, 0, 1], "parent": "B"},
                {"name": "B", "head": [0, 0, 1], "tail": [0, 0, 2], "parent": "A"},
            ])

    def test_weights(self):
        result = validate_weights([{"bone": "Root", "vertex": 0, "weight": 1}], ["Root"], 3)
        self.assertEqual(result[0]["weight"], 1.0)

    def test_empty_weights_rejected(self):
        with self.assertRaises(ValueError):
            validate_weights([], ["Root"], 3)

    def test_weight_index_rejected(self):
        with self.assertRaises(ValueError):
            validate_weights([{"bone": "Root", "vertex": 3, "weight": 1}], ["Root"], 3)

    def test_color_and_scalar(self):
        self.assertEqual(validate_color([1, 0, 0, 1]), [1.0, 0.0, 0.0, 1.0])
        self.assertEqual(validate_scalar(0.4, "roughness", 0, 1), 0.4)
        with self.assertRaises(ValueError):
            validate_color([1, 0, 0, 2])


if __name__ == "__main__":
    unittest.main()
