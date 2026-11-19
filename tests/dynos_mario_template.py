"""Inspect the official Coop Deluxe Mario character template before DynOS export."""
import bpy, json, os
from pathlib import Path

out = Path(os.environ.get("BFAI_REPORT", "mario_template_report.json"))
objects, armatures, meshes = [], [], []
for obj in bpy.data.objects:
    row = {
        "name": obj.name, "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        "vertex_groups": [group.name for group in obj.vertex_groups],
        "vertices": len(obj.data.vertices) if obj.type == "MESH" else 0,
    }
    objects.append(row)
    if obj.type == "ARMATURE":
        armatures.append({"name": obj.name, "bones": [b.name for b in obj.data.bones],
                          "children": [c.name for c in obj.children]})
    if obj.type == "MESH":
        meshes.append(row)
report = {"blender_version": bpy.app.version_string, "scene": bpy.context.scene.name,
          "armatures": armatures, "meshes": meshes, "object_count": len(objects), "objects": objects}
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
if not armatures: raise RuntimeError("Mario template contains no armature")
if not meshes: raise RuntimeError("Mario template contains no mesh")
print("BFAI_MARIO_TEMPLATE_INSPECTION:PASS")
print("BFAI_MARIO_ARMATURES:" + json.dumps(armatures))
print("BFAI_MARIO_MESHES:" + json.dumps(meshes))
