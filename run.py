"""Launch Markdown Anything on Linux, macOS, or Windows.

Steps: check the Python version, create .venv if missing, install any
missing packages, pick a free port (7860 unless taken or PORT is set),
then serve the app on 127.0.0.1. Only the standard library is used here,
so this file runs wherever Python 3.10+ is installed.

Usage:
    python run.py
"""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("PORT", "7860"))
MODULES = ("fastapi", "uvicorn", "markitdown", "pypdf", "multipart")
MINERU_PORT = 16580
MINERU_READY_TIMEOUT_S = 240
MINERU_ENV = Path.home() / "mineru-env"


def venv_exe(venv: Path, name: str) -> Path:
    folder = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return venv / folder / f"{name}{suffix}"


def venv_python() -> Path:
    return venv_exe(VENV, "python")


def check_python() -> None:
    if sys.version_info < (3, 10):
        raise SystemExit(
            f"Python 3.10 or newer is required, found {sys.version.split()[0]}."
        )
    if sys.version_info >= (3, 15):
        print("Note: this project is tested up to Python 3.14.")


def ensure_venv() -> Path:
    python = venv_python()
    if python.exists():
        return python
    print("Creating virtual environment in .venv.")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)], check=True, cwd=ROOT
        )
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Could not create .venv. On Linux this usually means the "
            "python3-venv package is missing (apt install python3-venv)."
        )
    return venv_python()


def ensure_deps(python: Path) -> None:
    probe = (
        "import importlib.util, sys; sys.exit(0 if all("
        "importlib.util.find_spec(m) for m in sys.argv[1:]) else 1)"
    )
    done = subprocess.run(
        [str(python), "-c", probe, *MODULES], capture_output=True
    )
    if done.returncode == 0:
        print("Dependencies are installed.")
        return
    print("Installing dependencies. The first run takes a few minutes.")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        cwd=ROOT,
    )
    subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        check=True,
        cwd=ROOT,
    )


def find_mineru() -> Path | None:
    env = os.environ.get("MINERU_BIN")
    if env and Path(env).exists():
        return Path(env)
    default = venv_exe(MINERU_ENV, "mineru")
    if default.exists():
        return default
    found = shutil.which("mineru")
    return Path(found) if found else None


def install_mineru() -> Path | None:
    """Create ~/mineru-env, install MinerU, fetch OCR models, enable local mode.

    Several GB of download; on failure the app still runs on the fast path.
    """
    print("Installing MinerU OCR engine (first run downloads several GB, can take a while).")
    python = venv_exe(MINERU_ENV, "python")
    try:
        if not python.exists():
            subprocess.run([sys.executable, "-m", "venv", str(MINERU_ENV)], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "mineru"], check=True)
        subprocess.run(
            [str(venv_exe(MINERU_ENV, "mineru-kit")), "models", "download", "--tier", "standard"],
            check=True,
        )
        subprocess.run(
            [str(venv_exe(MINERU_ENV, "mineru")), "config", "set", "parse_server.local.mode", "managed"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"MinerU install failed ({exc}). Scanned PDFs will use the fast path only.")
        return None
    return venv_exe(MINERU_ENV, "mineru")


def mineru_managed(mineru: Path) -> bool:
    proc = subprocess.run(
        [str(mineru), "config", "get", "parse_server.local.mode"],
        capture_output=True,
        text=True,
    )
    return "managed" in proc.stdout


def wait_mineru_ready(timeout: int) -> bool:
    waited = 0
    while waited < timeout:
        with socket.socket() as sock:
            sock.settimeout(2)
            try:
                sock.connect((HOST, MINERU_PORT))
                return True
            except OSError:
                time.sleep(2)
                waited += 2
    return False


def ensure_mineru() -> None:
    mineru = find_mineru() or install_mineru()
    if mineru is None:
        print("MinerU unavailable. Scanned PDFs will use the fast path only.")
        return
    print("Starting MinerU OCR server.")
    started = subprocess.run(
        [str(mineru), "server", "start"], capture_output=True, text=True
    )
    if started.returncode != 0:
        print("MinerU server did not start. Scanned PDFs will use the fast path only.")
        print(started.stderr.strip().splitlines()[-1] if started.stderr.strip() else "")
        return
    if not mineru_managed(mineru):
        print("MinerU local mode is off. For scanned PDFs, download the OCR models once:")
        print("  mineru-kit models download --tier standard")
        print("  mineru config set parse_server.local.mode managed")
        return
    if wait_mineru_ready(MINERU_READY_TIMEOUT_S):
        print("MinerU OCR engine is ready.")
    else:
        print("MinerU is still starting. The app starts anyway.")


def free_port(start: int) -> int:
    port = start
    while port < start + 100:
        with socket.socket() as sock:
            try:
                sock.bind((HOST, port))
                return port
            except OSError:
                port += 1
    raise SystemExit("No free port found near 7860.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    check_python()
    python = ensure_venv()
    ensure_deps(python)
    ensure_mineru()
    port = free_port(DEFAULT_PORT)
    if port != DEFAULT_PORT:
        print(f"Port {DEFAULT_PORT} is busy, using {port} instead.")
    print(f"Markdown Anything is running at http://{HOST}:{port}")
    try:
        subprocess.run(
            [str(python), "-m", "uvicorn", "app:app", "--host", HOST, "--port", str(port)],
            check=True,
            cwd=ROOT,
        )
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
