import argparse
import json
import sys
import time

from src.config import NAT_LABELS, read_rustdesk_config
from src.parser import parse_connections
from src.tracker import ConnectionTracker
from src.ui import DIM, R, clear_screen, print_dashboard


def build_arg_parser():
    desc = (
        "RustDesk Connection Monitor v4.0 — real-time dashboard with throughput,\n"
        "RTT sparklines, health grading, and connection tracking."
    )
    epilog = (
        "EXAMPLES:\n"
        "  %(prog)s                     Interactive dashboard\n"
        "  %(prog)s -j | jq             JSON snapshot\n"
        "  %(prog)s -j -w 1             NDJSON stream every 1s\n"
        "  %(prog)s -w 0.25             Fast 250ms refresh\n"
        "  %(prog)s --log conn.jsonl    Dashboard + append to log file\n"
        "  %(prog)s -p mydesk           Custom-branded client"
    )

    parser = argparse.ArgumentParser(
        description=desc,
        epilog=epilog,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="JSON output (single shot, or NDJSON with --watch)",
    )
    parser.add_argument(
        "-w",
        "--watch",
        type=float,
        metavar="SECS",
        help="Refresh interval (default: 0.5 for TTY)",
    )
    parser.add_argument(
        "-p",
        "--process-name",
        default="rustdesk",
        metavar="NAME",
        help="Process name to filter (default: rustdesk)",
    )
    parser.add_argument(
        "--log",
        metavar="FILE",
        help="Append NDJSON records to FILE alongside dashboard",
    )
    return parser


def parse_args(argv=None):
    return build_arg_parser().parse_args(argv)


def load_runtime_config():
    rd_cfg = read_rustdesk_config()
    direct_port = str(rd_cfg["direct_port"])
    nat_type = rd_cfg["nat_type"]

    if isinstance(nat_type, int):
        nat_label = NAT_LABELS.get(nat_type, "Unknown")
    else:
        nat_label = "Unknown"

    return direct_port, nat_label


def refresh_interval(watch):
    interval = watch if watch is not None else 0.5
    if interval < 0.1:
        interval = 0.1
    return interval


def open_log_file(path):
    if not path:
        return None

    try:
        return open(path, "a", buffering=1, encoding="utf-8")
    except IOError as e:
        print(f"Warning: cannot open log file: {e}", file=sys.stderr)
        return None


def export_connections(conns):
    export = []
    for c in conns:
        e = dict(c)
        e.pop("color", None)
        e.pop("rtt_hist", None)
        export.append(e)
    return export


def make_record(conns, nat_label, direct_port):
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "nat_type": nat_label,
        "direct_port": direct_port,
        "connections": export_connections(conns),
    }


def collect_connections(tracker, process_name, direct_port):
    return tracker.update(parse_connections(process_name, direct_port))


def run_json_once(args, tracker, nat_label, direct_port):
    conns = collect_connections(tracker, args.process_name, direct_port)
    print(json.dumps(make_record(conns, nat_label, direct_port), indent=2))
    sys.exit(0)


def run_json_watch(args, tracker, nat_label, direct_port, interval):
    try:
        while True:
            conns = collect_connections(tracker, args.process_name, direct_port)
            print(json.dumps(make_record(conns, nat_label, direct_port)), flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        sys.exit(0)


def should_loop_dashboard(args):
    return args.watch is not None or sys.stdout.isatty()


def write_log_record(log_fh, conns, nat_label, direct_port):
    if not log_fh:
        return

    try:
        log_fh.write(json.dumps(make_record(conns, nat_label, direct_port)) + "\n")
    except IOError:
        pass


def run_dashboard(args, tracker, nat_label, direct_port, interval, log_fh):
    loop = should_loop_dashboard(args)

    try:
        while True:
            conns = collect_connections(tracker, args.process_name, direct_port)

            if loop and sys.stdout.isatty():
                clear_screen()

            print_dashboard(conns, nat_label, direct_port)
            write_log_record(log_fh, conns, nat_label, direct_port)

            if not loop:
                break

            print(f"{DIM}  Ctrl+C to exit  │  Refreshing every {interval}s{R}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nExiting…")
    finally:
        if log_fh:
            log_fh.close()


def main():
    args = parse_args()
    direct_port, nat_label = load_runtime_config()
    interval = refresh_interval(args.watch)
    tracker = ConnectionTracker()
    log_fh = open_log_file(args.log)

    if args.json and args.watch is None:
        run_json_once(args, tracker, nat_label, direct_port)

    if args.json and args.watch is not None:
        run_json_watch(args, tracker, nat_label, direct_port, interval)

    run_dashboard(args, tracker, nat_label, direct_port, interval, log_fh)


if __name__ == "__main__":
    main()
