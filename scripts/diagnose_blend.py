"""Run the read-only asset pipeline inspector on a .blend file from inbox/."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INBOX = (ROOT / "inbox").resolve()
REPORTS = ROOT / "reports"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    value = os.environ.get("BFAI_BLEND_INPUT", "").strip()
    if not value:
        raise SystemExit("Set BFAI_BLEND_INPUT to a .blend file inside inbox/")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".blend":
        raise SystemExit("Input must be a relative .blend path inside inbox/")
    source = (ROOT / relative).resolve()
    if not source.is_relative_to(INBOX) or not source.is_file():
        raise SystemExit("Input file does not exist inside inbox/")
    if source.stat().st_size == 0:
        raise SystemExit("Input .blend file is empty")

    data_dir = Path(os.environ.get("BFAI_DATA_DIR", tempfile.mkdtemp(prefix="bfai-diagnostics-"))).resolve()
    workspace = data_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    # Keep relative texture folders beside the project when possible.
    shutil.copytree(
        source.parent,
        workspace,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.blend", "*.blend1", "__pycache__"),
    )
    shutil.copy2(source, workspace / "active.blend")
    os.environ["BFAI_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("BLENDER_BIN", "blender")

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from server.blender_runner import run_blender

    report = run_blender("inspect_asset_pipeline")
    report["input_file"] = {
        "repository_path": relative.as_posix(),
        "size_bytes": source.stat().st_size,
        "sha256": sha256(source),
    }
    report["execution"] = {
        "mode": "GitHub Actions headless Blender",
        "automatic_blend_python": "disabled",
        "read_only_scene_inspection": True,
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    destination = REPORTS / "pipeline-report.json"
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = report.get("summary", {})
    print("BFAI_DIAGNOSTIC_REPORT=" + str(destination))
    print(json.dumps({
        "objects_inspected": summary.get("objects_inspected", 0),
        "mesh_objects_in_scene": summary.get("mesh_objects_in_scene", 0),
        "issue_counts": summary.get("issue_counts", {}),
        "report": str(destination.relative_to(ROOT)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
