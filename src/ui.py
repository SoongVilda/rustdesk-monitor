import re
import shutil
import sys
import time

from src.parser import extract_port
from src.tracker import detect_alerts

ANSI_RE = re.compile(r"\033\[[0-9;]*m")
SPARK_CHARS = "▁▂▃▄▅▆▇█"

R = "\033[0m"
B = "\033[1m"
DIM = "\033[38;5;242m"
BORDER = "\033[38;5;60m"
HDR_BG = "\033[48;5;236m\033[38;5;75m"
ALERT_BG = "\033[48;5;52m\033[38;5;196m"
LABEL = "\033[38;5;75m"
VAL = "\033[1;38;5;255m"

HEALTH_DOT = {
    "A": "\033[38;5;84m●",
    "B": "\033[38;5;114m●",
    "C": "\033[38;5;220m●",
    "D": "\033[38;5;208m●",
    "F": "\033[38;5;196m●",
    "?": "\033[38;5;242m○",
    "—": "\033[38;5;242m·",
}

DIR_ICONS = {
    "IN": "\033[38;5;84m▼",
    "OUT": "\033[38;5;75m▲",
    "P2P": "\033[38;5;183m⇄",
    "LSTN": "\033[38;5;242m◉",
    "?": "\033[38;5;242m·",
}

TYPE_COLORS = {
    "Direct": "\033[38;5;84m",
    "Relay": "\033[38;5;196m",
    "Rendezvous": "\033[38;5;75m",
    "API": "\033[38;5;183m",
    "WS": "\033[38;5;117m",
    "Service": "\033[38;5;242m",
}


def render_sparkline(values, width=10):
    if not values:
        return ""

    vals = values[-width:]
    lo = min(vals)
    hi = max(vals)
    span = hi - lo if hi > lo else 1
    out = ""

    for v in vals:
        idx = int((v - lo) / span * (len(SPARK_CHARS) - 1))
        out += SPARK_CHARS[min(idx, len(SPARK_CHARS) - 1)]

    return out


def rtt_color(rtt):
    if rtt is None:
        return "\033[38;5;242m"
    if rtt < 20:
        return "\033[38;5;84m"
    if rtt < 80:
        return "\033[38;5;220m"
    return "\033[38;5;196m"


def type_color(conn_type):
    for key, color in TYPE_COLORS.items():
        if key in conn_type:
            return color
    return "\033[0m"


def fmt_duration(secs):
    if secs < 60:
        return f"{int(secs)}s"
    if secs < 3600:
        return f"{int(secs // 60)}m{int(secs % 60)}s"

    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    return f"{h}h{m}m"


def fmt_rate(bps):
    if bps is None:
        return "—"
    if bps < 1024:
        return f"{bps:.0f}B"
    if bps < 1024 * 1024:
        return f"{bps / 1024:.1f}K"
    return f"{bps / 1024 / 1024:.1f}M"


def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def ansi_len(s):
    return len(ANSI_RE.sub("", s))


def ansi_ljust(s, width):
    pad = width - ansi_len(s)
    if pad > 0:
        return s + (" " * pad)
    return s


def ansi_center(s, width):
    pad = width - ansi_len(s)
    if pad <= 0:
        return s

    left = pad // 2
    return " " * left + s + " " * (pad - left)


def trunc(s, w):
    if w <= 1:
        return ""

    mx = w - 1
    if len(s) <= mx:
        return s
    if mx < 10:
        return s[:mx]

    h = (mx - 3) // 2
    return s[:h] + "..." + s[-(mx - 3 - h) :]


def _border_line(tw, title="", char="─"):
    iw = tw - 2
    if not title:
        return f"{BORDER}├{char * iw}┤{R}"

    tlen = len(title) + 2
    pad = (iw - tlen - 2) // 2
    rem = iw - pad - tlen - 2
    return f"{BORDER}├{char * pad}┤{R} {B}{title}{R} {BORDER}├{char * rem}┤{R}"


def _boxed_line(tw, content):
    iw = tw - 4
    print(f"{BORDER}│{R} {ansi_center(content, iw)} {BORDER}│{R}")


def _stat_pill(label, value, color=VAL):
    return f"{LABEL}{label} {color}{value}{R}"


def _partition_connections(conns):
    active = [c for c in conns if c["dir"] != "LSTN"]
    infra = [c for c in conns if c["dir"] == "LSTN"]
    return active, infra


