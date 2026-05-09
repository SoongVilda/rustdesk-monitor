#!/usr/bin/env python3
"""
RustDesk Connection Monitor v4.0

Real-time terminal dashboard for RustDesk connections with live throughput,
RTT sparklines, connection duration, health grading, and alert detection.

Port Architecture (hbb_common/config.rs):
  21114 = API Server    21116 = Rendezvous    21117 = Relay
  21118 = WS Rendezvous / Direct Access (default)    21119 = WS Relay / LAN Discovery

Dependencies: Python 3.x + ss (iproute2). No pip packages.
"""

import subprocess, time, sys, shutil, json, argparse, os, re

# =============================================================================
# Config Reader
# =============================================================================

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
    except Exception: pass
    return cfg

NAT_LABELS = {0: "Unknown", 1: "Asymmetric", 2: "Symmetric"}

# =============================================================================
# Port Map
# =============================================================================

SERVER_PORT_MAP = {
    "21114": {"type": "API Server",              "color": "\033[1;35m"},
    "21116": {"type": "Rendezvous (Signaling)",  "color": "\033[1;34m"},
    "21117": {"type": "Relay (Indirect Routing)", "color": "\033[1;31m"},
    "21118": {"type": "WS Rendezvous",           "color": "\033[1;36m"},
    "21119": {"type": "WS Relay",                "color": "\033[1;36m"},
}

# =============================================================================
# Parsing
# =============================================================================

def extract_port(addr):
    if addr in ("*:*",) or addr.endswith(":*"): return "*"
    if "]:" in addr: return addr.rsplit(":", 1)[-1]
    return addr.rsplit(":", 1)[-1] if ":" in addr else ""

def parse_tcp_info(line):
    """Extract rtt, jitter, cwnd, retrans, bytes_sent, bytes_received from ss -i."""
    rtt = jitter = cwnd = retrans = bsent = brecv = None
    m = re.search(r'rtt:(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)', line)
    if m: rtt, jitter = float(m.group(1)), float(m.group(2))
    m = re.search(r'cwnd:(\d+)', line)
    if m: cwnd = int(m.group(1))
    m = re.search(r'retrans:\d+/(\d+)', line)
    if m: retrans = int(m.group(1))
    m = re.search(r'bytes_sent:(\d+)', line)
    if m: bsent = int(m.group(1))
    m = re.search(r'bytes_received:(\d+)', line)
    if m: brecv = int(m.group(1))
    return rtt, jitter, cwnd, retrans, bsent, brecv

