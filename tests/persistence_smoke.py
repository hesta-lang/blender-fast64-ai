"""Verify that separate Blender subprocesses share one saved active.blend."""
import os
from pathlib import Path

from server.blender_runner import WORK, run_blender


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    if WORK.exists():
        for path in sorted(WORK.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    WORK.mkdir(parents=True, exist_ok=True)

    created = run_blender(
        "create_mesh_object",
        name="PersistentMesh",
        vertices=[[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        faces=[[0, 1, 2, 3]],
    )
    check(created["created"] == "PersistentMesh", "mesh creation did not complete")

    # This is a new Blender process. It must load the file saved by the previous call.
    objects = run_blender("list_objects")
    check(any(item["name"] == "PersistentMesh" for item in objects), "scene did not persist into the next worker process")

    transformed = run_blender(
        "set_object_transform",
        name="PersistentMesh",
        location=[4.0, 5.0, 6.0],
    )
    check(transformed["location"] == [4.0, 5.0, 6.0], "transform did not run on the persisted object")

    # Another new process confirms the material can be assigned to that same saved mesh.
    material = run_blender(
        "create_material",
        name="PersistentMaterial",
        base_color=[0.2, 0.4, 0.6, 1.0],
        assign_to_object="PersistentMesh",
    )
    check(material["assigned_to"] == "PersistentMesh", "material assignment lost the scene")
    scene = run_blender("inspect_scene")
    entry = next((obj for obj in scene["objects"] if obj["name"] == "PersistentMesh"), None)
    check(entry is not None, "persisted object missing after three worker launches")
    check("PersistentMaterial" in scene["materials"], "material did not persist")

    project = WORK / "active.blend"
    check(project.is_file(), "active.blend was not saved automatically")
    print("BFAI_PERSISTENCE_SMOKE:PASS")


if __name__ == "__main__":
    main()
