import re
import shutil
import sys
import time

from src.parser import extract_port
from src.tracker import detect_alerts

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

HEALTH_DOT = {
    'A': "\033[38;5;84m●",  'B': "\033[38;5;114m●",  'C': "\033[38;5;220m●",
    'D': "\033[38;5;208m●", 'F': "\033[38;5;196m●",  '?': "\033[38;5;242m○",
    '—': "\033[38;5;242m·",
}

DIR_ICONS = {
    'IN':  "\033[38;5;84m▼",   'OUT': "\033[38;5;75m▲",
    'P2P': "\033[38;5;183m⇄",  'LSTN': "\033[38;5;242m◉",
    '?':   "\033[38;5;242m·",
}

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
    if bps is None: return "—"
    if bps < 1024: return f"{bps:.0f}B"
    if bps < 1024 * 1024: return f"{bps/1024:.1f}K"
    return f"{bps/1024/1024:.1f}M"

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
    return len(re.sub(r'\033\[[0-9;]*m', '', s))

def ansi_ljust(s, width):
    pad = width - ansi_len(s)
    return s + (' ' * pad) if pad > 0 else s

def ansi_center(s, width):
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
    return s[:h] + "..." + s[-(mx - 3 - h):]

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

def print_dashboard(conns, nat_label, direct_port):
    raw_tw = shutil.get_terminal_size((120, 20)).columns

    active = [c for c in conns if c['dir'] != 'LSTN']
    infra = [c for c in conns if c['dir'] == 'LSTN']

    il = max([len(c['local']) for c in active] + [5]) + 1 if active else 6
    ip = max([len(c['peer']) for c in active] + [4]) + 1 if active else 5
    max_type = max([len(c['type']) for c in active] + [16]) if active else 16

    fixed_cols_width = 3 + 5 + 4 + 8 + 11 + 12 + 15 + 8 + max_type
    needed_tw = fixed_cols_width + il + ip

    tw = min(raw_tw, max(110, needed_tw))

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

    d_n = 0
    r_n = 0
    rn_n = 0
    rtts = []
    for c in active:
        ctype = c['type']
        if "Direct" in ctype:
            d_n += 1
        elif "Relay" in ctype:
            r_n += 1
        elif "Rendezvous" in ctype:
            rn_n += 1
        rtt = c.get('rtt')
        if rtt is not None:
            rtts.append(rtt)

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

    alerts = detect_alerts(conns)
    if alerts:
        print(f"{BORDER}├{'─' * (tw - 2)}┤{R}")
        for a in alerts:
            alert_s = f"{ALERT_BG}{B} {a} {R}"
            _boxed_line(tw, alert_s)

    print(_border_line(tw, "Active Sessions"))
    print()

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

        print()
    else:
        empty_msg = f"{DIM}○  No active RustDesk sessions{R}"
        print(f"\n  {ansi_center(empty_msg, tw - 4)}\n")

    print(_border_line(tw, "Infrastructure"))
    if infra:
        for c in infra:
            port = extract_port(c['local'])
            proto_badge = f"{DIM}{c['proto'].upper()}{R}"
            tc = type_color(c['type'])
            print(f"    {HEALTH_DOT['—']}{R}  {proto_badge}:{LABEL}{port}{R}    {tc}{c['type']}{R}")
    else:
        print(f"    {DIM}No listening sockets{R}")

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
