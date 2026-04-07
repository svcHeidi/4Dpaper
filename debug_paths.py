import sys
from pathlib import Path

_here = Path("_extensions/4dpaper/4dpaper.py").resolve()
_ext_dir = _here.parent
_project_root = _ext_dir.parent.parent.parent if _ext_dir.name == "4dpaper" else _ext_dir.parent
_venv_python = _project_root / ".venv" / "bin" / "python"

print(f"HERE: {_here}")
print(f"EXT_DIR: {_ext_dir}")
print(f"PROJECT_ROOT: {_project_root}")
print(f"VENV_PYTHON: {_venv_python}")
print(f"VENV_EXISTS: {_venv_python.exists()}")
