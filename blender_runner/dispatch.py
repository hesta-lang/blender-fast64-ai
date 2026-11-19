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

def safe_object(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    return obj

def fast64_modules():
    return [name for name in sys.modules if "fast64" in name.lower()]

def run(req):
    action, p = req["action"], req.get("params", {})
    workspace = Path(req["workspace"]).resolve()
    imports = (workspace / "imports").resolve()
    exports = (workspace / "exports").resolve()
    imports.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)

    if action == "status":
        return {"blender_version": bpy.app.version_string, "project": bpy.data.filepath or None, "fast64_loaded": bool(fast64_modules()), "fast64_modules": fast64_modules()[:40]}
    if action == "inspect_scene":
        return {"scene": bpy.context.scene.name, "objects": [{"name": o.name, "type": o.type, "vertices": len(o.data.vertices) if o.type == "MESH" else None, "polygons": len(o.data.polygons) if o.type == "MESH" else None} for o in bpy.context.scene.objects], "materials": [m.name for m in bpy.data.materials], "armatures": [o.name for o in bpy.data.objects if o.type == "ARMATURE"]}
    if action == "list_objects":
        return [{"name": o.name, "type": o.type} for o in bpy.context.scene.objects]
    if action == "rename_object":
        safe_object(p["old_name"]).name = p["new_name"]
        return {"renamed": p["old_name"], "to": p["new_name"]}
    if action == "set_object_transform":
        obj = safe_object(p["name"])
        if "location" in p: obj.location = p["location"]
        if "rotation" in p: obj.rotation_euler = p["rotation"]
        if "scale" in p: obj.scale = p["scale"]
        return {"name": obj.name, "location": list(obj.location), "rotation": list(obj.rotation_euler), "scale": list(obj.scale)}
    if action == "import_model":
        name = p["filename"]
        path = (imports / name).resolve()
        if path.parent != imports or not path.is_file(): raise ValueError("Import file not found or path is invalid")
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
        elif ext == ".ply": bpy.ops.import_mesh.ply(filepath=str(path))
        else: raise ValueError("Unsupported import format")
        return {"imported": name}
    if action == "fast64_diagnostics":
        modules = fast64_modules()
        ops = [x for x in dir(bpy.ops) if "fast64" in x.lower() or "sm64" in x.lower()]
        return {"loaded": bool(modules), "modules": modules[:100], "operator_namespaces": ops}
    if action == "fast64_export_operators":
        found = []
        for ns_name in dir(bpy.ops):
            try: ns = getattr(bpy.ops, ns_name)
            except Exception: continue
            for op_name in dir(ns):
                try:
                    op = getattr(ns, op_name)
                    rna = op.get_rna_type()
                    ident = getattr(rna, "identifier", "")
                    if ("fast64" in ident.lower() or "sm64" in ident.lower()) and ("export" in ident.lower()):
                        found.append({"namespace": ns_name, "operator": op_name, "identifier": ident})
                except Exception: pass
        return found[:100]
    if action == "save_project":
        target = workspace / "active.blend"
        if bpy.data.filepath:
            bpy.ops.wm.save_as_mainfile(filepath=str(target))
        else:
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
