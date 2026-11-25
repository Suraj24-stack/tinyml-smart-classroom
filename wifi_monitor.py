import re, subprocess, time, math

IFACE = "wlan0"

def _run(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    except Exception: return ""

def raw_stats():
    s = _run(["iw", "dev", IFACE, "station", "dump"])
    g = lambda k: int(m.group(1)) if (m := re.search(k + r":\s*(-?\d+)", s)) else None
    survey = _run(["iw", "dev", IFACE, "survey", "dump"])
    util = None
    for block in survey.split("Survey data"):
        if "[in use]" in block:
            a = re.search(r"channel active time:\s*(\d+)", block)
            b = re.search(r"channel busy time:\s*(\d+)", block)
            if a and b and int(a.group(1)) > 0: util = int(b.group(1)) / int(a.group(1))
    return {"rssi": g("signal"), "tx": g("tx packets"), "rx": g("rx packets"),
            "retries": g("tx retries"), "failed": g("tx failed"), "util": util,
            "connected": bool(s.strip())}

class WifiMonitor:
    """Baseline z-score anomaly detector: learns NORMAL during the first N samples."""
    def __init__(self, baseline_n=30):
        self.prev, self.prev_t = None, None
        self.base, self.n = [], baseline_n
        self.mean = self.std = None
        self.version = "zscore-1.0"

    def features(self):
        r, t = raw_stats(), time.time()
        feat = {"packet_rate": None, "retry_rate": None, "rssi": r["rssi"],
                "mgmt_rate": None, "channel_utilization": r["util"], "connected": r["connected"]}
        if self.prev and r["tx"] is not None and self.prev["tx"] is not None:
            dt = t - self.prev_t
            dtx = r["tx"] - self.prev["tx"]; drx = r["rx"] - self.prev["rx"]
            feat["packet_rate"] = (dtx + drx) / dt if dt > 0 else 0
            feat["retry_rate"] = (r["retries"] - self.prev["retries"]) / dtx if dtx > 0 else 0.0
        self.prev, self.prev_t = r, t
        return feat

    def classify(self, f):
        if not f["connected"]:
            return "SUSPICIOUS_ACTIVITY", 1.0         # unexpected disconnect / deauth
        vec = [f["rssi"] or -90, f["retry_rate"] or 0, f["channel_utilization"] or 0]
        if len(self.base) < self.n:
            self.base.append(vec); return "LEARNING", 0.0
        if self.mean is None:
            cols = list(zip(*self.base))
            self.mean = [sum(c) / len(c) for c in cols]
            self.std = [max(1e-3, math.sqrt(sum((x - m) ** 2 for x in c) / len(c)))
                        for c, m in zip(cols, self.mean)]
        z = [abs(v - m) / s for v, m, s in zip(vec, self.mean, self.std)]
        score = max(z)
        if score > 4 and (vec[1] > self.mean[1] or vec[2] > self.mean[2]):
            return "INTERFERENCE", min(1.0, score / 8)
        return "NORMAL", max(0.0, 1 - score / 4)