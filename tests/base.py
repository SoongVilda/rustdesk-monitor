import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_compiled_monitor():
    module_name = "rustdesk_monitor_compiled"
    file_path = PROJECT_ROOT / "rustdesk-monitor.py"
    spec = importlib.util.spec_from_file_location(module_name, file_path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load compiled monitor from {file_path}")

    monitor = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = monitor
    spec.loader.exec_module(monitor)
    return monitor
