"""Runs inside Blender: blender --background --python tests/blender_smoke.py."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bpy
from blender_runner import dispatch


def check(condition, message):
    if not condition:
        raise AssertionError(message)


workspace = Path(tempfile.mkdtemp(prefix="bfai-blender-smoke-")).resolve()
(workspace / "imports").mkdir(parents=True, exist_ok=True)

mesh_result = dispatch.run({
    "action": "create_mesh_object",
    "workspace": str(workspace),
    "params": {
        "name": "BFAI_SmokeMesh",
        "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        "faces": [[0, 1, 2, 3]],
    },
})
check(mesh_result["vertices"] == 4 and mesh_result["faces"] == 1, "mesh creation failed")

armature_result = dispatch.run({
    "action": "create_armature",
    "workspace": str(workspace),
    "params": {
        "name": "BFAI_SmokeRig",
        "bones": [
            {"name": "Root", "head": [0, 0, 0], "tail": [0, 0, 1], "parent": None, "use_deform": True, "use_connect": False},
        ],
    },
})
check(armature_result["bones"] == ["Root"], "armature creation failed")

weight_result = dispatch.run({
    "action": "set_vertex_weights",
    "workspace": str(workspace),
    "params": {
        "mesh_name": "BFAI_SmokeMesh",
        "armature_name": "BFAI_SmokeRig",
        "weights": [{"bone": "Root", "vertex": index, "weight": 1.0} for index in range(4)],
    },
})
check(weight_result["weighted_vertices"] == 4, "vertex weights failed")

uv_result = dispatch.run({
    "action": "smart_uv_unwrap",
    "workspace": str(workspace),
    "params": {"mesh_name": "BFAI_SmokeMesh"},
})
check(bool(uv_result["uv_layers"]), "UV unwrap failed")

material_result = dispatch.run({
    "action": "create_material",
    "workspace": str(workspace),
    "params": {
        "name": "BFAI_SmokeMaterial",
        "base_color": [0.3, 0.5, 0.8, 1.0],
        "metallic": 0.0,
        "roughness": 0.7,
        "assign_to_object": "BFAI_SmokeMesh",
    },
})
check(material_result["assigned_to"] == "BFAI_SmokeMesh", "material assignment failed")

save_result = dispatch.run({
    "action": "save_project",
    "workspace": str(workspace),
    "params": {},
})
check(Path(save_result["saved"]).is_file(), "blend project save failed")

print("BFAI_BLENDER_SMOKE:PASS")
