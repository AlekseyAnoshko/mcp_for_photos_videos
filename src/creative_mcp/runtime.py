"""Dependency-free discovery, shared by installer and server."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess


def config_path():
    explicit = os.environ.get("CREATIVE_MCP_CONFIG")
    if explicit:
        return Path(explicit).expanduser().resolve()
    base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) if os.name == "nt" else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "creative-mcp" / "config.json"


def probe(command, minimum=0, timeout=15):
    if not command:
        return {"available": False, "status": "not_found", "command": []}
    result = {"available": False, "command": command}
    try:
        proc = subprocess.run([*command, "--version"], capture_output=True, text=True, errors="replace", timeout=timeout)
        output = proc.stdout + "\n" + proc.stderr
        pattern = r"(?:GNU Image Manipulation Program|GIMP|Blender|codex(?:-cli)?)\D*(\d+(?:\.\d+)+)"
        match = re.search(pattern, output, re.I)
        version = match.group(1) if match else None
        result.update(version=version, available=proc.returncode == 0 and version is not None and int(version.split('.')[0]) >= minimum,
                      status="ok" if proc.returncode == 0 else "error")
        if proc.returncode == 0 and not result["available"]:
            result["status"] = "unsupported_version"
        if proc.returncode:
            result["detail"] = output[-1000:]
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
    except OSError as exc:
        result.update(status="error", detail=str(exc))
    return result


def find_app(name):
    candidates = []
    names = {"gimp": ["gimp-3.0", "gimp-3", "gimp"], "blender": ["blender"], "codex": ["codex"]}[name]
    for item in names:
        path = shutil.which(item)
        if path:
            candidates.append([path])
    if name == "codex":
        exe = "codex.exe" if os.name == "nt" else "codex"
        candidates.append([str(Path.home() / ".local/bin" / exe)])
    if platform.system() == "Darwin":
        paths = {"gimp": ["/Applications/GIMP.app/Contents/MacOS/gimp"], "blender": ["/Applications/Blender.app/Contents/MacOS/Blender"], "codex": []}
        candidates.extend([[p] for p in paths[name] if Path(p).exists()])
    if os.name == "nt":
        roots = [Path(os.environ.get("ProgramFiles", "C:/Program Files")), Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Programs"]
        patterns = {"gimp": "GIMP*/bin/gimp-3*.exe", "blender": "Blender Foundation/Blender*/blender.exe", "codex": "_no_match_"}
        for root in roots:
            candidates.extend([[str(p)] for p in sorted(root.glob(patterns[name]), reverse=True)])
    minimum = 3 if name in ("gimp", "blender") else 0
    # Prefer a working native GIMP 3; never select GIMP 2 for the adapter.
    for command in candidates:
        if probe(command, minimum)["available"]:
            return command
    if name in ("gimp", "blender") and shutil.which("flatpak"):
        app = "org.gimp.GIMP" if name == "gimp" else "org.blender.Blender"
        for scope in ("--user", "--system"):
            command = [shutil.which("flatpak"), "run", scope, app]
            if probe(command, minimum)["available"]:
                return command
    return []


def read_config(path=None):
    path = Path(path or config_path())
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported config schema_version")
    if not isinstance(data.get("workspace"), str) or not Path(data["workspace"]).is_absolute():
        raise ValueError("workspace must be an absolute path")
    for name in ("gimp", "blender"):
        command = data.get(name, {}).get("command")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
            raise ValueError(f"{name}.command must be a non-empty argument array")
    return data