def _dashboard_dimensions(raw_tw, active):
    il = max([len(c["local"]) for c in active] + [5]) + 1 if active else 6
    ip = max([len(c["peer"]) for c in active] + [4]) + 1 if active else 5
    max_type = max([len(c["type"]) for c in active] + [16]) if active else 16

    fixed_cols_width = 3 + 5 + 4 + 8 + 11 + 12 + 15 + 8 + max_type
    needed_tw = fixed_cols_width + il + ip
    tw = min(raw_tw, max(110, needed_tw))

    return tw, il, ip, max_type


def _print_dashboard_header(tw):
    print(f"{BORDER}╭{'─' * (tw - 2)}╮{R}")

    clock = time.strftime("%H:%M:%S")
    title = "RustDesk Connection Monitor"
    title_s = f"{HDR_BG} {title} {R}"
    clock_s = f"{DIM}{clock}{R}"
    iw = tw - 4
    used = len(title) + 2 + len(clock)
    gap = iw - used
    left = gap // 2
    right = gap - left

    print(f"{BORDER}│{R} {' ' * left}{title_s}{' ' * right}{clock_s} {BORDER}│{R}")
    print(f"{BORDER}├{'─' * (tw - 2)}┤{R}")


def _connection_summary(active):
    direct_count = 0
    relay_count = 0
    rendezvous_count = 0
    rtts = []

    for c in active:
        ctype = c["type"]
        if "Direct" in ctype:
            direct_count += 1
        elif "Relay" in ctype:
            relay_count += 1
        elif "Rendezvous" in ctype:
            rendezvous_count += 1

        rtt = c.get("rtt")
        if rtt is not None:
            rtts.append(rtt)

    return direct_count, relay_count, rendezvous_count, rtts


def _print_summary(tw, active, nat_label, direct_port):
    direct_count, relay_count, rendezvous_count, rtts = _connection_summary(active)
    pills = [
        _stat_pill("Sessions:", str(len(active))),
        _stat_pill(
            "Direct:", str(direct_count), "\033[38;5;84m" if direct_count else VAL
        ),
        _stat_pill(
            "Relay:", str(relay_count), "\033[38;5;196m" if relay_count else VAL
        ),
        _stat_pill("Rend:", str(rendezvous_count)),
        _stat_pill("NAT:", nat_label),
    ]

    if rtts:
        avg = sum(rtts) / len(rtts)
        pills.append(_stat_pill("Avg RTT:", f"{avg:.1f}ms", rtt_color(avg)))

    _boxed_line(tw, "  │  ".join(pills))

    if direct_port != "21118":
        _boxed_line(tw, f"{DIM}Direct Port: {direct_port} (custom){R}")


def _print_alerts(tw, conns):
    alerts = detect_alerts(conns)
    if not alerts:
        return

    print(f"{BORDER}├{'─' * (tw - 2)}┤{R}")
    for alert in alerts:
        _boxed_line(tw, f"{ALERT_BG}{B} {alert} {R}")


def _active_layout(tw, il, ip, max_type):
    sp = 2
    hw = 3
    pw = 5
    dw = 4
    rttw = 11
    durw = 8
    type_min = max_type

    show_trend = tw >= 100
    show_throughput = tw >= 90
    spkw = 12 if show_trend else 0
    thrw = 15 if show_throughput else 0

    n_sp = 2 + (1 if show_trend else 0) + (1 if show_throughput else 0)
    fixed = hw + pw + dw + (sp * n_sp) + rttw + spkw + thrw + durw + type_min

    avail_addr = tw - fixed
    if il + ip <= avail_addr:
        lw = il
        prw = ip
    else:
        lw = avail_addr // 2
        prw = avail_addr - lw

    return {
        "sp": sp,
        "hw": hw,
        "pw": pw,
        "dw": dw,
        "rttw": rttw,
        "durw": durw,
        "show_trend": show_trend,
        "show_throughput": show_throughput,
        "spkw": spkw,
        "thrw": thrw,
        "lw": lw,
        "prw": prw,
    }


