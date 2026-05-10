import importlib.util
import sys

def load_compiled_monitor():
    module_name = "rustdesk_monitor_compiled"
    file_path = "rustdesk-monitor.py"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    monitor = importlib.util.module_from_spec(spec)
    # We don't add to sys.modules to prevent accidental bleed between tests if necessary,
    # but some internal test dependencies might need it. Let's add it.
    sys.modules[module_name] = monitor
    spec.loader.exec_module(monitor)
    return monitor
