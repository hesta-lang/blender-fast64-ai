"""Restricted Blender worker. Invoked only by server.blender_runner."""
import bpy
import json
import math
import os
import importlib
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


def fast64_ready():
    return hasattr(bpy.ops.object, "convert_bsdf") and hasattr(bpy.context.scene, "fast64")


def ensure_fast64_addon():
    """Load the official Fast64 addon in this Blender worker process."""
    if fast64_ready():
        return True
    addon_path = os.getenv("BFAI_FAST64_ADDON_PATH")
    if addon_path:
        package_dir = Path(addon_path).expanduser().resolve()
        if not (package_dir / "__init__.py").is_file():
            raise RuntimeError("BFAI_FAST64_ADDON_PATH must point to the Fast64 folder containing __init__.py")
        parent_dir = str(package_dir.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
    try:
        bpy.ops.preferences.addon_enable(module="fast64")
    except Exception:
        pass
    if not fast64_ready():
        try:
            addon = importlib.import_module("fast64")
            addon.register()
        except Exception as exc:
            raise RuntimeError(f"Could not load the Fast64 Blender addon: {exc}") from exc
    if not fast64_ready():
        raise RuntimeError("Fast64 did not register its Principled-to-F3D converter")
    return True


def try_enable_fast64():
    try:
        return {"loaded": bool(ensure_fast64_addon()), "error": None}
    except Exception as exc:
        return {"loaded": False, "error": str(exc)}


def load_workspace_project(workspace):
    project = workspace / "active.blend"
    if project.is_file():
        current = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
        if current != project.resolve():
            bpy.ops.wm.open_mainfile(filepath=str(project), load_ui=False)
    return project


def save_workspace_project(workspace):
    project = workspace / "active.blend"
    project.parent.mkdir(parents=True, exist_ok=True)
    try:
        bpy.context.preferences.filepaths.save_version = 1
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(filepath=str(project), check_existing=False)
    if not project.is_file():
        raise RuntimeError("Blender did not create active.blend")
    return str(project)


def _validate_sm64_binary_mesh(mesh, armature):
    group_names = {group.index: group.name for group in mesh.vertex_groups}
    deform_bones = {bone.name: bone for bone in armature.data.bones if bone.use_deform}
    used_bones = set()
    for vertex in mesh.data.vertices:
        influences = [
            (group_names.get(entry.group), float(entry.weight))
            for entry in vertex.groups
            if float(entry.weight) > 1e-5
        ]
        if len(influences) != 1:
            raise ValueError(
                f"SM64 binary skinning requires one bone influence per vertex; vertex {vertex.index} has {len(influences)}"
            )
        bone_name, weight = influences[0]
        if bone_name not in deform_bones:
            raise ValueError(f"Vertex {vertex.index} is assigned to a missing or non-deform bone: {bone_name}")
        if abs(weight - 1.0) > 1e-4:
            raise ValueError(f"Vertex {vertex.index} must have weight 1.0, not {weight}")
        used_bones.add(bone_name)
    if not used_bones:
        raise ValueError("The mesh has no SM64 deform-bone assignments")
    for bone_name in used_bones:
        if deform_bones[bone_name].parent is None:
            raise ValueError(
                f"SM64 skinning bone {bone_name} has no parent deform/geolayout node; add it below a parent bone"
            )
    return sorted(used_bones)



def safe_workspace_file(folder, filename):
    root = folder.resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError("File not found or path is invalid")
    return path


def _source_metadata(obj):
    keys = ("bfai_source_file", "bfai_source_format", "bfai_source_sha256", "bfai_imported_at", "bfai_pipeline_stage")
    return {key: obj.get(key) for key in keys if obj.get(key) is not None}


def _material_pipeline_report(material):
    if material is None:
        return {"name": None, "issues": ["empty_material_slot"]}
    report = {
        "name": material.name,
        "use_nodes": bool(material.use_nodes),
        "is_f3d": bool(getattr(material, "is_f3d", False)),
        "blend_method": getattr(material, "blend_method", None),
        "nodes": [],
        "links": [],
        "images": [],
        "surface_output_connected": False,
        "issues": [],
    }
    if not material.use_nodes or material.node_tree is None:
        report["issues"].append("material_has_no_node_tree")
        return report

    nodes = list(material.node_tree.nodes)
    links = list(material.node_tree.links)
    output_nodes = [node for node in nodes if node.type == "OUTPUT_MATERIAL"]
    upstream = set()
    pending = []
    for output in output_nodes:
        surface = output.inputs.get("Surface")
        if surface:
            report["surface_output_connected"] = bool(surface.is_linked)
            pending.extend(link.from_node for link in links if link.to_node == output and link.to_socket == surface)
    while pending:
        node = pending.pop()
        if node in upstream:
            continue
        upstream.add(node)
        for socket in node.inputs:
            pending.extend(link.from_node for link in links if link.to_node == node and link.to_socket == socket)

    for node in nodes:
        node_info = {"name": node.name, "type": node.type, "label": node.label or None}
        if node.type == "BSDF_PRINCIPLED":
            base = node.inputs.get("Base Color")
            if base and not base.is_linked:
                node_info["base_color"] = [float(value) for value in base.default_value]
            roughness = node.inputs.get("Roughness")
            if roughness and not roughness.is_linked:
                node_info["roughness"] = float(roughness.default_value)
        if node.type == "TEX_IMAGE":
            image = node.image
            if image is None:
                node_info["image"] = None
                report["issues"].append("image_texture_node_without_image:" + node.name)
            else:
                raw_path = image.filepath or ""
                absolute_path = bpy.path.abspath(raw_path) if raw_path else ""
                packed = bool(getattr(image, "packed_file", None) or getattr(image, "packed_files", None))
                exists = bool(absolute_path and Path(absolute_path).is_file())
                image_info = {
                    "name": image.name,
                    "filepath": raw_path,
                    "absolute_path": absolute_path or None,
                    "exists_on_disk": exists,
                    "packed": packed,
                    "source": image.source,
                    "size": [int(image.size[0]), int(image.size[1])],
                    "used_by_output": node in upstream,
                }
                node_info["image"] = image_info
                report["images"].append(image_info)
                if not exists and not packed and image.source == "FILE":
                    report["issues"].append("missing_image_file:" + image.name)
                if node not in upstream:
                    report["issues"].append("image_not_connected_to_surface:" + image.name)
        report["nodes"].append(node_info)

    for link in links:
        report["links"].append({
            "from_node": link.from_node.name,
            "from_socket": link.from_socket.name,
            "to_node": link.to_node.name,
            "to_socket": link.to_socket.name,
        })
    if not output_nodes:
        report["issues"].append("material_has_no_output_node")
    elif not report["surface_output_connected"]:
        report["issues"].append("material_surface_is_not_connected")
    if not report["images"]:
        report["issues"].append("material_has_no_image_texture")
    return report


def _diagnose_mesh_object(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    bounds = {
        "dimensions": [float(value) for value in obj.dimensions],
        "location": [float(value) for value in obj.location],
        "rotation_euler": [float(value) for value in obj.rotation_euler],
        "scale": [float(value) for value in obj.scale],
        "matrix_world": [[float(value) for value in row] for row in obj.matrix_world],
    }
    uv_layers = []
    for layer in mesh.uv_layers:
        values = [[float(loop.uv[0]), float(loop.uv[1])] for loop in layer.data]
        uv_layers.append({
            "name": layer.name,
            "loop_count": len(values),
            "non_finite_values": sum(1 for pair in values if not all(math.isfinite(v) for v in pair)),
            "minimum": [min((pair[i] for pair in values), default=None) for i in range(2)],
            "maximum": [max((pair[i] for pair in values), default=None) for i in range(2)],
        })

    materials = [_material_pipeline_report(slot.material) for slot in obj.material_slots]
    issues = []
    if not materials:
        issues.append({"severity": "error", "code": "mesh_has_no_material_slots", "message": "La malla no tiene ranuras de material."})
    for material in materials:
        for issue in material["issues"]:
            severity = "error" if issue.startswith("missing_image_file:") or issue in {
                "empty_material_slot", "material_has_no_output_node", "material_surface_is_not_connected"
            } else "warning"
            issues.append({"severity": severity, "code": issue, "material": material["name"]})
    if not uv_layers:
        issues.append({"severity": "warning", "code": "mesh_has_no_uv_map", "message": "No hay mapas UV; las texturas no podrán proyectarse correctamente."})
    if any(layer["non_finite_values"] for layer in uv_layers):
        issues.append({"severity": "error", "code": "uv_contains_non_finite_values"})
    degenerate_faces = sum(1 for polygon in mesh.polygons if not math.isfinite(float(polygon.area)) or float(polygon.area) <= 1e-12)
    non_finite_vertices = sum(1 for vertex in mesh.vertices if not all(math.isfinite(float(v)) for v in vertex.co))
    if degenerate_faces:
        issues.append({"severity": "warning", "code": "degenerate_faces", "count": degenerate_faces})
    if non_finite_vertices:
        issues.append({"severity": "error", "code": "non_finite_vertex_coordinates", "count": non_finite_vertices})

    armature_links = []
    for modifier in obj.modifiers:
        entry = {"name": modifier.name, "type": modifier.type, "show_viewport": bool(modifier.show_viewport), "show_render": bool(modifier.show_render)}
        if modifier.type == "ARMATURE":
            armature = modifier.object
            entry["armature"] = armature.name if armature else None
            if armature and armature.type == "ARMATURE":
                bones = list(armature.data.bones)
                bone_names = {bone.name for bone in bones}
                group_names = {group.name for group in obj.vertex_groups}
                deform_bones = [bone for bone in bones if bone.use_deform]
                counts = {name: 0 for name in group_names}
                unweighted_vertices = 0
                multi_influence_vertices = 0
                for vertex in mesh.vertices:
                    influences = [obj.vertex_groups[item.group].name for item in vertex.groups if item.weight > 1e-6 and item.group < len(obj.vertex_groups)]
                    if not influences:
                        unweighted_vertices += 1
                    if len(influences) > 1:
                        multi_influence_vertices += 1
                    for name in set(influences):
                        counts[name] = counts.get(name, 0) + 1
                missing_groups = sorted(name for name in group_names if name not in bone_names)
                missing_bone_groups = sorted(bone.name for bone in deform_bones if bone.name not in group_names)
                entry["rig"] = {
                    "name": armature.name,
                    "parent": armature.parent.name if armature.parent else None,
                    "bone_count": len(bones),
                    "bones": [{
                        "name": bone.name,
                        "parent": bone.parent.name if bone.parent else None,
                        "use_deform": bool(bone.use_deform),
                        "head_local": [float(v) for v in bone.head_local],
                        "tail_local": [float(v) for v in bone.tail_local],
                    } for bone in bones],
                    "vertex_group_vertex_counts": counts,
                    "vertex_count": len(mesh.vertices),
                    "unweighted_vertices": unweighted_vertices,
                    "multi_influence_vertices": multi_influence_vertices,
                    "groups_without_matching_bones": missing_groups,
                    "deform_bones_without_groups": missing_bone_groups,
                }
                if unweighted_vertices:
                    issues.append({"severity": "error", "code": "unweighted_vertices", "count": unweighted_vertices, "armature": armature.name})
                if missing_groups:
                    issues.append({"severity": "error", "code": "vertex_groups_without_bones", "names": missing_groups})
                if missing_bone_groups:
                    issues.append({"severity": "warning", "code": "deform_bones_without_vertex_groups", "names": missing_bone_groups})
                if not modifier.show_viewport:
                    issues.append({"severity": "warning", "code": "armature_modifier_disabled_in_viewport", "modifier": modifier.name})
                if not modifier.show_render:
                    issues.append({"severity": "warning", "code": "armature_modifier_disabled_in_render", "modifier": modifier.name})
            elif armature is None:
                issues.append({"severity": "error", "code": "armature_modifier_has_no_target", "modifier": modifier.name})
        armature_links.append(entry)

    if not armature_links or not any(item["type"] == "ARMATURE" for item in armature_links):
        issues.append({"severity": "warning", "code": "mesh_has_no_armature_modifier"})
    return {
        "name": obj.name,
        "type": obj.type,
        "data_name": mesh.name,
        "topology": {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
            "triangles": len(mesh.loop_triangles),
            "degenerate_faces": degenerate_faces,
            "non_finite_vertices": non_finite_vertices,
        },
        "transform": bounds,
        "parent": obj.parent.name if obj.parent else None,
        "children": [child.name for child in obj.children],
        "collections": sorted(collection.name for collection in obj.users_collection),
        "uv_layers": uv_layers,
        "materials": materials,
        "vertex_groups": [group.name for group in obj.vertex_groups],
        "modifiers": armature_links,
        "source": _source_metadata(obj),
        "issues": issues,
    }


def _sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        addon = sys.modules.get("fast64")
        version = (addon.bl_info.get("version") if addon and hasattr(addon, "bl_info") else None)
        return {"blender_version": bpy.app.version_string, "project": bpy.data.filepath or None, "fast64_loaded": bool(modules or enabled or fast64_ready()), "fast64_version": version, "fast64_modules": modules[:40], "fast64_enabled_addons": enabled}

    if action == "inspect_scene":
        return {
            "scene": bpy.context.scene.name,
            "objects": [{"name": o.name, "type": o.type, "vertices": len(o.data.vertices) if o.type == "MESH" else None, "polygons": len(o.data.polygons) if o.type == "MESH" else None, "materials": [m.name if m else None for m in o.data.materials] if o.type == "MESH" else []} for o in bpy.context.scene.objects],
            "materials": [m.name for m in bpy.data.materials],
            "images": [img.name for img in bpy.data.images],
            "armatures": [{"name": o.name, "bones": [b.name for b in o.data.bones]} for o in bpy.data.objects if o.type == "ARMATURE"],
        }

    if action == "inspect_asset_pipeline":
        requested = p.get("object_name")
        if requested:
            target = safe_object(requested)
            targets = [target] if target.type == "MESH" else [child for child in target.children_recursive if child.type == "MESH"]
            if target.type == "MESH":
                pass
            elif not targets:
                raise ValueError(f"Object {requested} is not a mesh and has no mesh descendants")
        else:
            targets = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"][:100]
        object_reports = [_diagnose_mesh_object(obj) for obj in targets]
        issue_counts = {}
        for report in object_reports:
            for issue in report["issues"]:
                key = issue["severity"] + ":" + issue["code"]
                issue_counts[key] = issue_counts.get(key, 0) + 1
        world = bpy.context.scene.world
        return {
            "schema_version": 1,
            "project": bpy.data.filepath or None,
            "blender_version": bpy.app.version_string,
            "scene": {
                "name": bpy.context.scene.name,
                "frame": int(bpy.context.scene.frame_current),
                "render_engine": bpy.context.scene.render.engine,
                "active_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
                "resolution": [int(bpy.context.scene.render.resolution_x), int(bpy.context.scene.render.resolution_y)],
                "world": {
                    "name": world.name if world else None,
                    "use_nodes": bool(world and world.use_nodes),
                    "color": [float(v) for v in world.color] if world else None,
                },
            },
            "summary": {
                "objects_inspected": len(object_reports),
                "mesh_objects_in_scene": sum(1 for obj in bpy.context.scene.objects if obj.type == "MESH"),
                "materials_in_file": len(bpy.data.materials),
                "images_in_file": len(bpy.data.images),
                "armatures_in_scene": sum(1 for obj in bpy.context.scene.objects if obj.type == "ARMATURE"),
                "issue_counts": issue_counts,
            },
            "objects": object_reports,
            "notes": [
                "Este informe sigue malla -> UV/material -> nodos -> imágenes y malla -> modificador -> armature -> grupos de vértices.",
                "Los avisos identifican señales técnicas; no sustituyen una revisión visual del render final.",
                "Los materiales F3D y el render de SM64 pueden diferir del aspecto de Blender Material Preview.",
            ],
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
        before = {obj.as_pointer() for obj in bpy.context.scene.objects}
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
        imported = [obj for obj in bpy.context.scene.objects if obj.as_pointer() not in before]
        source_hash = _sha256_file(path)
        imported_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        for obj in imported:
            obj["bfai_source_file"] = name
            obj["bfai_source_format"] = ext.lstrip(".")
            obj["bfai_source_sha256"] = source_hash
            obj["bfai_imported_at"] = imported_at
            obj["bfai_pipeline_stage"] = "blender_import"
        return {
            "imported": name,
            "source_sha256": source_hash,
            "objects": [obj.name for obj in imported],
            "tagged_objects": len(imported),
            "provenance": "bfai_source_* custom properties",
        }

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

    if action == "convert_materials_to_f3d":
        ensure_fast64_addon()
        obj = safe_object(p["mesh_name"], "MESH")
        scene = bpy.context.scene
        old_convert_all = scene.bsdf_conv_all
        old_rename_uvs = scene.rename_uv_maps
        old_active = bpy.context.view_layer.objects.active
        old_selected = list(bpy.context.selected_objects)
        try:
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            scene.bsdf_conv_all = False
            scene.rename_uv_maps = bool(p.get("rename_uv_maps", True))
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            result = bpy.ops.object.convert_bsdf()
            if "FINISHED" not in result:
                raise RuntimeError(f"Fast64 Principled-to-F3D conversion did not finish: {sorted(result)}")
        finally:
            scene.bsdf_conv_all = old_convert_all
            scene.rename_uv_maps = old_rename_uvs
            _restore_selection(old_active, old_selected)
        materials = [slot.material for slot in obj.material_slots]
        not_converted = [mat.name if mat else "<empty>" for mat in materials if mat is None or not getattr(mat, "is_f3d", False)]
        if not materials or not_converted:
            raise RuntimeError("Fast64 conversion completed without producing F3D materials for every material slot: " + ", ".join(not_converted))
        return {
            "object": obj.name,
            "converted_materials": [mat.name for mat in materials],
            "f3d_versions": [getattr(mat, "mat_ver", None) for mat in materials],
            "native_f3d": True,
        }

    if action == "sm64_skinning_context":
        mesh = safe_object(p["mesh_name"], "MESH")
        armature = safe_object(p["armature_name"], "ARMATURE")
        return {
            "vertex_count": len(mesh.data.vertices),
            "deform_bones": [bone.name for bone in armature.data.bones if bone.use_deform],
        }

    if action == "set_sm64_binary_skinning":
        mesh = safe_object(p["mesh_name"], "MESH")
        armature = safe_object(p["armature_name"], "ARMATURE")
        deform_bones = {bone.name for bone in armature.data.bones if bone.use_deform}
        if len(p["assignments"]) != len(mesh.data.vertices):
            raise ValueError("SM64 requires exactly one bone assignment per mesh vertex")
        by_bone = {}
        seen = set()
        for item in p["assignments"]:
            vertex_index, bone_name = item["vertex"], item["bone"]
            if vertex_index in seen or not 0 <= vertex_index < len(mesh.data.vertices):
                raise ValueError("duplicate or out-of-range SM64 vertex assignment")
            if bone_name not in deform_bones:
                raise ValueError(f"Unknown or non-deform SM64 bone: {bone_name}")
            seen.add(vertex_index)
            by_bone.setdefault(bone_name, []).append(vertex_index)
        if len(seen) != len(mesh.data.vertices):
            raise ValueError("Every mesh vertex must be assigned to exactly one deform bone")
        for group in list(mesh.vertex_groups):
            mesh.vertex_groups.remove(group)
        for bone_name, indices in by_bone.items():
            group = mesh.vertex_groups.new(name=bone_name)
            group.add(indices, 1.0, "REPLACE")
        old_world = mesh.matrix_world.copy()
        mesh.parent = armature
        mesh.matrix_world = old_world
        modifier = next((mod for mod in mesh.modifiers if mod.type == "ARMATURE"), None)
        if modifier is None:
            modifier = mesh.modifiers.new(name="SM64 Armature", type="ARMATURE")
        modifier.object = armature
        return {
            "mesh": mesh.name,
            "armature": armature.name,
            "vertices": len(mesh.data.vertices),
            "binary_skinning": True,
            "bone_assignments": {name: len(indices) for name, indices in by_bone.items()},
        }

    if action == "export_sm64_armature":
        ensure_fast64_addon()
        armature = safe_object(p["armature_name"], "ARMATURE")
        mesh_children = [child for child in armature.children if child.type == "MESH"]
        if len(mesh_children) != 1:
            raise ValueError(f"Fast64 SM64 armature export requires exactly one mesh child; found {len(mesh_children)}")
        mesh = mesh_children[0]
        materials = [slot.material for slot in mesh.material_slots]
        if not materials or any(mat is None or not getattr(mat, "is_f3d", False) for mat in materials):
            raise ValueError("Convert every mesh material to a native Fast64 F3D material before exporting")
        used_bones = _validate_sm64_binary_mesh(mesh, armature)
        root_bones = [bone for bone in armature.data.bones if bone.parent is None]
        if len(root_bones) != 1:
            raise ValueError(f"SM64 armature export requires exactly one root bone; found {len(root_bones)}")
        root = root_bones[0]
        if not hasattr(root, "geo_cmd"):
            raise RuntimeError("Fast64 geolayout bone properties are not registered")
        previous_root_command = root.geo_cmd
        output_root = exports / p["output_folder"]
        if output_root.exists() and any(output_root.iterdir()):
            raise ValueError("Export folder already contains files; choose a new output_folder to avoid overwriting")
        output_root.mkdir(parents=True, exist_ok=True)
        scene = bpy.context.scene
        if not hasattr(scene, "fast64") or not hasattr(scene.fast64, "sm64"):
            raise RuntimeError("Fast64 SM64 scene properties are not registered")
        sm64_props = scene.fast64.sm64
        combined = sm64_props.combined_export
        previous_scene_values = {
            "export_type": sm64_props.export_type,
            "export_header_type": combined.export_header_type,
            "custom_export_path": combined.custom_export_path,
            "export_gfx": combined.export_gfx,
            "export_col": combined.export_col,
            "export_anim": combined.export_anim,
            "export_all_selected": combined.export_all_selected,
            "graphics_object": combined.graphics_object,
            "object_name": combined.object_name,
            "use_name_filtering": combined.use_name_filtering,
            "saveTextures": scene.saveTextures,
        }
        old_active = bpy.context.view_layer.objects.active
        old_selected = list(bpy.context.selected_objects)
        export_succeeded = False
        try:
            # Fast64's Bone.geo_cmd update callback inspects context.object and
            # creates Armature bone collections. Set the armature active before
            # changing the root command; otherwise the callback receives the mesh.
            bpy.ops.object.select_all(action="DESELECT")
            armature.select_set(True)
            bpy.context.view_layer.objects.active = armature
            root.geo_cmd = "Start"
            if hasattr(scene, "gameEditorMode"):
                try:
                    scene.gameEditorMode = "SM64"
                except Exception:
                    pass
            sm64_props.export_type = "C"
            combined.export_header_type = "Custom"
            combined.custom_export_path = str(output_root)
            combined.export_gfx = True
            combined.export_col = False
            combined.export_anim = False
            combined.export_all_selected = False
            combined.graphics_object = mesh
            combined.object_name = p.get("object_name") or mesh.name
            combined.use_name_filtering = False
            scene.saveTextures = bool(p.get("save_textures", True))
            result = bpy.ops.object.sm64_export_geolayout_armature(export_obj=armature.name)
            if "FINISHED" not in result:
                raise RuntimeError(f"Fast64 SM64 geolayout exporter did not finish: {sorted(result)}")
            export_succeeded = True
        finally:
            if not export_succeeded:
                root.geo_cmd = previous_root_command
            sm64_props.export_type = previous_scene_values["export_type"]
            combined.export_header_type = previous_scene_values["export_header_type"]
            combined.custom_export_path = previous_scene_values["custom_export_path"]
            combined.export_gfx = previous_scene_values["export_gfx"]
            combined.export_col = previous_scene_values["export_col"]
            combined.export_anim = previous_scene_values["export_anim"]
            combined.export_all_selected = previous_scene_values["export_all_selected"]
            combined.graphics_object = previous_scene_values["graphics_object"]
            combined.object_name = previous_scene_values["object_name"]
            combined.use_name_filtering = previous_scene_values["use_name_filtering"]
            scene.saveTextures = previous_scene_values["saveTextures"]
            _restore_selection(old_active, old_selected)
        files = sorted(path for path in output_root.rglob("*") if path.is_file())
        if not files:
            raise RuntimeError("Fast64 returned FINISHED but generated no files in the selected output folder")
        source = _source_metadata(mesh)
        if not source:
            source = _source_metadata(armature)
        manifest_path = output_root / "bfai_export_manifest.json"
        manifest = {
            "schema_version": 1,
            "exported_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "blender_version": bpy.app.version_string,
            "export_format": "Fast64 SM64 C geolayout",
            "source": source,
            "objects": {
                "mesh": mesh.name,
                "armature": armature.name,
                "mesh_data": mesh.data.name,
                "vertices": len(mesh.data.vertices),
                "polygons": len(mesh.data.polygons),
                "uv_layers": [layer.name for layer in mesh.data.uv_layers],
                "materials": [mat.name for mat in materials],
                "bones": [{
                    "name": bone.name,
                    "parent": bone.parent.name if bone.parent else None,
                    "use_deform": bool(bone.use_deform),
                } for bone in armature.data.bones],
                "binary_skinning_bones": used_bones,
            },
            "files": [{
                "path": str(path.relative_to(output_root)),
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            } for path in files],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        files = sorted(path for path in output_root.rglob("*") if path.is_file())
        return {
            "armature": armature.name,
            "mesh": mesh.name,
            "export_format": "Fast64 SM64 C geolayout",
            "export_folder": str(output_root),
            "files": [str(path.relative_to(output_root)) for path in files],
            "manifest": str(manifest_path),
            "binary_skinning_bones": used_bones,
            "native_f3d_materials": [mat.name for mat in materials],
        }

    if action == "fast64_diagnostics":
        modules = fast64_modules()
        enabled = [name for name in bpy.context.preferences.addons.keys() if "fast64" in name.lower()]
        ops = [x for x in dir(bpy.ops) if "fast64" in x.lower() or "sm64" in x.lower() or x.lower() in {"f3d", "oot", "z64"}]
        addon = sys.modules.get("fast64")
        version = addon.bl_info.get("version") if addon and hasattr(addon, "bl_info") else None
        return {"loaded": bool(modules or enabled or fast64_ready()), "version": version, "modules": modules[:100], "enabled_addons": enabled, "operator_namespaces": ops}

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


MUTATING_ACTIONS = {
    "rename_object",
    "set_object_transform",
    "import_model",
    "create_mesh_object",
    "create_armature",
    "bind_mesh_to_armature",
    "set_vertex_weights",
    "set_sm64_binary_skinning",
    "create_material",
    "assign_material",
    "smart_uv_unwrap",
    "convert_materials_to_f3d",
    "export_sm64_armature",
}


def main():
    try:
        args = sys.argv[sys.argv.index("--") + 1:]
        req = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        workspace = Path(req["workspace"]).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "imports").mkdir(parents=True, exist_ok=True)
        (workspace / "exports").mkdir(parents=True, exist_ok=True)

        action = req.get("action")
        if os.getenv("BFAI_FAST64_ADDON_PATH") or action in {
            "fast64_diagnostics", "convert_materials_to_f3d",
            "set_sm64_binary_skinning", "sm64_skinning_context",
            "export_sm64_armature", "fast64_export_operators", "fast64_run_export",
        }:
            try_enable_fast64()

        load_workspace_project(workspace)
        result = run(req)
        if action in MUTATING_ACTIONS:
            save_workspace_project(workspace)
        emit(result)
    except Exception as exc:
        emit(error=f"{exc}\n{traceback.format_exc()[-5000:]}")


if __name__ == "__main__":
    main()
