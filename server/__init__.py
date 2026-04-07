import importlib.util
from pathlib import Path


_ROOT_SERVER_FILE = Path(__file__).resolve().parent.parent / "server.py"
_spec = importlib.util.spec_from_file_location("_server_file_module", _ROOT_SERVER_FILE)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_module)

app = _module.app


def main():
    _module.main()
