"""Create and export a blue-cap/gold-emblem Mario DynOS source pack."""
import json
import os
import sys
import zipfile
from collections import Counter
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from blender_runner import dispatch


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def rig_signature(obj):
    return [(b.name, b.parent.name if b.parent else None, bool(b.use_deform))
            for b in obj.data.bones]


def report_material(mat):
    f3d = mat.f3d_mat
    return {
        "name": mat.name,
        "is_f3d": bool(getattr(mat, "is_f3d", False)),
        "coop_player_part": f3d.coopplayerpart.sm64,
        "light": [float(v) for v in f3d.default_light_color],
        "ambient": [float(v) for v in f3d.ambient_light_color],
        "uses_default_lighting": bool(f3d.use_default_lighting),
        "sets_lights": bool(f3d.set_lights),
    }


def recolor_fixed(mat, light_rgb, ambient_rgb):
    require(mat is not None, "Missing target material")
    require(bool(getattr(mat, "is_f3d", False)), f"{mat.name} is not a native F3D material")
    f3d = mat.f3d_mat
    # Fast64-Gart: None uses the material's own light and ambient instead of
    # the live in-game player palette.
    f3d.coopplayerpart.sm64 = "None"
    f3d.set_lights = True
    f3d.use_default_lighting = True
    f3d.set_ambient_from_light = False
    f3d.default_light_color = (*light_rgb, 1.0)
    f3d.ambient_light_color = (*ambient_rgb, 1.0)


