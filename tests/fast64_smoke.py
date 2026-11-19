"""Integration smoke test against the pinned, real Fast64 addon."""
import os
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


def main():
    addon_path = os.environ.get("BFAI_FAST64_ADDON_PATH")
    check(addon_path and (Path(addon_path) / "__init__.py").is_file(), "Fast64 addon source was not checked out")
    dispatch.ensure_fast64_addon()
    check(hasattr(bpy.ops.object, "convert_bsdf"), "Fast64 Principled-to-F3D converter is not registered")
    check(hasattr(bpy.ops.object, "sm64_export_geolayout_armature"), "Fast64 SM64 armature exporter is not registered")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    workspace = Path(tempfile.mkdtemp(prefix="bfai-fast64-smoke-")).resolve()
    (workspace / "imports").mkdir(parents=True, exist_ok=True)
    (workspace / "exports").mkdir(parents=True, exist_ok=True)

    mesh = dispatch.run({
        "action": "create_mesh_object",
        "workspace": str(workspace),
        "params": {
            "name": "BFAI_SM64Mesh",
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
    check(mesh["vertices"] == 8, "Fast64 test mesh creation failed")

    dispatch.run({
        "action": "create_armature",
        "workspace": str(workspace),
        "params": {
            "name": "BFAI_SM64Rig",
            "bones": [
                {
                    "name": "Root",
                    "head": [0, 0, 0],
                    "tail": [0, 0, 1],
                    "parent": None,
                    "use_deform": False,
                    "use_connect": False,
                },
                {
                    "name": "Body",
                    "head": [0, 0, 1],
                    "tail": [0, 0, 2],
                    "parent": "Root",
                    "use_deform": True,
                    "use_connect": False,
                },
            ],
        },
    })

    dispatch.run({
        "action": "create_material",
        "workspace": str(workspace),
        "params": {
            "name": "BFAI_Principled",
            "base_color": [0.35, 0.55, 0.8, 1.0],
            "metallic": 0.0,
            "roughness": 0.8,
            "assign_to_object": "BFAI_SM64Mesh",
        },
    })
    dispatch.run({
        "action": "smart_uv_unwrap",
        "workspace": str(workspace),
        "params": {"mesh_name": "BFAI_SM64Mesh"},
    })

    converted = dispatch.run({
        "action": "convert_materials_to_f3d",
        "workspace": str(workspace),
        "params": {"mesh_name": "BFAI_SM64Mesh", "rename_uv_maps": True},
    })
    check(converted["native_f3d"], "Fast64 conversion did not produce a native F3D material")

    assignments = [{"vertex": index, "bone": "Body"} for index in range(8)]
    skinning = dispatch.run({
        "action": "set_sm64_binary_skinning",
        "workspace": str(workspace),
        "params": {
            "mesh_name": "BFAI_SM64Mesh",
            "armature_name": "BFAI_SM64Rig",
            "assignments": assignments,
        },
    })
    check(skinning["binary_skinning"], "SM64 binary skinning was not applied")

    exported = dispatch.run({
        "action": "export_sm64_armature",
        "workspace": str(workspace),
        "params": {
            "armature_name": "BFAI_SM64Rig",
            "output_folder": "fast64-smoke",
            "object_name": "bfai_smoke",
            "save_textures": False,
        },
    })
    check(exported["files"], "Fast64 geolayout C exporter generated no files")
    check(any(path.endswith(".c") for path in exported["files"]), "Fast64 export did not produce C output")
    print("BFAI_FAST64_SMOKE:PASS")
    print("BFAI_FAST64_OUTPUT:" + ", ".join(exported["files"]))


if __name__ == "__main__":
    main()
