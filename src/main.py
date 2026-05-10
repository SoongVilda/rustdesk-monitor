import argparse
import json
import sys
import time

from src.config import read_rustdesk_config, NAT_LABELS
from src.parser import parse_connections
from src.tracker import ConnectionTracker
from src.ui import print_dashboard, clear_screen, DIM, R

def main():
    desc = ("RustDesk Connection Monitor v4.0 — real-time dashboard with throughput,\n"
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
    if interval < 0.1:
        interval = 0.1
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

    if args.json and args.watch is None:
        conns = tracker.update(parse_connections(args.process_name, direct_port))
        print(json.dumps(make_record(conns), indent=2))
        sys.exit(0)

    if args.json and args.watch is not None:
        try:
            while True:
                conns = tracker.update(parse_connections(args.process_name, direct_port))
                print(json.dumps(make_record(conns)), flush=True)
                time.sleep(interval)
        except KeyboardInterrupt:
            sys.exit(0)

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
