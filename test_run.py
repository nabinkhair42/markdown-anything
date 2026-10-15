"""Self-check for run.py path helpers. Run: python test_run.py"""

import os

import run


def check(osname: str) -> None:
    os.name = osname
    py = run.venv_exe(run.VENV, "python")
    mineru = run.venv_exe(run.MINERU_ENV, "mineru")
    if osname == "nt":
        assert py.name == "python.exe" and py.parts[-2] == "Scripts", py
        assert mineru.name == "mineru.exe", mineru
    else:
        assert py.name == "python" and py.parts[-2] == "bin", py
        assert mineru.name == "mineru", mineru


if __name__ == "__main__":
    real = os.name
    try:
        check("posix")
        check("nt")
    finally:
        os.name = real
    print("ok")
