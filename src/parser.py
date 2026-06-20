import re
import subprocess
import sys

from src.config import SERVER_PORT_MAP

SS_COMMAND = ["ss", "-tuipn"]

_RE_RTT = re.compile(r"rtt:(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)")
_RE_CWND = re.compile(r"cwnd:(\d+)")
_RE_RETRANS = re.compile(r"retrans:\d+/(\d+)")
_RE_BSENT = re.compile(r"bytes_sent:(\d+)")
_RE_BRECV = re.compile(r"bytes_received:(\d+)")
_RE_PID = re.compile(r"pid=(\d+)")
_RE_PNAME = re.compile(r'users:\(\("([^"]+)"')


def extract_port(addr):
    if addr == "*:*" or addr.endswith(":*"):
        return "*"

    if "]:" in addr:
        return addr.rsplit(":", 1)[-1]

    if ":" in addr:
        return addr.rsplit(":", 1)[-1]

    return ""


def parse_tcp_info(line):
    rtt = jitter = cwnd = retrans = bsent = brecv = None

    m = _RE_RTT.search(line)
    if m:
        rtt = float(m.group(1))
        jitter = float(m.group(2))

    m = _RE_CWND.search(line)
    if m:
        cwnd = int(m.group(1))

    m = _RE_RETRANS.search(line)
    if m:
        retrans = int(m.group(1))

    m = _RE_BSENT.search(line)
    if m:
        bsent = int(m.group(1))

    m = _RE_BRECV.search(line)
    if m:
        brecv = int(m.group(1))

    return rtt, jitter, cwnd, retrans, bsent, brecv


def run_ss():
    try:
        return subprocess.check_output(
            SS_COMMAND,
            universal_newlines=True,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print(
            "\033[1;31mError:\033[0m 'ss' not found. Install iproute2.", file=sys.stderr
        )
        sys.exit(1)
    except subprocess.CalledProcessError:
        return ""


def parse_connections(process_name, direct_port):
    return parse_ss_output(run_ss(), process_name, direct_port)


def parse_ss_output(output, process_name, direct_port):
    conns = []
    lines = output.strip().split("\n")
    pname = process_name.lower()
    i = 0

    while i < len(lines):
        line = lines[i]
        if not _matches_process(line, pname):
            i += 1
            continue

        parts = line.split()
        if len(parts) < 6:
            i += 1
            continue

        tcp_info_line = None
        if _has_tcp_info_line(lines, i):
            tcp_info_line = lines[i + 1]
            i += 1

        conns.append(_parse_socket_parts(parts, tcp_info_line, direct_port))
        i += 1

    return conns


def _matches_process(line, process_name_lower):
    return process_name_lower in line.lower()


def _has_tcp_info_line(lines, index):
    return (
        index + 1 < len(lines)
        and lines[index + 1]
        and lines[index + 1][0] in (" ", "\t")
    )


def _parse_socket_parts(parts, tcp_info_line, direct_port):
    proto, state, rx, tx, local, peer = parts[:6]
    rtt = jitter = cwnd = retrans = bsent = brecv = None

    if tcp_info_line is not None:
        rtt, jitter, cwnd, retrans, bsent, brecv = parse_tcp_info(tcp_info_line)

    local_port = extract_port(local)
    peer_port = extract_port(peer)
    direction, conn_type, color = classify_connection(
        proto,
        state,
        local_port,
        peer_port,
        direct_port,
    )
    pid, pname = parse_process_info(parts[6:])

    return {
        "proto": proto,
        "state": state,
        "rx": rx,
        "tx": tx,
        "dir": direction,
        "local": local,
        "peer": peer,
        "pid": pid,
        "pname": pname,
        "type": conn_type,
        "color": color,
        "rtt": rtt,
        "jitter": jitter,
        "cwnd": cwnd,
        "retrans": retrans,
        "bytes_sent": bsent,
        "bytes_received": brecv,
    }


def classify_connection(proto, state, local_port, peer_port, direct_port):
    if state in ("LISTEN", "UNCONN"):
        return _classify_listener(local_port, direct_port)

    if local_port == direct_port and state == "ESTAB":
        return "IN", "Direct (Incoming Peer)", "\033[1;32m"

    if peer_port in SERVER_PORT_MAP:
        server = SERVER_PORT_MAP[peer_port]
        return "OUT", server["type"], server["color"]

    if proto == "udp" and peer_port not in ("*", ""):
        return "P2P", "Direct (UDP Hole-Punch)", "\033[1;32m"

    conn_type = "Direct (TCP P2P)" if proto == "tcp" else "Unknown"
    color = "\033[1;32m" if proto == "tcp" else "\033[0m"
    return "P2P", conn_type, color


def _classify_listener(local_port, direct_port):
    if local_port == direct_port:
        return "LSTN", "Direct Access (Listening)", "\033[1;32m"

    if local_port == "21116":
        return "LSTN", "Rendezvous (Listening)", "\033[1;34m"

    if local_port == "21118" and local_port != direct_port:
        return "LSTN", "WS Rendezvous (Listening)", "\033[1;36m"

    return "LSTN", "Service (Listening)", "\033[38;5;245m"


def parse_process_info(proc_parts):
    proc_blob = "".join(proc_parts) if proc_parts else ""
    pid = ""
    pname = ""

    m_pid = _RE_PID.search(proc_blob)
    if m_pid:
        pid = m_pid.group(1)

    m_pname = _RE_PNAME.search(proc_blob)
    if m_pname:
        pname = m_pname.group(1)

    return pid, pname
