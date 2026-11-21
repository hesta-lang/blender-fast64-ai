bl_info = {
    "name": "Blender Fast64 AI Bridge Diagnostics",
    "author": "hesta-lang",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > AI Bridge",
    "description": "Inspect Blender asset links and export a trace report for AI-assisted debugging",
    "category": "3D View",
}

import bpy
import json
import math
from pathlib import Path
from datetime import datetime, timezone


def _image_node_report(node):
    image = node.image
    if image is None:
        return {"node": node.name, "image": None, "connected": False}
    path = bpy.path.abspath(image.filepath) if image.filepath else ""
    packed = bool(getattr(image, "packed_file", None) or getattr(image, "packed_files", None))
    return {
        "node": node.name,
        "image": image.name,
        "filepath": image.filepath,
        "absolute_path": path or None,
        "exists": bool(path and Path(path).is_file()),
        "packed": packed,
        "size": [int(image.size[0]), int(image.size[1])],
    }


def _build_active_report(obj):
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "blender_version": bpy.app.version_string,
        "scene": bpy.context.scene.name,
        "active_object": obj.name if obj else None,
        "issues": [],
    }
    if obj is None:
        report["issues"].append({"severity": "error", "code": "no_active_object"})
        return report
    report["source"] = {
        key: obj.get(key)
        for key in ("bfai_source_file", "bfai_source_format", "bfai_source_sha256", "bfai_imported_at", "bfai_pipeline_stage")
        if obj.get(key) is not None
    }
    report["object"] = {
        "name": obj.name,
        "type": obj.type,
        "location": [float(v) for v in obj.location],
        "rotation_euler": [float(v) for v in obj.rotation_euler],
        "scale": [float(v) for v in obj.scale],
        "dimensions": [float(v) for v in obj.dimensions],
        "parent": obj.parent.name if obj.parent else None,
        "children": [child.name for child in obj.children],
        "collections": sorted(collection.name for collection in obj.users_collection),
    }
    if obj.type != "MESH":
        report["issues"].append({"severity": "warning", "code": "active_object_is_not_mesh"})
        return report
    mesh = obj.data
    mesh.calc_loop_triangles()
    report["mesh"] = {
        "data_name": mesh.name,
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "triangles": len(mesh.loop_triangles),
        "uv_layers": [],
        "materials": [],
        "vertex_groups": [group.name for group in obj.vertex_groups],
        "modifiers": [],
    }
    for layer in mesh.uv_layers:
        values = [loop.uv for loop in layer.data]
        report["mesh"]["uv_layers"].append({
            "name": layer.name,
            "loops": len(values),
            "non_finite": sum(1 for uv in values if not all(math.isfinite(float(v)) for v in uv)),
        })
    if not mesh.uv_layers:
        report["issues"].append({"severity": "warning", "code": "mesh_has_no_uv_map"})
    if not obj.material_slots:
        report["issues"].append({"severity": "error", "code": "mesh_has_no_material_slots"})
    for slot in obj.material_slots:
        material = slot.material
        if material is None:
            report["mesh"]["materials"].append({"name": None, "issues": ["empty_material_slot"]})
            report["issues"].append({"severity": "error", "code": "empty_material_slot"})
            continue
        material_info = {
            "name": material.name,
            "is_f3d": bool(getattr(material, "is_f3d", False)),
            "use_nodes": bool(material.use_nodes),
            "images": [],
            "links": [],
        }
        if material.use_nodes and material.node_tree:
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE":
                    image_info = _image_node_report(node)
                    material_info["images"].append(image_info)
                    if image_info["image"] is None:
                        report["issues"].append({"severity": "error", "code": "image_node_without_image", "material": material.name, "node": node.name})
                    elif not image_info["exists"] and not image_info["packed"]:
                        report["issues"].append({"severity": "error", "code": "missing_image_file", "material": material.name, "image": image_info["image"]})
            for link in material.node_tree.links:
                material_info["links"].append({
                    "from": f"{link.from_node.name}.{link.from_socket.name}",
                    "to": f"{link.to_node.name}.{link.to_socket.name}",
                })
        report["mesh"]["materials"].append(material_info)
    for modifier in obj.modifiers:
        item = {"name": modifier.name, "type": modifier.type, "show_viewport": bool(modifier.show_viewport), "show_render": bool(modifier.show_render)}
        if modifier.type == "ARMATURE":
            armature = modifier.object
            item["armature"] = armature.name if armature else None
            if armature and armature.type == "ARMATURE":
                item["bones"] = [{
                    "name": bone.name,
                    "parent": bone.parent.name if bone.parent else None,
                    "deform": bool(bone.use_deform),
                } for bone in armature.data.bones]
                names = {bone.name for bone in armature.data.bones}
                item["groups_without_bones"] = sorted(group.name for group in obj.vertex_groups if group.name not in names)
                item["deform_bones_without_groups"] = sorted(
                    bone.name for bone in armature.data.bones if bone.use_deform and obj.vertex_groups.get(bone.name) is None
                )
                unweighted = 0
                multi = 0
                for vertex in mesh.vertices:
                    count = sum(1 for assignment in vertex.groups if assignment.weight > 1e-6)
                    unweighted += count == 0
                    multi += count > 1
                item["unweighted_vertices"] = unweighted
                item["multi_influence_vertices"] = multi
                if unweighted:
                    report["issues"].append({"severity": "error", "code": "unweighted_vertices", "count": unweighted})
            elif armature is None:
                report["issues"].append({"severity": "error", "code": "armature_modifier_has_no_target"})
        report["mesh"]["modifiers"].append(item)
    if not any(mod.type == "ARMATURE" for mod in obj.modifiers):
        report["issues"].append({"severity": "warning", "code": "mesh_has_no_armature_modifier"})
    return report


class BFAI_OT_diagnostics(bpy.types.Operator):
    bl_idname = "bfai.diagnostics"
    bl_label = "Check Fast64"

    def execute(self, context):
        loaded = [m for m in __import__("sys").modules if "fast64" in m.lower()]
        self.report({"INFO"}, "Fast64 modules: " + str(len(loaded)))
        return {"FINISHED"}


class BFAI_OT_inspect_active_asset(bpy.types.Operator):
    bl_idname = "bfai.inspect_active_asset"
    bl_label = "Inspect Active Asset"
    bl_description = "Trace the active object through mesh, UV, materials, images and armature references"

    def execute(self, context):
        report = _build_active_report(context.view_layer.objects.active)
        name = "BFAI_PIPELINE_REPORT.json"
        text_block = bpy.data.texts.get(name) or bpy.data.texts.new(name)
        text_block.clear()
        text_block.write(json.dumps(report, indent=2, ensure_ascii=False))
        errors = sum(1 for item in report.get("issues", []) if item["severity"] == "error")
        warnings = len(report.get("issues", [])) - errors
        self.report({"INFO"}, f"Report saved in Blender Text datablock: {errors} errors, {warnings} warnings")
        return {"FINISHED"}


class BFAI_PT_panel(bpy.types.Panel):
    bl_label = "AI Bridge"
    bl_idname = "BFAI_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AI Bridge"

    def draw(self, context):
        layout = self.layout
        layout.operator("bfai.inspect_active_asset", icon="VIEWZOOM")
        layout.operator("bfai.diagnostics", icon="PLUGIN")
        layout.label(text='Report: Text datablock "BFAI_PIPELINE_REPORT.json"')


classes = (BFAI_OT_diagnostics, BFAI_OT_inspect_active_asset, BFAI_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
