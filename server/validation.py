import math
import os
import re

ALLOWED_IMPORTS = {".blend", ".fbx", ".obj", ".glb", ".gltf", ".stl", ".ply"}

def finite_vector(value, size=3, label="vector"):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"{label} must contain {size} numbers")
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result):
        raise ValueError(f"{label} contains a non-finite number")
    return result

def safe_name(value, label="name"):
    if not isinstance(value, str) or not value.strip() or len(value) > 96:
        raise ValueError(f"invalid {label}")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {label}")
    return value.strip()

def safe_filename(value):
    if not isinstance(value, str) or os.path.basename(value) != value or value in {"", ".", ".."}:
        raise ValueError("filename must be a plain file name")
    if not re.fullmatch(r"[A-Za-z0-9_. -]{1,120}", value):
        raise ValueError("filename contains unsupported characters")
    if os.path.splitext(value)[1].lower() not in ALLOWED_IMPORTS:
        raise ValueError("file extension is not allowed")
    return value

def validate_mesh_data(vertices, faces):
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= 50000:
        raise ValueError("vertices must contain 3..50000 points")
    points = [finite_vector(v, 3, "vertex") for v in vertices]
    if not isinstance(faces, list) or not 1 <= len(faces) <= 50000:
        raise ValueError("faces must contain 1..50000 polygons")
    polygons = []
    for face in faces:
        if not isinstance(face, list) or not 3 <= len(face) <= 64:
            raise ValueError("each face must contain 3..64 indices")
        if any(not isinstance(i, int) or i < 0 or i >= len(points) for i in face):
            raise ValueError("face index out of range")
        polygons.append(face)
    return points, polygons
