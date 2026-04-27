from datetime import datetime, time

from surmount.base_class import Strategy, TargetAllocation
from surmount.logging import log


class TradingStrategy(Strategy):
    """Opening Range Breakout on SPY, expressed 3x via SPXL (long) / SPXS (short).

    - Signal source: SPY 5-minute candles.
    - Opening range: first 30 minutes (6 x 5-min bars).
    - Once a breakout occurs, stays in that direction until an opposite
      breakout or the 15:55 flatten time.
    - Stateless: direction is derived from scanning the current session's bars
      each tick, so the strategy behaves identically whether the instance is
      reused or re-instantiated each call.
    """

    @property
    def assets(self):
        return ["SPY", "SPXL", "SPXS"]

    @property
    def interval(self):
        return "5min"

    def _parse_bar_time(self, raw):
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw
        value = str(raw).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    def run(self, data):
        flat = {"SPXL": 0.0, "SPXS": 0.0, "SPY": 0.0}

        ohlcv = data.get("ohlcv") if isinstance(data, dict) else None
        if not ohlcv:
            return TargetAllocation(flat)

        opening_range_bars = 6
        breakout_buffer = 0.0
        flat_time = time(15, 55)

        # Pull SPY bars with parsed timestamps
        spy_bars = []
        for row in ohlcv:
            if not isinstance(row, dict):
                continue
            bar = row.get("SPY")
            if not bar:
                continue
            ts = self._parse_bar_time(bar.get("date"))
            if ts is None:
                continue
            spy_bars.append((ts, bar))

        if not spy_bars:
            return TargetAllocation(flat)

        # Restrict to the most recent session only
        latest_ts = spy_bars[-1][0]
        session_date = latest_ts.date()
        todays = [(ts, b) for ts, b in spy_bars if ts.date() == session_date]

        # Flatten near close
        if latest_ts.time() >= flat_time:
            return TargetAllocation(flat)

        if len(todays) < opening_range_bars:
            return TargetAllocation(flat)

        opening_slice = [b for _, b in todays[:opening_range_bars]]
        opening_high = max(float(b["high"]) for b in opening_slice)
        opening_low = min(float(b["low"]) for b in opening_slice)

        # Replay post-opening-range bars to determine current direction.
        # The last breakout wins; absence of any breakout keeps us flat.
        direction = None
        for _, b in todays[opening_range_bars:]:
            close_px = float(b["close"])
            if close_px > opening_high + breakout_buffer:
                direction = "long"
            elif close_px < opening_low - breakout_buffer:
                direction = "short"

        if direction == "long":
            return TargetAllocation({"SPXL": 1.0, "SPXS": 0.0, "SPY": 0.0})
        if direction == "short":
            return TargetAllocation({"SPXL": 0.0, "SPXS": 1.0, "SPY": 0.0})

        return TargetAllocation(flat)