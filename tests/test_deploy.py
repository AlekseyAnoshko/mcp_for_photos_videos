import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy", ROOT / "scripts/deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
from creative_mcp import runtime


class DeploymentTests(unittest.TestCase):
    def test_gimp_two_is_rejected(self):
        completed = subprocess.CompletedProcess([], 0, "GNU Image Manipulation Program version 2.10.34", "")
        with patch.object(runtime.subprocess, "run", return_value=completed):
            self.assertFalse(runtime.probe(["gimp"], 3)["available"])

    def test_gimp_three_and_space_path(self):
        completed = subprocess.CompletedProcess([], 0, "GNU Image Manipulation Program version 3.2.8", "")
        with patch.object(runtime.subprocess, "run", return_value=completed) as run:
            self.assertTrue(runtime.probe(["/a path/gimp"], 3)["available"])
            self.assertEqual(run.call_args.args[0], ["/a path/gimp", "--version"])

    def test_timeout_is_reported(self):
        with patch.object(runtime.subprocess, "run", side_effect=subprocess.TimeoutExpired("gimp", 15)):
            self.assertEqual(runtime.probe(["gimp"], 3)["status"], "timeout")

    def test_linux_preserves_native_apps(self):
        with patch.object(deploy.shutil, "which", return_value="/usr/bin/flatpak"):
            plan = deploy.app_plan("Linux", ["gimp"])
        self.assertEqual(plan[-1][-1], "org.gimp.GIMP")
        self.assertNotIn("org.blender.Blender", plan[-1])
        self.assertTrue(all("sudo" not in command for command in plan))

    def test_platform_plans(self):
        with patch.object(deploy.shutil, "which", return_value="manager"):
            self.assertEqual(deploy.app_plan("Darwin", ["gimp"]), [["brew", "install", "--cask", "gimp"]])
            self.assertIn("GIMP.GIMP.3", deploy.app_plan("Windows", ["gimp"])[0])

    def test_config_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.json"
            original = json.dumps({"schema_version": 1, "workspace": tmp, "gimp": {"command": ["gimp"]}, "blender": {"command": ["blender"]}})
            cfg.write_text(original)
            with patch.object(deploy.os, "geteuid", return_value=1000, create=True):
                with self.assertRaisesRegex(RuntimeError, "Конфигурация уже существует"):
                    deploy.main(["--config", str(cfg), "--workspace", str(Path(tmp) / "new")])
            self.assertEqual(cfg.read_text(), original)

    def test_dry_run_no_files_or_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.json"
            with patch.object(deploy.os, "geteuid", return_value=1000, create=True), \
                 patch.object(deploy, "find_app", return_value=["/fake/app"]), \
                 patch.object(deploy, "probe", return_value={"available": True}), \
                 patch.object(deploy, "ROOT", Path(tmp)), \
                 patch.object(deploy.subprocess, "run") as run:
                self.assertEqual(deploy.main(["--dry-run", "--config", str(cfg), "--workspace", str(Path(tmp) / "art"), "--register-codex"]), 0)
                run.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_existing_mcp_is_preserved(self):
        current = subprocess.CompletedProcess([], 0, json.dumps({"transport": {"command": "/old/server"}}), "")
        with patch.object(deploy, "find_app", return_value=["codex"]), \
             patch.object(deploy.subprocess, "run", return_value=current), \
             patch.object(deploy, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "уже существует"):
                deploy.register(Path("/new/config"), Path("/new/server"), "creative-mcp", False)
            run.assert_not_called()

    def test_identical_registration_is_noop(self):
        current = subprocess.CompletedProcess([], 0, json.dumps({"transport": {"command": "/new/server", "env": {"CREATIVE_MCP_CONFIG": "/new/config"}}}), "")
        with patch.object(deploy, "find_app", return_value=["codex"]), \
             patch.object(deploy.subprocess, "run", return_value=current), \
             patch.object(deploy, "run") as run:
            deploy.register(Path("/new/config"), Path("/new/server"), "creative-mcp", False)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
