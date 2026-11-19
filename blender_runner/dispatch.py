"""Restricted Blender worker. Invoked only by server.blender_runner."""
import bpy
import json
import math
import os
import sys
import traceback
from pathlib import Path


def emit(data=None, error=None):
    print("BFAI_RESULT:" + json.dumps({"ok": error is None, "data": data, "error": error}, ensure_ascii=False))


def safe_object(name, expected_type=None):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    if expected_type and obj.type != expected_type:
        raise ValueError(f"Object {name} must be type {expected_type}")
    return obj


def fast64_modules():
    return [name for name in sys.modules if "fast64" in name.lower()]


def safe_workspace_file(folder, filename):
    root = folder.resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError("File not found or path is invalid")
    return path


def _operator_catalog():
    found = []
    for ns_name in dir(bpy.ops):
        try:
            namespace = getattr(bpy.ops, ns_name)
        except Exception:
            continue
        for op_name in dir(namespace):
            try:
                operator = getattr(namespace, op_name)
                rna = operator.get_rna_type()
                identifier = getattr(rna, "identifier", "")
                searchable = f"{ns_name}.{op_name}.{identifier}".lower()
                if "export" not in searchable or not ("fast64" in searchable or "sm64" in searchable or ns_name.lower() in {"f3d", "oot", "z64"}):
                    continue
                props = []
                for prop in rna.properties:
                    if prop.identifier == "rna_type":
                        continue
                    item = {"name": prop.identifier, "type": prop.type, "description": prop.description}
                    if hasattr(prop, "is_readonly"):
                        item["read_only"] = bool(prop.is_readonly)
                    if prop.type == "ENUM":
                        try:
                            item["enum_items"] = [entry.identifier for entry in prop.enum_items]
                        except Exception:
                            item["enum_items"] = []
                    if prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING"}:
                        try:
                            default = prop.default
                            if isinstance(default, (str, int, float, bool)):
                                item["default"] = default
                        except Exception:
                            pass
                    props.append(item)
                found.append({"namespace": ns_name, "operator": op_name, "identifier": identifier, "properties": props})
            except Exception:
                continue
    return found[:150]


def _property_value_ok(prop, value):
    if getattr(prop, "is_array", False) and prop.type in {"INT", "FLOAT"}:
        if not isinstance(value, (list, tuple)) or len(value) != prop.array_length:
            return False
        if prop.type == "INT":
            return all(isinstance(item, int) and not isinstance(item, bool) for item in value)
        return all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item)) for item in value)
    if prop.type == "BOOLEAN":
        return isinstance(value, bool)
    if prop.type == "INT":
        return isinstance(value, int) and not isinstance(value, bool)
    if prop.type == "FLOAT":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    if prop.type == "STRING":
        return isinstance(value, str) and len(value) <= 4096
    if prop.type == "ENUM":
        try:
            return isinstance(value, str) and value in {entry.identifier for entry in prop.enum_items}
        except Exception:
            return False
    return False


def _safe_export_property(prop, value, exports):
    if prop.type == "STRING" and any(token in prop.identifier.lower() for token in ("path", "directory", "folder")) and value:
        raw = Path(value)
        target = (exports / raw).resolve() if not raw.is_absolute() else raw.resolve()
        if target != exports.resolve() and exports.resolve() not in target.parents:
            raise ValueError(f"Export path property {prop.identifier} must stay inside workspace/exports")
        if "directory" in prop.identifier.lower() or "folder" in prop.identifier.lower():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        return str(target)
    if getattr(prop, "is_array", False) and prop.type in {"FLOAT", "INT"}:
        if not isinstance(value, (list, tuple)) or len(value) != prop.array_length:
            raise ValueError(f"invalid array property: {prop.identifier}")
        if prop.type == "FLOAT" and any(not math.isfinite(float(x)) for x in value):
            raise ValueError(f"non-finite array property: {prop.identifier}")
        if prop.type == "INT" and any(isinstance(x, bool) or not isinstance(x, int) for x in value):
            raise ValueError(f"invalid integer array property: {prop.identifier}")
        return list(value)
    if not _property_value_ok(prop, value):
        raise ValueError(f"invalid value for Fast64 operator property: {prop.identifier}")
    return value


