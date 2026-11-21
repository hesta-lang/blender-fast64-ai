"""Create a small .blend file used to smoke-test the Android diagnostic workflow."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bpy
from blender_runner import dispatch

# Remove factory-startup objects so this fixture is deterministic.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

workspace = ROOT / "inbox" / "fixture-workspace"
workspace.mkdir(parents=True, exist_ok=True)
(workspace / "imports").mkdir(parents=True, exist_ok=True)

dispatch.run({
    "action": "create_mesh_object",
    "workspace": str(workspace),
    "params": {
        "name": "BFAI_DiagnosticFixture",
        "vertices": [
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
        ],
        "faces": [
            [0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
            [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
        ],
    },
})
dispatch.run({
    "action": "create_armature",
    "workspace": str(workspace),
    "params": {
        "name": "BFAI_DiagnosticRig",
        "bones": [{
            "name": "Root",
            "head": [0, 0, -1],
            "tail": [0, 0, 1],
            "parent": None,
            "use_deform": True,
            "use_connect": False,
        }],
    },
})
dispatch.run({
    "action": "set_vertex_weights",
    "workspace": str(workspace),
    "params": {
        "mesh_name": "BFAI_DiagnosticFixture",
        "armature_name": "BFAI_DiagnosticRig",
        "weights": [{"bone": "Root", "vertex": index, "weight": 1.0} for index in range(8)],
    },
})
dispatch.run({
    "action": "smart_uv_unwrap",
    "workspace": str(workspace),
    "params": {"mesh_name": "BFAI_DiagnosticFixture"},
})
dispatch.run({
    "action": "create_material",
    "workspace": str(workspace),
    "params": {
        "name": "BFAI_DiagnosticMaterial",
        "base_color": [0.5, 0.6, 0.8, 1.0],
        "metallic": 0.0,
        "roughness": 0.8,
        "assign_to_object": "BFAI_DiagnosticFixture",
    },
})
output = ROOT / "inbox" / "ci-fixture.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(output))
print("BFAI_FIXTURE=" + str(output))
