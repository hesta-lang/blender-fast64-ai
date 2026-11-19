"""Input validation shared by the MCP API and Blender worker."""
import math
import os
import re

ALLOWED_IMPORTS = {".blend", ".fbx", ".obj", ".glb", ".gltf", ".stl", ".ply"}
ALLOWED_TEXTURES = {".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp", ".exr"}
MAX_VERTICES = 50000
MAX_FACES = 50000
MAX_BONES = 512
MAX_WEIGHTS = 500000


def finite_vector(value, size=3, label="vector"):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{label} must contain {size} numbers")
    if any(isinstance(v, bool) for v in value):
        raise ValueError(f"{label} must contain numbers, not booleans")
    try:
        result = [float(v) for v in value]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must contain numbers") from exc
    if not all(math.isfinite(v) for v in result):
        raise ValueError(f"{label} contains a non-finite number")
    return result


def safe_name(value, label="name"):
    if not isinstance(value, str) or not value.strip() or len(value) > 96:
        raise ValueError(f"invalid {label}")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {label}")
    return value.strip()


def safe_filename(value, allowed=ALLOWED_IMPORTS):
    if not isinstance(value, str) or os.path.basename(value) != value or value in {"", ".", ".."}:
        raise ValueError("filename must be a plain file name")
    if not re.fullmatch(r"[A-Za-z0-9_. -]{1,120}", value):
        raise ValueError("filename contains unsupported characters")
    if os.path.splitext(value)[1].lower() not in allowed:
        raise ValueError("file extension is not allowed")
    return value


def safe_texture_filename(value):
    return safe_filename(value, ALLOWED_TEXTURES)


def validate_mesh_data(vertices, faces):
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= MAX_VERTICES:
        raise ValueError(f"vertices must contain 3..{MAX_VERTICES} points")
    points = [finite_vector(v, 3, "vertex") for v in vertices]
    if not isinstance(faces, list) or not 1 <= len(faces) <= MAX_FACES:
        raise ValueError(f"faces must contain 1..{MAX_FACES} polygons")
    polygons = []
    for face in faces:
        if not isinstance(face, list) or not 3 <= len(face) <= 64:
            raise ValueError("each face must contain 3..64 indices")
        if any(isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(points) for i in face):
            raise ValueError("face index out of range")
        if len(set(face)) < 3:
            raise ValueError("each face must reference at least three different vertices")
        polygons.append(list(face))
    return points, polygons


def validate_bones(bones):
    if not isinstance(bones, list) or not 1 <= len(bones) <= MAX_BONES:
        raise ValueError(f"bones must contain 1..{MAX_BONES} entries")
    normalized = []
    names = set()
    for bone in bones:
        if not isinstance(bone, dict):
            raise ValueError("each bone must be an object")
        name = safe_name(bone.get("name"), "bone name")
        if name in names:
            raise ValueError(f"duplicate bone name: {name}")
        names.add(name)
        head = finite_vector(bone.get("head"), 3, f"{name}.head")
        tail = finite_vector(bone.get("tail"), 3, f"{name}.tail")
        if sum((head[i] - tail[i]) ** 2 for i in range(3)) < 1e-12:
            raise ValueError(f"bone {name} has a zero-length direction")
        parent = bone.get("parent")
        if parent is not None:
            parent = safe_name(parent, f"{name}.parent")
        use_deform = bone.get("use_deform", True)
        use_connect = bone.get("use_connect", False)
        if not isinstance(use_deform, bool) or not isinstance(use_connect, bool):
            raise ValueError(f"bone flags for {name} must be booleans")
        normalized.append({
            "name": name,
            "head": head,
            "tail": tail,
            "parent": parent,
            "use_deform": use_deform,
            "use_connect": use_connect,
        })
    for bone in normalized:
        if bone["parent"] is not None and bone["parent"] not in names:
            raise ValueError(f"unknown parent bone: {bone['parent']}")
        if bone["parent"] == bone["name"]:
            raise ValueError(f"bone {bone['name']} cannot parent itself")
    parents = {bone["name"]: bone["parent"] for bone in normalized}
    for name in parents:
        seen = set()
        current = name
        while current is not None:
            if current in seen:
                raise ValueError("bone hierarchy contains a cycle")
            seen.add(current)
            current = parents[current]
    return normalized


def validate_weights(weights, bone_names, vertex_count):
    if not isinstance(weights, list) or not 1 <= len(weights) <= MAX_WEIGHTS:
        raise ValueError(f"weights must contain 1..{MAX_WEIGHTS} entries")
    valid_bones = set(bone_names)
    normalized = []
    seen = set()
    for item in weights:
        if not isinstance(item, dict):
            raise ValueError("each weight entry must be an object")
        bone = safe_name(item.get("bone"), "weight bone")
        if bone not in valid_bones:
            raise ValueError(f"unknown deform bone: {bone}")
        vertex = item.get("vertex")
        if isinstance(vertex, bool) or not isinstance(vertex, int) or not 0 <= vertex < vertex_count:
            raise ValueError("weight vertex index out of range")
        weight = finite_vector([item.get("weight")], 1, "weight")[0]
        if not 0.0 < weight <= 1.0:
            raise ValueError("weight must be greater than 0 and at most 1")
        key = (bone, vertex)
        if key in seen:
            raise ValueError(f"duplicate weight for bone {bone} and vertex {vertex}")
        seen.add(key)
        normalized.append({"bone": bone, "vertex": vertex, "weight": weight})
    return normalized


def validate_color(value, label="color"):
    color = finite_vector(value, 4, label)
    if any(component < 0.0 or component > 1.0 for component in color):
        raise ValueError(f"{label} components must be between 0 and 1")
    return color


def validate_scalar(value, label, minimum, maximum):
    result = finite_vector([value], 1, label)[0]
    if not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return result