def _restore_selection(active, selected):
    try:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in selected:
            if obj and obj.name in bpy.data.objects:
                obj.select_set(True)
        if active and active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = active
    except Exception:
        pass


def run(req):
    action, p = req["action"], req.get("params", {})
    workspace = Path(req["workspace"]).resolve()
    imports = (workspace / "imports").resolve()
    exports = (workspace / "exports").resolve()
    imports.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)

    if action == "status":
        enabled = [name for name in bpy.context.preferences.addons.keys() if "fast64" in name.lower()]
        modules = fast64_modules()
        return {"blender_version": bpy.app.version_string, "project": bpy.data.filepath or None, "fast64_loaded": bool(modules or enabled), "fast64_modules": modules[:40], "fast64_enabled_addons": enabled}

    if action == "inspect_scene":
        return {
            "scene": bpy.context.scene.name,
            "objects": [{"name": o.name, "type": o.type, "vertices": len(o.data.vertices) if o.type == "MESH" else None, "polygons": len(o.data.polygons) if o.type == "MESH" else None, "materials": [m.name if m else None for m in o.data.materials] if o.type == "MESH" else []} for o in bpy.context.scene.objects],
            "materials": [m.name for m in bpy.data.materials],
            "images": [img.name for img in bpy.data.images],
            "armatures": [{"name": o.name, "bones": [b.name for b in o.data.bones]} for o in bpy.data.objects if o.type == "ARMATURE"],
        }

    if action == "list_objects":
        return [{"name": o.name, "type": o.type} for o in bpy.context.scene.objects]

    if action == "rename_object":
        old_name, new_name = p["old_name"], p["new_name"]
        safe_object(old_name).name = new_name
        return {"renamed": old_name, "to": new_name}

    if action == "set_object_transform":
        obj = safe_object(p["name"])
        if "location" in p: obj.location = p["location"]
        if "rotation" in p: obj.rotation_euler = p["rotation"]
        if "scale" in p: obj.scale = p["scale"]
        return {"name": obj.name, "location": list(obj.location), "rotation": list(obj.rotation_euler), "scale": list(obj.scale)}

    if action == "import_model":
        name = p["filename"]
        path = safe_workspace_file(imports, name)
        ext = path.suffix.lower()
        if ext == ".blend":
            with bpy.data.libraries.load(str(path), link=False) as (src, dst): dst.objects = list(src.objects)
            for obj in dst.objects:
                if obj: bpy.context.scene.collection.objects.link(obj)
        elif ext == ".fbx": bpy.ops.import_scene.fbx(filepath=str(path))
        elif ext == ".obj":
            if hasattr(bpy.ops.wm, "obj_import"): bpy.ops.wm.obj_import(filepath=str(path))
            else: bpy.ops.import_scene.obj(filepath=str(path))
        elif ext in {".glb", ".gltf"}: bpy.ops.import_scene.gltf(filepath=str(path))
        elif ext == ".stl": bpy.ops.import_mesh.stl(filepath=str(path))
        elif ext == ".ply":
            if hasattr(bpy.ops.wm, "ply_import"): bpy.ops.wm.ply_import(filepath=str(path))
            else: bpy.ops.import_mesh.ply(filepath=str(path))
        else:
            raise ValueError("Unsupported import format")
        return {"imported": name}

    if action == "create_mesh_object":
        mesh = bpy.data.meshes.new(p["name"] + "Mesh")
        mesh.from_pydata(p["vertices"], [], p["faces"])
        mesh.validate(verbose=False, clean_customdata=True)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(p["name"], mesh)
        bpy.context.scene.collection.objects.link(obj)
        return {"created": obj.name, "vertices": len(mesh.vertices), "faces": len(mesh.polygons)}

    if action == "create_armature":
        arm_data = bpy.data.armatures.new(p["name"] + "Data")
        arm_obj = bpy.data.objects.new(p["name"], arm_data)
        bpy.context.scene.collection.objects.link(arm_obj)
        old_active = bpy.context.view_layer.objects.active
        old_selected = list(bpy.context.selected_objects)
        try:
            bpy.ops.object.select_all(action="DESELECT")
            arm_obj.select_set(True)
            bpy.context.view_layer.objects.active = arm_obj
            bpy.ops.object.mode_set(mode="EDIT")
            edit_bones = {}
            for spec in p["bones"]:
                bone = arm_data.edit_bones.new(spec["name"])
                bone.head = spec["head"]
                bone.tail = spec["tail"]
                bone.use_deform = spec["use_deform"]
                edit_bones[spec["name"]] = bone
            for spec in p["bones"]:
                if spec["parent"]:
                    edit_bones[spec["name"]].parent = edit_bones[spec["parent"]]
                    edit_bones[spec["name"]].use_connect = bool(spec["use_connect"])
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            if arm_obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            bpy.data.objects.remove(arm_obj, do_unlink=True)
            raise
        finally:
            _restore_selection(old_active, old_selected)
        return {"created": arm_obj.name, "bones": [bone.name for bone in arm_data.bones]}

    if action == "weight_context":
        mesh = safe_object(p["mesh_name"], "MESH")
        armature = safe_object(p["armature_name"], "ARMATURE")
        deform_bones = [bone.name for bone in armature.data.bones if bone.use_deform]
        return {"bones": deform_bones, "vertex_count": len(mesh.data.vertices)}

    if action == "bind_mesh_to_armature":
        mesh = safe_object(p["mesh_name"], "MESH")
        armature = safe_object(p["armature_name"], "ARMATURE")
        old_active = bpy.context.view_layer.objects.active
        old_selected = list(bpy.context.selected_objects)
        try:
            bpy.ops.object.select_all(action="DESELECT")
            mesh.select_set(True)
            armature.select_set(True)
            bpy.context.view_layer.objects.active = armature
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        finally:
            _restore_selection(old_active, old_selected)
        return {"mesh": mesh.name, "armature": armature.name, "parented": mesh.parent == armature, "vertex_groups": [group.name for group in mesh.vertex_groups]}

    if action == "set_vertex_weights":
        mesh = safe_object(p["mesh_name"], "MESH")
        armature = safe_object(p["armature_name"], "ARMATURE")
        bone_names = {bone.name for bone in armature.data.bones if bone.use_deform}
        grouped = {}
        for item in p["weights"]:
            if item["bone"] not in bone_names:
                raise ValueError(f"Unknown deform bone: {item['bone']}")
            if item["vertex"] >= len(mesh.data.vertices):
                raise ValueError("Weight vertex index out of range")
            grouped.setdefault(item["bone"], []).append((item["vertex"], item["weight"]))
        for bone_name, entries in grouped.items():
            group = mesh.vertex_groups.get(bone_name) or mesh.vertex_groups.new(name=bone_name)
            for vertex_index, weight in entries:
                group.add([vertex_index], weight, "REPLACE")
        modifier = next((m for m in mesh.modifiers if m.type == "ARMATURE" and m.object == armature), None)
        if modifier is None:
            modifier = mesh.modifiers.new(name=armature.name, type="ARMATURE")
            modifier.object = armature
        if mesh.parent != armature:
            mesh.parent = armature
        return {"mesh": mesh.name, "armature": armature.name, "weighted_vertices": len(p["weights"]), "vertex_groups": [group.name for group in mesh.vertex_groups]}

    if action == "create_material":
        name = p["name"]
        material = bpy.data.materials.get(name) or bpy.data.materials.new(name=name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
        if principled is None:
            principled = nodes.new("ShaderNodeBsdfPrincipled")
        output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
        if output is None:
            output = nodes.new("ShaderNodeOutputMaterial")
        for link in list(material.node_tree.links):
            if link.to_node == principled and (link.to_socket == principled.inputs["Base Color"] or link.to_socket == principled.inputs["Alpha"]):
                material.node_tree.links.remove(link)
            if link.to_node == output and link.to_socket == output.inputs["Surface"]:
                material.node_tree.links.remove(link)
        material.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
        principled.inputs["Base Color"].default_value = p["base_color"]
        principled.inputs["Metallic"].default_value = p["metallic"]
        principled.inputs["Roughness"].default_value = p["roughness"]
        texture_name = p.get("texture_filename")
        if texture_name:
            image_path = safe_workspace_file(imports, texture_name)
            image = bpy.data.images.load(str(image_path), check_existing=True)
            texture = next((node for node in nodes if node.type == "TEX_IMAGE" and node.image == image), None)
            if texture is None:
                texture = nodes.new("ShaderNodeTexImage")
            texture.image = image
            material.node_tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
            if "Alpha" in principled.inputs:
                material.node_tree.links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
        if p.get("assign_to_object"):
            obj = safe_object(p["assign_to_object"])
            if obj.type != "MESH":
                raise ValueError("Materials can only be assigned to mesh objects in this operation")
            if len(obj.data.materials): obj.data.materials[0] = material
            else: obj.data.materials.append(material)
        return {"material": material.name, "texture": texture_name, "assigned_to": p.get("assign_to_object")}

    if action == "assign_material":
        obj = safe_object(p["object_name"], "MESH")
        material = bpy.data.materials.get(p["material_name"])
        if material is None:
            raise ValueError(f"Material not found: {p['material_name']}")
        if len(obj.data.materials): obj.data.materials[0] = material
        else: obj.data.materials.append(material)
        return {"object": obj.name, "material": material.name}

    if action == "smart_uv_unwrap":
        obj = safe_object(p["mesh_name"], "MESH")
        old_active = bpy.context.view_layer.objects.active
        old_selected = list(bpy.context.selected_objects)
        try:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            if not obj.data.uv_layers:
                obj.data.uv_layers.new(name="UVMap")
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project()
            bpy.ops.object.mode_set(mode="OBJECT")
        finally:
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            _restore_selection(old_active, old_selected)
        return {"object": obj.name, "uv_layers": [layer.name for layer in obj.data.uv_layers]}

    if action == "fast64_diagnostics":
        modules = fast64_modules()
        enabled = [name for name in bpy.context.preferences.addons.keys() if "fast64" in name.lower()]
        ops = [x for x in dir(bpy.ops) if "fast64" in x.lower() or "sm64" in x.lower() or x.lower() in {"f3d", "oot", "z64"}]
        return {"loaded": bool(modules or enabled), "modules": modules[:100], "enabled_addons": enabled, "operator_namespaces": ops}

    if action == "fast64_export_operators":
        return _operator_catalog()

    if action == "fast64_run_export":
        requested = p["operator_identifier"]
        catalog = _operator_catalog()
        match = next((entry for entry in catalog if entry["identifier"] == requested), None)
        if match is None:
            raise ValueError("Operator is not a currently registered Fast64 export operator")
        namespace = getattr(bpy.ops, match["namespace"])
        operator = getattr(namespace, match["operator"])
        rna = operator.get_rna_type()
        prop_defs = {prop.identifier: prop for prop in rna.properties if prop.identifier != "rna_type"}
        kwargs = {}
        for key, value in p.get("properties", {}).items():
            if key not in prop_defs:
                raise ValueError(f"Unknown operator property: {key}")
            prop = prop_defs[key]
            if getattr(prop, "is_readonly", False):
                raise ValueError(f"Operator property is read-only: {key}")
            kwargs[key] = _safe_export_property(prop, value, exports)
        old_active = bpy.context.view_layer.objects.active
        old_selected = list(bpy.context.selected_objects)
        try:
            result = operator(**kwargs)
        finally:
            _restore_selection(old_active, old_selected)
        return {"operator": requested, "status": sorted(result), "properties": kwargs, "export_directory": str(exports)}

    if action == "save_project":
        target = workspace / "active.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(target))
        return {"saved": str(target)}

    raise ValueError(f"Unsupported action: {action}")


def main():
    try:
        args = sys.argv[sys.argv.index("--") + 1:]
        req = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        emit(run(req))
    except Exception as exc:
        emit(error=f"{exc}\n{traceback.format_exc()[-3000:]}")


if __name__ == "__main__":
    main()
