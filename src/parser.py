import re
import subprocess
import sys

from src.config import SERVER_PORT_MAP

def extract_port(addr):
    if addr in ("*:*",) or addr.endswith(":*"): return "*"
    if "]:" in addr: return addr.rsplit(":", 1)[-1]
    return addr.rsplit(":", 1)[-1] if ":" in addr else ""

_RE_RTT = re.compile(r'rtt:(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)')
_RE_CWND = re.compile(r'cwnd:(\d+)')
_RE_RETRANS = re.compile(r'retrans:\d+/(\d+)')
_RE_BSENT = re.compile(r'bytes_sent:(\d+)')
_RE_BRECV = re.compile(r'bytes_received:(\d+)')

def parse_tcp_info(line):
    rtt = jitter = cwnd = retrans = bsent = brecv = None
    m = _RE_RTT.search(line)
    if m: rtt, jitter = float(m.group(1)), float(m.group(2))
    m = _RE_CWND.search(line)
    if m: cwnd = int(m.group(1))
    m = _RE_RETRANS.search(line)
    if m: retrans = int(m.group(1))
    m = _RE_BSENT.search(line)
    if m: bsent = int(m.group(1))
    m = _RE_BRECV.search(line)
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
        m_pid = re.search(r'pid=(\d+)', proc_blob)
        if m_pid: pid = m_pid.group(1)
        m_pname = re.search(r'users:\(\("([^"]+)"', proc_blob)
        if m_pname: pname_parsed = m_pname.group(1)

        conns.append({
            "proto": proto, "state": state, "rx": rx, "tx": tx,
            "dir": direction, "local": local, "peer": peer,
            "pid": pid, "pname": pname_parsed, "type": conn_type, "color": color,
            "rtt": rtt, "jitter": jitter, "cwnd": cwnd, "retrans": retrans,
            "bytes_sent": bsent, "bytes_received": brecv,
        })
        i += 1
    return conns
