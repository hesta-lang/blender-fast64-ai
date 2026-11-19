import json
from mcp.server.fastmcp import FastMCP
from server.blender_runner import run_blender
from server.validation import finite_vector, safe_name, safe_filename

mcp = FastMCP("Blender Fast64 AI Bridge")

@mcp.tool()
def workspace_status() -> str:
    """Return Blender version, current project and Fast64 availability."""
    return json.dumps(run_blender("status"), ensure_ascii=False)

@mcp.tool()
def inspect_scene() -> str:
    """Inspect objects, mesh counts, armatures and materials in the active scene."""
    return json.dumps(run_blender("inspect_scene"), ensure_ascii=False)

@mcp.tool()
def list_objects() -> str:
    """List object names and types in the active Blender scene."""
    return json.dumps(run_blender("list_objects"), ensure_ascii=False)

@mcp.tool()
def rename_object(old_name: str, new_name: str) -> str:
    """Rename one existing Blender object."""
    return json.dumps(run_blender("rename_object", old_name=safe_name(old_name), new_name=safe_name(new_name)), ensure_ascii=False)

@mcp.tool()
def set_object_transform(name: str, location: list[float] | None = None, rotation: list[float] | None = None, scale: list[float] | None = None) -> str:
    """Set location, Euler rotation in radians, and/or scale of an existing object."""
    params = {"name": safe_name(name)}
    if location is not None: params["location"] = finite_vector(location, 3, "location")
    if rotation is not None: params["rotation"] = finite_vector(rotation, 3, "rotation")
    if scale is not None: params["scale"] = finite_vector(scale, 3, "scale")
    return json.dumps(run_blender("set_object_transform", **params), ensure_ascii=False)

@mcp.tool()
def import_model(filename: str) -> str:
    """Import a file already placed in workspace/imports. Allowed: blend, FBX, OBJ, GLB, GLTF, STL, PLY."""
    return json.dumps(run_blender("import_model", filename=safe_filename(filename)), ensure_ascii=False)

@mcp.tool()
def fast64_diagnostics() -> str:
    """Check whether Fast64 modules and operators are registered in Blender."""
    return json.dumps(run_blender("fast64_diagnostics"), ensure_ascii=False)

@mcp.tool()
def fast64_export_operators() -> str:
    """Discover registered Fast64 export operators. Discovery does not guarantee an export will succeed."""
    return json.dumps(run_blender("fast64_export_operators"), ensure_ascii=False)

@mcp.tool()
def save_project() -> str:
    """Save the active Blender project in the persistent workspace."""
    return json.dumps(run_blender("save_project"), ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