def parse_connections(process_name, direct_port):
    try:
        output = subprocess.check_output(
            ["ss", "-tuipn"], universal_newlines=True, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("\033[1;31mError:\033[0m 'ss' not found. Install iproute2.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError:
        return []

    conns = []
    lines = output.strip().split('\n')
    pname = process_name.lower()
    i = 0
    while i < len(lines):
        line = lines[i]
        if pname not in line.lower():
            i += 1; continue
        parts = line.split()
        if len(parts) < 6:
            i += 1; continue

        proto, state, rx, tx, local, peer = parts[:6]
        rtt, jitter, cwnd, retrans, bsent, brecv = None, None, None, None, None, None
        if i + 1 < len(lines) and lines[i + 1] and lines[i + 1][0] in (' ', '\t'):
            rtt, jitter, cwnd, retrans, bsent, brecv = parse_tcp_info(lines[i + 1])
            i += 1

        local_port = extract_port(local)
        peer_port = extract_port(peer)

        direction = "?"
        conn_type = "Unknown"
        color = "\033[0m"

        if state in ("LISTEN", "UNCONN"):
            direction = "LSTN"
            if local_port == direct_port:
                conn_type, color = "Direct Access (Listening)", "\033[1;32m"
            elif local_port == "21116":
                conn_type, color = "Rendezvous (Listening)", "\033[1;34m"
            elif local_port == "21118" and local_port != direct_port:
                conn_type, color = "WS Rendezvous (Listening)", "\033[1;36m"
            else:
                conn_type, color = "Service (Listening)", "\033[38;5;245m"
        else:
            if local_port == direct_port and state == "ESTAB":
                direction, conn_type, color = "IN", "Direct (Incoming Peer)", "\033[1;32m"
            elif peer_port in SERVER_PORT_MAP:
                direction = "OUT"
                conn_type, color = SERVER_PORT_MAP[peer_port]["type"], SERVER_PORT_MAP[peer_port]["color"]
            elif proto == "udp" and peer_port not in ("*", ""):
                direction, conn_type, color = "P2P", "Direct (UDP Hole-Punch)", "\033[1;32m"
            else:
                direction = "P2P"
                conn_type = "Direct (TCP P2P)" if proto == "tcp" else "Unknown"
                color = "\033[1;32m" if proto == "tcp" else "\033[0m"

        proc_blob = "".join(parts[6:]) if len(parts) > 6 else ""
        pid = pname_parsed = ""
        if "pid=" in proc_blob:
            try:
                pid = proc_blob.split("pid=")[1].split(",")[0]
                if 'users:(("' in proc_blob:
                    pname_parsed = proc_blob.split('users:(("')[1].split('"')[0]
            except Exception: pass

        conns.append({
            "proto": proto, "state": state, "rx": rx, "tx": tx,
            "dir": direction, "local": local, "peer": peer,
            "pid": pid, "pname": pname_parsed, "type": conn_type, "color": color,
            "rtt": rtt, "jitter": jitter, "cwnd": cwnd, "retrans": retrans,
            "bytes_sent": bsent, "bytes_received": brecv,
        })
        i += 1
    return conns

# =============================================================================
# Connection Tracker — state across refresh cycles
# =============================================================================

class ConnectionTracker:
    def __init__(self, spark_depth=20):
        self.spark_depth = spark_depth
        self._state = {}

    def _key(self, c):
        return (c['local'], c['peer'])

    def update(self, conns):
        now = time.time()
        seen = set()
        for c in conns:
            k = self._key(c)
            seen.add(k)
            if k not in self._state:
                self._state[k] = {
                    'first_seen': now, 'rtt_hist': [],
                    'prev_bsent': None, 'prev_brecv': None, 'prev_t': None,
                }
            st = self._state[k]

            # Duration
            c['duration'] = now - st['first_seen']

            # RTT sparkline history
            if c.get('rtt') is not None:
                st['rtt_hist'].append(c['rtt'])
                if len(st['rtt_hist']) > self.spark_depth:
                    st['rtt_hist'] = st['rtt_hist'][-self.spark_depth:]
            c['rtt_hist'] = list(st['rtt_hist'])

            # Throughput (bytes/sec)
            c['tx_rate'] = c['rx_rate'] = None
            bs, br = c.get('bytes_sent'), c.get('bytes_received')
            if bs is not None and st['prev_bsent'] is not None and st['prev_t'] is not None:
                dt = now - st['prev_t']
                if dt > 0.05:
                    c['tx_rate'] = max(0, (bs - st['prev_bsent'])) / dt
                    c['rx_rate'] = max(0, (br - (st['prev_brecv'] or 0))) / dt
            st['prev_bsent'] = bs
            st['prev_brecv'] = br
            st['prev_t'] = now

            # Health grade
            c['health'] = compute_health(c)

        # Prune gone connections
        for k in [k for k in self._state if k not in seen]:
            del self._state[k]
        return conns

# =============================================================================
# Derived Metrics
# =============================================================================

SPARK_CHARS = "▁▂▃▄▅▆▇█"

def render_sparkline(values, width=10):
    if not values: return ""
    vals = values[-width:]
    lo, hi = min(vals), max(vals)
    span = hi - lo if hi > lo else 1
    out = ""
    for v in vals:
        idx = int((v - lo) / span * (len(SPARK_CHARS) - 1))
        out += SPARK_CHARS[min(idx, len(SPARK_CHARS) - 1)]
    return out

def rtt_color(rtt):
    if rtt is None:  return "\033[38;5;242m"
    if rtt < 20:     return "\033[38;5;84m"
    if rtt < 80:     return "\033[38;5;220m"
    return "\033[38;5;196m"

def compute_health(c):
    """A/B/C/D/F health grade from connection metrics."""
    if c.get('dir') == 'LSTN': return '—'
    rtt = c.get('rtt')
    if rtt is None: return '?'
    retrans = c.get('retrans') or 0
    jitter = c.get('jitter') or 0
    try:
        q = int(c.get('rx', 0)) + int(c.get('tx', 0))
    except (ValueError, TypeError):
        q = 0
    if rtt < 20 and jitter < 5 and retrans == 0 and q == 0: return 'A'
    if rtt < 50 and retrans <= 2: return 'B'
    if rtt < 100: return 'C'
    if rtt < 200: return 'D'
    return 'F'

# Health: colored dot + letter
HEALTH_DOT = {
    'A': "\033[38;5;84m●",  'B': "\033[38;5;114m●",  'C': "\033[38;5;220m●",
    'D': "\033[38;5;208m●", 'F': "\033[38;5;196m●",  '?': "\033[38;5;242m○",
    '—': "\033[38;5;242m·",
}

# Direction icons
DIR_ICONS = {
    'IN':  "\033[38;5;84m▼",   'OUT': "\033[38;5;75m▲",
    'P2P': "\033[38;5;183m⇄",  'LSTN': "\033[38;5;242m◉",
    '?':   "\033[38;5;242m·",
}

# Type colors (refined palette)
TYPE_COLORS = {
    'Direct':     "\033[38;5;84m",
    'Relay':      "\033[38;5;196m",
    'Rendezvous': "\033[38;5;75m",
    'API':        "\033[38;5;183m",
    'WS':         "\033[38;5;117m",
    'Service':    "\033[38;5;242m",
}

def type_color(conn_type):
    for key, color in TYPE_COLORS.items():
        if key in conn_type: return color
    return "\033[0m"

def fmt_duration(secs):
    if secs < 60: return f"{int(secs)}s"
    if secs < 3600: return f"{int(secs//60)}m{int(secs%60)}s"
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    return f"{h}h{m}m"

def fmt_rate(bps):
    """Format bytes/sec to human string."""
    if bps is None: return "—"
    if bps < 1024: return f"{bps:.0f}B"
    if bps < 1024 * 1024: return f"{bps/1024:.1f}K"
    return f"{bps/1024/1024:.1f}M"

def detect_alerts(conns):
    """Return list of alert strings for current state."""
    alerts = []
    relay = [c for c in conns if "Relay" in c['type'] and c['dir'] != 'LSTN']
    if relay:
        alerts.append(f"⚠ {len(relay)} relay connection(s) — not direct")
    high_rtt = [c for c in conns if c.get('rtt') is not None and c['rtt'] > 200]
    if high_rtt:
        alerts.append(f"⚠ {len(high_rtt)} connection(s) with RTT >200ms")
    retrans = [c for c in conns if c.get('retrans') and c['retrans'] > 5]
    if retrans:
        alerts.append(f"⚠ {len(retrans)} connection(s) with retransmissions")
    queued = []
    for c in conns:
        try:
            if int(c.get('rx', 0)) > 0 or int(c.get('tx', 0)) > 0:
                queued.append(c)
        except (ValueError, TypeError): pass
    if queued:
        alerts.append(f"⚠ {len(queued)} connection(s) with queued data")
    return alerts

# =============================================================================
# Dashboard Renderer
# =============================================================================

R  = "\033[0m"
B  = "\033[1m"
DIM = "\033[38;5;242m"
BORDER = "\033[38;5;60m"
HDR_BG = "\033[48;5;236m\033[38;5;75m"
ALERT_BG = "\033[48;5;52m\033[38;5;196m"
SUMMARY_FG = "\033[38;5;252m"
LABEL = "\033[38;5;75m"
VAL = "\033[1;38;5;255m"

def clear_screen():
    sys.stdout.write("\033[2J\033[H"); sys.stdout.flush()

def ansi_len(s):
    """Visible length of a string, ignoring ANSI escape codes."""
    return len(re.sub(r'\033\[[0-9;]*m', '', s))

def ansi_ljust(s, width):
    """Left-justify a string with ANSI codes to `width` visible characters."""
    pad = width - ansi_len(s)
    return s + (' ' * pad) if pad > 0 else s

def ansi_center(s, width):
    """Center a string with ANSI codes within `width` visible characters."""
    pad = width - ansi_len(s)
    if pad <= 0: return s
    left = pad // 2
    return ' ' * left + s + ' ' * (pad - left)

def trunc(s, w):
    if w <= 1: return ""
    mx = w - 1
    if len(s) <= mx: return s
    if mx < 10: return s[:mx]
    h = (mx - 3) // 2
    return s[:h] + "…" + s[-(mx - 3 - h):]

def _border_line(tw, title="", char="─"):
    iw = tw - 2  # inner width (inside ├ ┤)
    if not title:
        return f"{BORDER}├{char * iw}┤{R}"
    tlen = len(title) + 2  # " title "
    pad = (iw - tlen - 2) // 2  # ─ before ┤
    rem = iw - pad - tlen - 2    # ─ after ├
    return f"{BORDER}├{char * pad}┤{R} {B}{title}{R} {BORDER}├{char * rem}┤{R}"

def _boxed_line(tw, content):
    """Print a line inside box borders │ ... │, centered."""
    iw = tw - 4  # usable inner space (│ + space + ... + space + │)
    print(f"{BORDER}│{R} {ansi_center(content, iw)} {BORDER}│{R}")

def _stat_pill(label, value, color=VAL):
    return f"{LABEL}{label} {color}{value}{R}"

def print_dashboard(conns, nat_label, direct_port):
    raw_tw = shutil.get_terminal_size((120, 20)).columns

    active = [c for c in conns if c['dir'] != 'LSTN']
    infra = [c for c in conns if c['dir'] == 'LSTN']

    il = max([len(c['local']) for c in active] + [5]) + 1 if active else 6
    ip = max([len(c['peer']) for c in active] + [4]) + 1 if active else 5
    max_type = max([len(c['type']) for c in active] + [16]) if active else 16
    
    # Calculate width needed to fit full IPv6 addresses without truncation
    # fixed columns: H(3) PRT(5) DIR(4) SP(8) RTT(11) TREND(12) THR(15) AGE(8) TYPE(max_type)
    fixed_cols_width = 3 + 5 + 4 + 8 + 11 + 12 + 15 + 8 + max_type
    needed_tw = fixed_cols_width + il + ip
    
    # Scale flexibly up to terminal width, but no wider than needed to avoid empty stretching
    tw = min(raw_tw, max(110, needed_tw))

    # ╭─── Header ───╮
    print(f"{BORDER}╭{'─' * (tw - 2)}╮{R}")
    clock = time.strftime("%H:%M:%S")
    title = "RustDesk Connection Monitor"
    title_s = f"{HDR_BG} {title} {R}"
    clock_s = f"{DIM}{clock}{R}"
    # space: │ <pad> <title> <gap> <clock> <pad> │
    iw = tw - 4
    used = len(title) + 2 + len(clock)  # visible chars
    gap = iw - used
    left = gap // 2
    right = gap - left
    print(f"{BORDER}│{R} {' ' * left}{title_s}{' ' * right}{clock_s} {BORDER}│{R}")
    print(f"{BORDER}├{'─' * (tw - 2)}┤{R}")

    # │ Summary stats │
    d_n = sum(1 for c in active if "Direct" in c['type'])
    r_n = sum(1 for c in active if "Relay" in c['type'])
    rn_n = sum(1 for c in active if "Rendezvous" in c['type'])
    rtts = [c['rtt'] for c in active if c.get('rtt') is not None]

    pills = [
        _stat_pill("Sessions:", str(len(active))),
        _stat_pill("Direct:", str(d_n), "\033[38;5;84m" if d_n else VAL),
        _stat_pill("Relay:", str(r_n), "\033[38;5;196m" if r_n else VAL),
        _stat_pill("Rend:", str(rn_n)),
        _stat_pill("NAT:", nat_label),
    ]
    if rtts:
        avg = sum(rtts) / len(rtts)
        pills.append(_stat_pill("Avg RTT:", f"{avg:.1f}ms", rtt_color(avg)))

    stats_text = "  │  ".join(pills)
    _boxed_line(tw, stats_text)

    if direct_port != "21118":
        _boxed_line(tw, f"{DIM}Direct Port: {direct_port} (custom){R}")

    # ├─── Alerts ───┤
    alerts = detect_alerts(conns)
    if alerts:
        print(f"{BORDER}├{'─' * (tw - 2)}┤{R}")
        for a in alerts:
            alert_s = f"{ALERT_BG}{B} {a} {R}"
            _boxed_line(tw, alert_s)

    # ├─── Active Sessions ───┤
    print(_border_line(tw, "Active Sessions"))
    print()  # breathing room

    # Adaptive column layout — hide less-critical columns on narrow terminals
    SP = 2
    hw, pw, dw = 3, 5, 4
    rttw, durw = 11, 8
    type_min = max_type

    show_trend = tw >= 100
    show_throughput = tw >= 90
    spkw = 12 if show_trend else 0
    thrw = 15 if show_throughput else 0

    n_sp = 2 + (1 if show_trend else 0) + (1 if show_throughput else 0)
    fixed = hw + pw + dw + (SP * n_sp) + rttw + spkw + thrw + durw + type_min

    avail_addr = tw - fixed
    if il + ip <= avail_addr:
        lw, prw = il, ip
    else:
        lw = avail_addr // 2
        prw = avail_addr - lw

    if active:
        # Column header
        hdr_parts = [
            f"{'':>{hw}}",
            f"{'PRT':<{pw}}",
            f"{'DIR':<{dw}}",
            f"{'':<{SP}}",
            f"{'LOCAL':<{lw}}",
            f"{'':<{SP}}",
            f"{'PEER':<{prw}}",
            f"{'':<{SP}}",
            f"{'RTT ms':<{rttw}}",
        ]
        if show_trend:
            hdr_parts.append(f"{'TREND':<{spkw}}")
        if show_throughput:
            hdr_parts.append(f"{'':<{SP}}")
            hdr_parts.append(f"{'THROUGHPUT':<{thrw}}")
        hdr_parts.append(f"{'AGE':<{durw}}")
        hdr_parts.append("TYPE")
        print(f"  {DIM}{''.join(hdr_parts)}{R}")
        print(f"  {BORDER}{'╌' * (tw - 4)}{R}")

        for c in active:
            h = c.get('health', '?')
            hd = HEALTH_DOT.get(h, HEALTH_DOT['?'])
            di = DIR_ICONS.get(c['dir'], DIR_ICONS['?'])
            rc = rtt_color(c.get('rtt'))

            rtt_s = f"{rc}{c['rtt']:.1f}/{c['jitter']:.1f}{R}" if c.get('rtt') is not None else f"{DIM}—{R}"

            # Build row with proper ANSI-aware padding
            parts = [
                f" {hd}{R} ",
                f"{c['proto']:<{pw}}",
                ansi_ljust(f"{di}{R}", dw + SP),
                f"{trunc(c['local'], lw):<{lw}}",
                f"{' ' * SP}",
                f"{trunc(c['peer'], prw):<{prw}}",
                f"{' ' * SP}",
                ansi_ljust(rtt_s, rttw),
            ]

            if show_trend:
                spark = render_sparkline(c.get('rtt_hist', []), spkw - 2)
                spark_s = f"{rc}{spark}{R}" if spark else f"{DIM}{'·' * (spkw - 2)}{R}"
                parts.append(ansi_ljust(spark_s, spkw))

            if show_throughput:
                if c.get('tx_rate') is not None:
                    tx_r, rx_r = fmt_rate(c['tx_rate']), fmt_rate(c['rx_rate'])
                    thr_s = f"\033[38;5;114m↑{tx_r}  \033[38;5;75m↓{rx_r}{R}"
                else:
                    thr_s = f"{DIM}—{R}"
                parts.append(f"{' ' * SP}")
                parts.append(ansi_ljust(thr_s, thrw))

            dur_s = f"{DIM}{fmt_duration(c.get('duration', 0))}{R}"
            tc = type_color(c['type'])
            parts.append(ansi_ljust(dur_s, durw))
            parts.append(f"{tc}{c['type']}{R}")

            print("".join(parts))

        print()  # breathing room
    else:
        empty_msg = f"{DIM}○  No active RustDesk sessions{R}"
        print(f"\n  {ansi_center(empty_msg, tw - 4)}\n")

    # ├─── Infrastructure ───┤
    print(_border_line(tw, "Infrastructure"))
    if infra:
        for c in infra:
            port = extract_port(c['local'])
            proto_badge = f"{DIM}{c['proto'].upper()}{R}"
            tc = type_color(c['type'])
            print(f"    {HEALTH_DOT['—']}{R}  {proto_badge}:{LABEL}{port}{R}    {tc}{c['type']}{R}")
    else:
        print(f"    {DIM}No listening sockets{R}")

    # ╰─── Footer ───╯
    print(f"{BORDER}├{'─' * (tw - 2)}┤{R}")
    legend = (
        f"   {HEALTH_DOT['A']}{R} Excellent  "
        f"{HEALTH_DOT['B']}{R} Good  "
        f"{HEALTH_DOT['C']}{R} Fair  "
        f"{HEALTH_DOT['D']}{R} Poor  "
        f"{HEALTH_DOT['F']}{R} Bad"
        f"    {DIM}│{R}    "
        f"{DIR_ICONS['IN']}{R} In   "
        f"{DIR_ICONS['OUT']}{R} Out   "
        f"{DIR_ICONS['P2P']}{R} P2P   "
        f"{DIR_ICONS['LSTN']}{R} Listen"
    )
    print(legend)
    print(f"{BORDER}╰{'─' * (tw - 2)}╯{R}")

# =============================================================================
# Main
# =============================================================================

def main():
    desc = ("RustDesk Connection Monitor v3 — real-time dashboard with throughput,\n"
            "RTT sparklines, health grading, and connection tracking.")
    epilog = (
        "EXAMPLES:\n"
        "  %(prog)s                     Interactive dashboard\n"
        "  %(prog)s -j | jq             JSON snapshot\n"
        "  %(prog)s -j -w 1             NDJSON stream every 1s\n"
        "  %(prog)s -w 0.25             Fast 250ms refresh\n"
        "  %(prog)s --log conn.jsonl    Dashboard + append to log file\n"
        "  %(prog)s -p mydesk           Custom-branded client")

    parser = argparse.ArgumentParser(description=desc, epilog=epilog,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-j", "--json", action="store_true",
                        help="JSON output (single shot, or NDJSON with --watch)")
    parser.add_argument("-w", "--watch", type=float, metavar="SECS",
                        help="Refresh interval (default: 0.5 for TTY)")
    parser.add_argument("-p", "--process-name", default="rustdesk", metavar="NAME",
                        help="Process name to filter (default: rustdesk)")
    parser.add_argument("--log", metavar="FILE",
                        help="Append NDJSON records to FILE alongside dashboard")
    args = parser.parse_args()

    rd_cfg = read_rustdesk_config()
    direct_port = rd_cfg["direct_port"]
    nat_label = NAT_LABELS.get(rd_cfg["nat_type"], "Unknown")
    interval = args.watch if args.watch is not None else 0.5
    tracker = ConnectionTracker()
    log_fh = None

    if args.log:
        try:
            log_fh = open(args.log, "a", buffering=1)
        except IOError as e:
            print(f"Warning: cannot open log file: {e}", file=sys.stderr)

    def make_record(conns):
        export = []
        for c in conns:
            e = dict(c)
            e.pop("color", None)
            e.pop("rtt_hist", None)
            export.append(e)
        return {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "nat_type": nat_label, "direct_port": direct_port,
                "connections": export}

    # --- JSON single-shot ---
    if args.json and args.watch is None:
        conns = tracker.update(parse_connections(args.process_name, direct_port))
        print(json.dumps(make_record(conns), indent=2))
        sys.exit(0)

    # --- NDJSON streaming ---
    if args.json and args.watch is not None:
        try:
            while True:
                conns = tracker.update(parse_connections(args.process_name, direct_port))
                print(json.dumps(make_record(conns)), flush=True)
                time.sleep(interval)
        except KeyboardInterrupt:
            sys.exit(0)

    # --- Interactive dashboard ---
    loop = True
    if args.watch is None and not sys.stdout.isatty():
        loop = False

    while True:
        conns = tracker.update(parse_connections(args.process_name, direct_port))

        if loop and sys.stdout.isatty():
            clear_screen()

        print_dashboard(conns, nat_label, direct_port)

        if log_fh:
            try:
                log_fh.write(json.dumps(make_record(conns)) + "\n")
            except IOError:
                pass

        if not loop:
            break

        print(f"{DIM}  Ctrl+C to exit  │  Refreshing every {interval}s{R}")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nExiting…")
            break

    if log_fh:
        log_fh.close()

if __name__ == "__main__":
    main()
