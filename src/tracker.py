import time

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

def detect_alerts(conns):
    """Return list of alert strings for current state."""
    n_relay = n_rtt = n_retrans = n_queued = 0
    for c in conns:
        if "Relay" in c['type'] and c['dir'] != 'LSTN':
            n_relay += 1
        rtt = c.get('rtt')
        if rtt is not None and rtt > 200:
            n_rtt += 1
        retrans = c.get('retrans')
        if retrans is not None and retrans > 5:
            n_retrans += 1
        try:
            if int(c.get('rx', 0)) > 0 or int(c.get('tx', 0)) > 0:
                n_queued += 1
        except (ValueError, TypeError):
            pass

    alerts = []
    if n_relay:
        alerts.append(f"⚠ {n_relay} relay connection(s) — not direct")
    if n_rtt:
        alerts.append(f"⚠ {n_rtt} connection(s) with RTT >200ms")
    if n_retrans:
        alerts.append(f"⚠ {n_retrans} connection(s) with retransmissions")
    if n_queued:
        alerts.append(f"⚠ {n_queued} connection(s) with queued data")
    return alerts

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

            c['duration'] = now - st['first_seen']

            if c.get('rtt') is not None:
                st['rtt_hist'].append(c['rtt'])
                if len(st['rtt_hist']) > self.spark_depth:
                    st['rtt_hist'] = st['rtt_hist'][-self.spark_depth:]
            c['rtt_hist'] = list(st['rtt_hist'])

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

            c['health'] = compute_health(c)

        for k in [k for k in self._state if k not in seen]:
            del self._state[k]
        return conns
