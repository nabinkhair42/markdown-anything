"""Launch Markdown Anything on Linux, macOS, or Windows.

Steps: check the Python version, create .venv if missing, install any
missing packages, pick a free port (7860 unless taken or PORT is set),
then serve the app on 127.0.0.1. Only the standard library is used here,
so this file runs wherever Python 3.10+ is installed.

Usage:
    python run.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("PORT", "7860"))
MODULES = ("fastapi", "uvicorn", "markitdown", "pypdf", "multipart")


def venv_python() -> Path:
    folder = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    return VENV / folder / exe


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
    check_python()
    python = ensure_venv()
    ensure_deps(python)
    port = free_port(DEFAULT_PORT)
    if port != DEFAULT_PORT:
        print(f"Port {DEFAULT_PORT} is busy, using {port} instead.")
    print(f"Markdown Anything is running at http://{HOST}:{port}")
    subprocess.run(
        [str(python), "-m", "uvicorn", "app:app", "--host", HOST, "--port", str(port)],
        check=True,
        cwd=ROOT,
    )


if __name__ == "__main__":
    main()
