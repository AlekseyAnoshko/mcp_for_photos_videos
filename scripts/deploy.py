#!/usr/bin/env python3
"""Explicit, repeatable per-user setup. No background daemons or open ports."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from creative_mcp.runtime import config_path, find_app, probe, read_config


def run(command, dry=False, **kwargs):
    print("+ " + shlex.join([str(x) for x in command]), flush=True)
    if not dry:
        return subprocess.run([str(x) for x in command], check=True, **kwargs)


def linux_packages(packages):
    managers = [
        ("apt-get", [["apt-get", "update"], ["apt-get", "install", "-y", *packages]]),
        ("dnf", [["dnf", "install", "-y", *packages]]),
        ("pacman", [["pacman", "-S", "--needed", "--noconfirm", *packages]]),
        ("zypper", [["zypper", "--non-interactive", "install", *packages]]),
    ]
    for name, commands in managers:
        if shutil.which(name):
            return [["sudo", *cmd] for cmd in commands]
    raise RuntimeError("Неизвестный пакетный менеджер. Установите Flatpak вручную и повторите команду.")


def app_plan(system, missing):
    if not missing:
        return []
    if system == "Linux":
        commands = [] if shutil.which("flatpak") else linux_packages(["flatpak"])
        commands.append(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
        ids = {"gimp": "org.gimp.GIMP", "blender": "org.blender.Blender"}
        commands.append(["flatpak", "install", "--user", "-y", "flathub", *[ids[n] for n in missing]])
        return commands
    if system == "Darwin":
        if not shutil.which("brew"):
            raise RuntimeError("Установите Homebrew самостоятельно: https://brew.sh, либо GIMP 3 и Blender вручную.")
        return [["brew", "install", "--cask", *missing]]
    if system == "Windows":
        if not shutil.which("winget"):
            raise RuntimeError("Нужен winget (App Installer) либо ручная установка GIMP 3 и Blender.")
        ids = {"gimp": "GIMP.GIMP.3", "blender": "BlenderFoundation.Blender"}
        return [["winget", "install", "--exact", "--id", ids[n], "--source", "winget", "--accept-source-agreements", "--accept-package-agreements"] for n in missing]
    raise RuntimeError(f"Автоустановка приложений для {system} не реализована.")


def install_codex(dry):
    if find_app("codex"):
        print("Codex уже установлен; оставляем текущую версию.")
        return
    if platform.system() == "Windows":
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("Для установки Codex на Windows нужен Node.js LTS с npm. Установите его и откройте новый терминал.")
        run([npm, "install", "--global", "@openai/codex"], dry)
    else:
        url = "https://chatgpt.com/codex/install.sh"
        if dry:
            print(f"Скачать {url} и выполнить sh (без sudo; stdin закрыт, без интерактивного запуска Codex).")
            return
        with tempfile.TemporaryDirectory(prefix="creative-codex-") as tmp:
            script = Path(tmp) / "install.sh"
            with urllib.request.urlopen(url, timeout=60) as response:
                script.write_bytes(response.read())
            run(["sh", script], stdin=subprocess.DEVNULL)


def register(config_file, server, name, dry):
    codex = find_app("codex")
    if not codex and not dry:
        raise RuntimeError("Codex не найден. Повторите с --install-codex или установите его вручную.")
    codex = codex or ["codex"]
    if not dry:
        current = subprocess.run([*codex, "mcp", "get", name, "--json"], capture_output=True, text=True)
        if current.returncode == 0:
            data = json.loads(current.stdout)
            transport = data.get("transport", {})
            env = transport.get("env") or {}
            if (transport.get("command") == str(server)
                    and not transport.get("args")
                    and env.get("CREATIVE_MCP_CONFIG") == str(config_file)
                    and data.get("enabled", True)):
                print(f"MCP {name} уже зарегистрирован с этой конфигурацией.")
                return
            raise RuntimeError(f"MCP {name} уже существует с другими настройками. Он сохранён. Выберите другое имя через --mcp-name, например creative-mcp-portable.")
        # Do not interpret authentication/config parsing errors as a missing entry.
        if "not found" not in current.stderr.lower() and "no mcp server" not in current.stderr.lower():
            raise RuntimeError(f"Не удалось проверить подключение {name}: {current.stderr.strip()}")
    run([*codex, "mcp", "add", name, "--env", f"CREATIVE_MCP_CONFIG={config_file}", "--", server], dry)


def doctor(config_file):
    config = read_config(config_file)
    report = {name: probe(config[name]["command"], 3) for name in ("gimp", "blender")}
    report["python"] = platform.python_version()
    report["workspace"] = config["workspace"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(report[name]["available"] for name in ("gimp", "blender")) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-apps", action="store_true", help="Установить отсутствующие GIMP 3 / Blender; может понадобиться sudo/UAC")
    parser.add_argument("--install-codex", action="store_true", help="Установить Codex, если отсутствует")
    parser.add_argument("--register-codex", action="store_true", help="Зарегистрировать STDIO MCP, сохранив существующие подключения")
    parser.add_argument("--mcp-name", default="creative-mcp")
    parser.add_argument("--config", type=Path, default=config_path())
    parser.add_argument("--workspace", type=Path, help="Папка материалов для новой конфигурации; по умолчанию ~/CreativeProjects")
    parser.add_argument("--gimp-command", help='JSON-массив, например ["/path/to/gimp-3.0"]')
    parser.add_argument("--blender-command", help='JSON-массив команды запуска Blender')
    parser.add_argument("--dry-run", action="store_true", help="Показать план, не записывать файлы и не устанавливать пакеты")
    parser.add_argument("--doctor", action="store_true", help="Только проверить конфигурацию и версии приложений")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("Нужен Python 3.11 или новее.")
    cfg = args.config.expanduser().resolve()
    if args.doctor:
        return doctor(cfg)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise RuntimeError("Запускайте установщик обычным пользователем, без sudo. Системные команды сами запросят sudo при необходимости.")
    if platform.system() not in ("Linux", "Darwin", "Windows"):
        raise RuntimeError("Поддерживаются только Linux, macOS и Windows.")
    existing = cfg.exists()
    if existing and any((args.workspace, args.gimp_command, args.blender_command)):
        raise RuntimeError("Конфигурация уже существует. Отредактируйте её вручную или используйте --config с новым путём; файл не перезаписан.")
    config = read_config(cfg) if existing else {"schema_version": 1, "workspace": str((args.workspace or Path.home() / "CreativeProjects").expanduser().resolve())}
    if not existing:
        for name in ("gimp", "blender"):
            explicit = getattr(args, f"{name}_command")
            command = json.loads(explicit) if explicit else find_app(name)
            if explicit and (not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command)):
                raise RuntimeError(f"--{name}-command должен быть непустым JSON-массивом строк")
            config[name] = {"command": command}
    missing = [name for name in ("gimp", "blender") if not probe(config[name]["command"], 3)["available"]]
    if missing and args.install_apps:
        for cmd in app_plan(platform.system(), missing):
            run(cmd, args.dry_run)
        if not args.dry_run:
            for name in missing:
                if not existing and not getattr(args, f"{name}_command"):
                    config[name]["command"] = find_app(name)
            missing = [name for name in missing if not probe(config[name]["command"], 3)["available"]]
    if missing and not args.dry_run:
        raise RuntimeError("Не найдены совместимые приложения: " + ", ".join(missing) + ". Используйте --install-apps или задайте точные команды. Если конфигурация уже существует, исправьте пути в ней.")
    if args.dry_run and missing:
        print("Пока не обнаружены: " + ", ".join(missing) + "; перед реальной установкой они обязательны.")
    if args.install_codex:
        install_codex(args.dry_run)
    env = ROOT / ".venv"
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    server = env / ("Scripts/creative-mcp.exe" if os.name == "nt" else "bin/creative-mcp")
    if env.exists() and not (env / "pyvenv.cfg").is_file():
        raise RuntimeError(f"{env} уже существует и не является venv; не изменяю его.")
    if not python.exists():
        run([sys.executable, "-m", "venv", env], args.dry_run)
    run([python, "-m", "pip", "install", "-e", ROOT], args.dry_run)
    if args.dry_run:
        print(f"Конфигурация: {cfg} ({'сохранить существующую' if existing else 'создать'})")
        print(f"Материалы: {config['workspace']}")
    else:
        Path(config["workspace"]).mkdir(parents=True, exist_ok=True)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        if not existing:
            with cfg.open("x", encoding="utf-8") as stream:
                json.dump(config, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        # Machine-specific snapshot, deliberately outside version control.
        resolved = subprocess.check_output([str(python), "-m", "pip", "list", "--format=freeze"], text=True)
        lines = [line for line in resolved.splitlines() if not line.lower().startswith(("creative-mcp==", "pip==", "setuptools==", "wheel=="))]
        cfg.with_name("requirements.resolved.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.register_codex:
        register(cfg, server, args.mcp_name, args.dry_run)
    print("План готов." if args.dry_run else f"Установлено. Конфигурация: {cfg}\nПерезапустите Codex для загрузки MCP. Авторизация в Codex выполняется отдельно.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1)
