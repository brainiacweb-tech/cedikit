"""Build the cedikit desktop app as a single Windows program: dist-app/cedikit-app.exe.

Run from the repository root, in an environment with cedikit and PyInstaller:

    pip install -e ".[app]" pyinstaller
    python packaging/build_exe.py

The .exe includes Python, Tkinter and cedikit's data files, so it runs on computers
without Python installed. It goes in dist-app/ (not dist/, which holds the PyPI files),
and the script then self-tests it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "packaging" / "launch_desktop.py"
ICON = ROOT / "src" / "cedikit" / "app" / "cedikit.ico"
EXE = ROOT / "dist-app" / "cedikit-app.exe"  # kept out of dist/, which holds the PyPI files

# Big optional libraries the desktop app never uses: keep them out of the .exe.
EXCLUDE = [
    "pandas", "numpy", "matplotlib", "streamlit", "sklearn", "scipy", "joblib",
    "pydantic", "django", "wtforms", "typer", "click", "rich", "PIL", "IPython", "pytest",
]  # fmt: skip


def main() -> int:
    command = [
        sys.executable, "-m", "PyInstaller", str(LAUNCHER),
        "--name", "cedikit-app",
        "--onefile", "--windowed", "--noconfirm", "--clean",
        "--icon", str(ICON),
        "--collect-data", "cedikit",      # YAML data files, icon
        "--hidden-import", "openpyxl",    # Excel export is imported lazily
        "--distpath", str(EXE.parent),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        *[arg for module in EXCLUDE for arg in ("--exclude-module", module)],
    ]  # fmt: skip
    if subprocess.call(command) != 0:
        return 1
    print(f"\nBuilt {EXE} ({EXE.stat().st_size / 1e6:.1f} MB). Self-testing it...")
    return subprocess.call([str(EXE), "--selftest"], timeout=180)


if __name__ == "__main__":
    raise SystemExit(main())