def main():
    addon_path = os.environ.get("BFAI_FAST64_ADDON_PATH")
    require(addon_path and (Path(addon_path) / "__init__.py").is_file(),
            "Pinned Fast64-Gart checkout is missing")
    dispatch.ensure_fast64_addon()
    require(hasattr(bpy.ops.object, "sm64_export_geolayout_armature"),
            "Fast64-Gart SM64 geolayout exporter is not registered")

    armature = bpy.data.objects.get("Mario")
    mesh = bpy.data.objects.get("Mario Mesh")
    require(armature is not None and armature.type == "ARMATURE",
            "Mario armature was not found in the Coop Deluxe template")
    require(mesh is not None and mesh.type == "MESH",
            "Mario Mesh was not found in the Coop Deluxe template")
    require(mesh.parent == armature, "Mario Mesh is not parented to the original Mario armature")
    require(len([c for c in armature.children if c.type == "MESH"]) == 1,
            "Expected one primary mesh child under Mario")

    original_rig = rig_signature(armature)
    original_actions = sorted(a.name for a in bpy.data.actions)
    require(len(original_rig) >= 30, "Mario armature looks incomplete")

    materials = [slot.material for slot in mesh.material_slots]
    require(materials and all(materials), "Mario Mesh contains an empty material slot")
    not_f3d = [m.name for m in materials if not getattr(m, "is_f3d", False)]
    require(not not_f3d, "Template materials are not native Fast64-Gart F3D materials: " +
            ", ".join(not_f3d))

    groups = {g.name for g in mesh.vertex_groups}
    bones = {b.name for b in armature.data.bones}
    unknown = sorted(groups - bones)
    require(not unknown, "Vertex groups do not map to the Mario armature: " + ", ".join(unknown))
    influences = Counter(len(v.groups) for v in mesh.data.vertices)
    unassigned = sum(1 for v in mesh.data.vertices if not v.groups)
    require(unassigned == 0, f"{unassigned} Mario vertices are unassigned")
    require(influences.get(1, 0) == len(mesh.data.vertices),
            "Template vertex groups do not have exactly one assignment per vertex: " +
            json.dumps(dict(influences)))

    cap = bpy.data.materials.get("Cap (CAP)")
    logo = bpy.data.materials.get("Logo (EMBLEM)")
    require(cap is not None, "Material Cap (CAP) was not found")
    require(logo is not None, "Material Logo (EMBLEM) was not found")
    before = {"cap": report_material(cap), "emblem": report_material(logo)}

    recolor_fixed(cap, (0.10, 0.34, 1.00), (0.025, 0.09, 0.34))
    recolor_fixed(logo, (1.00, 0.66, 0.08), (0.34, 0.16, 0.018))
    after = {"cap": report_material(cap), "emblem": report_material(logo)}
    require(after["cap"]["coop_player_part"] == "None" and
            after["emblem"]["coop_player_part"] == "None",
            "Fast64-Gart did not set fixed material lighting for the test materials")
    require(rig_signature(armature) == original_rig, "Mario rig changed during recoloring")
    require(sorted(a.name for a in bpy.data.actions) == original_actions,
            "Mario animation actions changed during recoloring")

    workspace = Path(os.environ.get("GITHUB_WORKSPACE", str(ROOT))).resolve()
    pack_root = workspace / "dynos" / "packs" / "MarioStar"
    assets_dir = pack_root / "Assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    require(not any(assets_dir.iterdir()), "Output Assets folder is not empty; refusing overwrite")

    scene = bpy.context.scene
    require(hasattr(scene, "fast64") and hasattr(scene.fast64, "sm64"),
            "Fast64-Gart SM64 scene settings are unavailable")
    sm64 = scene.fast64.sm64
    combined = sm64.combined_export
    roots = [b for b in armature.data.bones if b.parent is None]
    require(len(roots) == 1, f"Expected one Mario root bone, got {len(roots)}")
    root = roots[0]
    require(hasattr(root, "geo_cmd"), "Mario root bone has no Fast64 geolayout property")

    old_active = bpy.context.view_layer.objects.active
    old_selected = list(bpy.context.selected_objects)
    saved = {
        "export_type": sm64.export_type,
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
    export_finished = False
    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        root.geo_cmd = "Start"
        if hasattr(scene, "gameEditorMode"):
            scene.gameEditorMode = "SM64"

        sm64.export_type = "C"
        combined.export_header_type = "Custom"
        combined.custom_export_path = str(assets_dir)
        combined.export_gfx = True
        combined.export_col = False
        combined.export_anim = False
        combined.export_all_selected = False
        combined.graphics_object = mesh
        combined.object_name = "mario"
        combined.use_name_filtering = False
        scene.saveTextures = True

        result = bpy.ops.object.sm64_export_geolayout_armature(export_obj=armature.name)
        require("FINISHED" in result,
                "Fast64-Gart export did not finish: " + ", ".join(sorted(result)))
        export_finished = True
    finally:
        sm64.export_type = saved["export_type"]
        combined.export_header_type = saved["export_header_type"]
        combined.custom_export_path = saved["custom_export_path"]
        combined.export_gfx = saved["export_gfx"]
        combined.export_col = saved["export_col"]
        combined.export_anim = saved["export_anim"]
        combined.export_all_selected = saved["export_all_selected"]
        combined.graphics_object = saved["graphics_object"]
        combined.object_name = saved["object_name"]
        combined.use_name_filtering = saved["use_name_filtering"]
        scene.saveTextures = saved["saveTextures"]
        try:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in old_selected:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            if old_active and old_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = old_active
        except Exception:
            pass

    require(export_finished, "Fast64-Gart export failed")
    generated = sorted(p for p in assets_dir.rglob("*") if p.is_file())
    require(generated, "Fast64-Gart produced no files")
    c_files = [p for p in generated if p.suffix.lower() == ".c"]
    geo_files = [p.name for p in generated if "geo" in p.name.lower()]
    model_files = [p.name for p in generated if "model" in p.name.lower()]
    require(c_files, "No C source file was generated")
    require(geo_files, "No geolayout output was generated")
    require(model_files, "No model/display-list output was generated")

    pack_root.joinpath("README.txt").write_text(
        "Mario Star - DynOS source pack candidate\n"
        "========================================\n\n"
        "Install this folder under the game's dynos/packs directory.\n"
        "The exported C sources and textures are in Assets/.\n"
        "SM64CoopDX creates runtime .bin assets when the pack is loaded.\n"
        "Delete stale generated .bin files before rebuilding changed assets.\n\n"
        "This artifact validates Fast64-Gart export only. It has not been opened\n"
        "in SM64CoopDX; in-game loading and appearance are not yet verified.\n",
        encoding="utf-8",
    )
    try:
        bpy.ops.file.pack_all()
    except Exception as exc:
        print("BFAI_PACK_IMAGES_WARNING:" + str(exc))
    blend_path = workspace / "mario_star_variant.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    report = {
        "status": "FAST64_GART_DYNOS_SOURCE_EXPORT_PASS",
        "blender_version": bpy.app.version_string,
        "addon": "ManIsCat2/Fast64-Gart",
        "addon_commit": "9384477f2ccdc8b6e05a96b52241f98808feb90b",
        "template": "coop-deluxe/character-template",
        "template_commit": "58149f1b58cef75c7f90c19f6d3cadb66bd5b915",
        "armature": armature.name,
        "mesh": mesh.name,
        "bone_count": len(original_rig),
        "animation_actions": original_actions,
        "vertex_count": len(mesh.data.vertices),
        "vertex_group_count": len(mesh.vertex_groups),
        "vertex_influence_distribution": dict(influences),
        "materials_before": before,
        "materials_after": after,
        "output_files": [str(p.relative_to(pack_root)) for p in generated],
        "geo_files": geo_files,
        "model_files": model_files,
        "runtime_bin_generated": False,
        "in_game_tested": False,
    }
    (workspace / "mario_star_export_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    zip_path = workspace / "MarioStar-DynOS-source-pack.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(pack_root.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(pack_root.parent))

    print("BFAI_MARIO_STAR_MATERIALS:" + json.dumps(after))
    print("BFAI_MARIO_STAR_OUTPUT:" + json.dumps(report["output_files"]))
    print("BFAI_MARIO_STAR_EXPORT:PASS")


if __name__ == "__main__":
    main()
