"""MCP tools for the restricted Blender/Fast64 worker."""
import json
from mcp.server.fastmcp import FastMCP
from server.blender_runner import run_blender
from server.validation import (
    finite_vector, safe_name, safe_filename, safe_texture_filename,
    validate_mesh_data, validate_bones, validate_weights,
    validate_color, validate_scalar,
)

mcp = FastMCP("Blender Fast64 AI Bridge")


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


@mcp.tool()
def workspace_status() -> str:
    """Return Blender version, current project and Fast64 availability."""
    return encoded(run_blender("status"))


@mcp.tool()
def inspect_scene() -> str:
    """Inspect objects, mesh counts, materials, armatures and texture images."""
    return encoded(run_blender("inspect_scene"))


@mcp.tool()
def list_objects() -> str:
    """List object names and types in the active Blender scene."""
    return encoded(run_blender("list_objects"))


@mcp.tool()
def rename_object(old_name: str, new_name: str) -> str:
    """Rename one existing Blender object."""
    return encoded(run_blender("rename_object", old_name=safe_name(old_name), new_name=safe_name(new_name)))


@mcp.tool()
def set_object_transform(name: str, location: list[float] | None = None, rotation: list[float] | None = None, scale: list[float] | None = None) -> str:
    """Set location, Euler rotation in radians, and/or scale of an existing object."""
    params = {"name": safe_name(name)}
    if location is not None:
        params["location"] = finite_vector(location, 3, "location")
    if rotation is not None:
        params["rotation"] = finite_vector(rotation, 3, "rotation")
    if scale is not None:
        params["scale"] = finite_vector(scale, 3, "scale")
    if not any(key in params for key in ("location", "rotation", "scale")):
        raise ValueError("provide location, rotation, or scale")
    return encoded(run_blender("set_object_transform", **params))


@mcp.tool()
def import_model(filename: str) -> str:
    """Import a model already placed in workspace/imports. Allowed: BLEND, FBX, OBJ, GLB, GLTF, STL, PLY."""
    return encoded(run_blender("import_model", filename=safe_filename(filename)))


@mcp.tool()
def create_mesh_object(name: str, vertices: list[list[float]], faces: list[list[int]]) -> str:
    """Create a real editable Blender mesh from vertex coordinates and polygon indices. Limits: 50,000 vertices/faces."""
    points, polygons = validate_mesh_data(vertices, faces)
    return encoded(run_blender("create_mesh_object", name=safe_name(name), vertices=points, faces=polygons))


@mcp.tool()
def create_armature(name: str, bones: list[dict]) -> str:
    """Create an armature with named bones. Each bone needs name, head and tail; parent is optional."""
    return encoded(run_blender("create_armature", name=safe_name(name), bones=validate_bones(bones)))


@mcp.tool()
def bind_mesh_to_armature(mesh_name: str, armature_name: str) -> str:
    """Bind a mesh to an armature using Blender automatic bone-heat weights. This can fail on disconnected or unsuitable geometry."""
    return encoded(run_blender("bind_mesh_to_armature", mesh_name=safe_name(mesh_name), armature_name=safe_name(armature_name)))


@mcp.tool()
def set_vertex_weights(mesh_name: str, armature_name: str, weights: list[dict]) -> str:
    """Assign explicit skin weights. Each entry is {bone, vertex, weight}; weights are 0..1."""
    data = run_blender("weight_context", mesh_name=safe_name(mesh_name), armature_name=safe_name(armature_name))
    normalized = validate_weights(weights, data["bones"], data["vertex_count"])
    return encoded(run_blender("set_vertex_weights", mesh_name=safe_name(mesh_name), armature_name=safe_name(armature_name), weights=normalized))


@mcp.tool()
def create_material(name: str, base_color: list[float] = [0.8, 0.8, 0.8, 1.0], metallic: float = 0.0, roughness: float = 0.5, texture_filename: str | None = None, assign_to_object: str | None = None) -> str:
    """Create a Principled BSDF material; optionally load a texture from workspace/imports and assign it to an object."""
    params = {
        "name": safe_name(name),
        "base_color": validate_color(base_color, "base_color"),
        "metallic": validate_scalar(metallic, "metallic", 0.0, 1.0),
        "roughness": validate_scalar(roughness, "roughness", 0.0, 1.0),
    }
    if texture_filename is not None:
        params["texture_filename"] = safe_texture_filename(texture_filename)
    if assign_to_object is not None:
        params["assign_to_object"] = safe_name(assign_to_object)
    return encoded(run_blender("create_material", **params))


@mcp.tool()
def assign_material(object_name: str, material_name: str) -> str:
    """Assign an existing Blender material to an object, replacing its first material slot."""
    return encoded(run_blender("assign_material", object_name=safe_name(object_name), material_name=safe_name(material_name)))


@mcp.tool()
def smart_uv_unwrap(mesh_name: str) -> str:
    """Create UVs using Blender Smart UV Project for an existing mesh."""
    return encoded(run_blender("smart_uv_unwrap", mesh_name=safe_name(mesh_name)))


@mcp.tool()
def fast64_diagnostics() -> str:
    """Check loaded Fast64 modules, enabled addons and registered Fast64-related namespaces."""
    return encoded(run_blender("fast64_diagnostics"))


@mcp.tool()
def fast64_export_operators() -> str:
    """Discover installed Fast64 export operators and their available properties."""
    return encoded(run_blender("fast64_export_operators"))


@mcp.tool()
def fast64_run_export(operator_identifier: str, properties: dict | None = None) -> str:
    """Run one currently registered Fast64 export operator discovered by fast64_export_operators. File outputs are restricted to workspace/exports."""
    identifier = safe_name(operator_identifier, "operator_identifier")
    if len(identifier) > 160 or "." not in identifier or "(" in identifier or ")" in identifier:
        raise ValueError("invalid Blender operator identifier")
    if properties is not None and not isinstance(properties, dict):
        raise ValueError("properties must be an object")
    if properties is not None and len(properties) > 64:
        raise ValueError("too many operator properties")
    return encoded(run_blender("fast64_run_export", operator_identifier=identifier, properties=properties or {}))


@mcp.tool()
def save_project() -> str:
    """Save the active Blender project in the persistent workspace as active.blend."""
    return encoded(run_blender("save_project"))


if __name__ == "__main__":
    mcp.run()
