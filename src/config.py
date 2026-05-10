import os
import re
import sys

def get_rustdesk_config_dir():
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    for p in [os.path.join(xdg, "RustDesk"), os.path.expanduser("~/.config/RustDesk")]:
        if os.path.isdir(p): return p
    return os.path.join(xdg, "RustDesk")

def read_rustdesk_config():
    cfg = {"direct_port": "21118", "nat_type": 0, "rendezvous_server": ""}
    path = os.path.join(get_rustdesk_config_dir(), "RustDesk2.toml")
    if not os.path.isfile(path): return cfg
    try:
        with open(path) as f: content = f.read()
        m = re.search(r'^nat_type\s*=\s*(\d+)', content, re.MULTILINE)
        if m: cfg["nat_type"] = int(m.group(1))
        m = re.search(r'^rendezvous_server\s*=\s*"([^"]*)"', content, re.MULTILINE)
        if m: cfg["rendezvous_server"] = m.group(1)
        in_opts = False
        for line in content.splitlines():
            s = line.strip()
            if s == "[options]": in_opts = True; continue
            if s.startswith("[") and s.endswith("]"): in_opts = False; continue
            if in_opts:
                m = re.match(r'direct-access-port\s*=\s*"?(\d+)"?', s)
                if m and int(m.group(1)) > 0: cfg["direct_port"] = m.group(1)
    except (OSError, ValueError) as e:
        print(f"Warning: failed to read config {path}: {e}", file=sys.stderr)
    return cfg

NAT_LABELS = {0: "Unknown", 1: "Asymmetric", 2: "Symmetric"}

SERVER_PORT_MAP = {
    "21114": {"type": "API Server",              "color": "\033[1;35m"},
    "21116": {"type": "Rendezvous (Signaling)",  "color": "\033[1;34m"},
    "21117": {"type": "Relay (Indirect Routing)", "color": "\033[1;31m"},
    "21118": {"type": "WS Rendezvous",           "color": "\033[1;36m"},
    "21119": {"type": "WS Relay",                "color": "\033[1;36m"},
}
