import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("BFAI_DATA_DIR", "./data")).resolve()
WORK = DATA / "workspace"
IMPORTS = WORK / "imports"
EXPORTS = WORK / "exports"
BLENDER = os.getenv("BLENDER_BIN", "blender")
TIMEOUT = int(os.getenv("BLENDER_TIMEOUT_SECONDS", "300"))

def run_blender(action, **params):
    WORK.mkdir(parents=True, exist_ok=True)
    IMPORTS.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    request = {"action": action, "params": params, "workspace": str(WORK)}
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as f:
        json.dump(request, f)
        request_path = f.name
    try:
        proc = subprocess.run(
            [BLENDER, "--background", "--disable-autoexec", "--python", str(ROOT / "blender_runner" / "dispatch.py"), "--", request_path],
            capture_output=True, text=True, timeout=TIMEOUT, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout)[-5000:])
        marker = "BFAI_RESULT:"
        line = next((x for x in reversed(proc.stdout.splitlines()) if x.startswith(marker)), None)
        if line is None:
            raise RuntimeError("Blender worker returned no result")
        result = json.loads(line[len(marker):])
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Blender operation failed"))
        return result.get("data")
    finally:
        Path(request_path).unlink(missing_ok=True)