def _active_header(layout):
    sp = layout["sp"]
    hdr_parts = [
        f"{'':>{layout['hw']}}",
        f"{'PRT':<{layout['pw']}}",
        f"{'DIR':<{layout['dw']}}",
        f"{'':<{sp}}",
        f"{'LOCAL':<{layout['lw']}}",
        f"{'':<{sp}}",
        f"{'PEER':<{layout['prw']}}",
        f"{'':<{sp}}",
        f"{'RTT ms':<{layout['rttw']}}",
    ]

    if layout["show_trend"]:
        hdr_parts.append(f"{'TREND':<{layout['spkw']}}")

    if layout["show_throughput"]:
        hdr_parts.append(f"{'':<{sp}}")
        hdr_parts.append(f"{'THROUGHPUT':<{layout['thrw']}}")

    hdr_parts.append(f"{'AGE':<{layout['durw']}}")
    hdr_parts.append("TYPE")
    return "".join(hdr_parts)


def _rtt_text(c, color):
    if c.get("rtt") is not None:
        return f"{color}{c['rtt']:.1f}/{c['jitter']:.1f}{R}"
    return f"{DIM}—{R}"


def _trend_text(c, color, width):
    spark = render_sparkline(c.get("rtt_hist", []), width - 2)
    if spark:
        return f"{color}{spark}{R}"
    return f"{DIM}{'·' * (width - 2)}{R}"


def _throughput_text(c):
    if c.get("tx_rate") is not None:
        tx_r = fmt_rate(c["tx_rate"])
        rx_r = fmt_rate(c["rx_rate"])
        return f"\033[38;5;114m↑{tx_r}  \033[38;5;75m↓{rx_r}{R}"
    return f"{DIM}—{R}"


def _active_row(c, layout):
    sp = layout["sp"]
    color = rtt_color(c.get("rtt"))
    health = c.get("health", "?")
    health_dot = HEALTH_DOT.get(health, HEALTH_DOT["?"])
    dir_icon = DIR_ICONS.get(c["dir"], DIR_ICONS["?"])

    parts = [
        f" {health_dot}{R} ",
        f"{c['proto']:<{layout['pw']}}",
        ansi_ljust(f"{dir_icon}{R}", layout["dw"] + sp),
        f"{trunc(c['local'], layout['lw']):<{layout['lw']}}",
        f"{' ' * sp}",
        f"{trunc(c['peer'], layout['prw']):<{layout['prw']}}",
        f"{' ' * sp}",
        ansi_ljust(_rtt_text(c, color), layout["rttw"]),
    ]

    if layout["show_trend"]:
        parts.append(ansi_ljust(_trend_text(c, color, layout["spkw"]), layout["spkw"]))

    if layout["show_throughput"]:
        parts.append(f"{' ' * sp}")
        parts.append(ansi_ljust(_throughput_text(c), layout["thrw"]))

    dur_s = f"{DIM}{fmt_duration(c.get('duration', 0))}{R}"
    parts.append(ansi_ljust(dur_s, layout["durw"]))
    parts.append(f"{type_color(c['type'])}{c['type']}{R}")

    return "".join(parts)


def _print_active_table(tw, active, layout):
    print(f"  {DIM}{_active_header(layout)}{R}")
    print(f"  {BORDER}{'╌' * (tw - 4)}{R}")

    for c in active:
        print(_active_row(c, layout))


def _print_active_sessions(tw, active, il, ip, max_type):
    print(_border_line(tw, "Active Sessions"))
    print()

    layout = _active_layout(tw, il, ip, max_type)
    if active:
        _print_active_table(tw, active, layout)
        print()
        return

    empty_msg = f"{DIM}○  No active RustDesk sessions{R}"
    print(f"\n  {ansi_center(empty_msg, tw - 4)}\n")


def _print_infrastructure(tw, infra):
    print(_border_line(tw, "Infrastructure"))
    if infra:
        for c in infra:
            port = extract_port(c["local"])
            proto_badge = f"{DIM}{c['proto'].upper()}{R}"
            tc = type_color(c["type"])
            print(
                f"    {HEALTH_DOT['—']}{R}  {proto_badge}:{LABEL}{port}{R}    "
                f"{tc}{c['type']}{R}"
            )
    else:
        print(f"    {DIM}No listening sockets{R}")


def _print_legend(tw):
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


def print_dashboard(conns, nat_label, direct_port):
    raw_tw = shutil.get_terminal_size((120, 20)).columns
    active, infra = _partition_connections(conns)
    tw, il, ip, max_type = _dashboard_dimensions(raw_tw, active)

    _print_dashboard_header(tw)
    _print_summary(tw, active, nat_label, direct_port)
    _print_alerts(tw, conns)
    _print_active_sessions(tw, active, il, ip, max_type)
    _print_infrastructure(tw, infra)
    _print_legend(tw)
