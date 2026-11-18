"""Forecaster for make.fun's gta6-twitch-ccu-forecast-01.

Reads every case file (<id>.in, schema makefun/twitch-ccu-case/v1) in the input
directory and writes <id>.out: for each hour 2..24 of the case's release day,
five quantiles (0.05, 0.25, 0.5, 0.75, 0.95) of that hour's Twitch viewer
count for the game's category. Python 3.13, standard library only, no network,
deterministic: the same case always yields the same bytes.

Method
------
A console game that unlocks at midnight local time, rolling around the world,
draws a characteristic UTC-day curve: New Zealand and then Europe are already
playing before the UTC day begins, hour 1 (00:00-01:00 UTC) is a lull with the
UK just in and the US still locked, and the count climbs through the European
evening and the US unlocks to a peak late in the day. Every case carries the
hourly curves of dozens of past launches (its `comparables`), all framed on
the same UTC release day, so the shape is estimated from them, not assumed:

* each comparable with a usable release day contributes its log-ratio curve
  r(h) = ln(viewers_h) - ln(viewers_1), h = 1..24;
* comparables are weighted by similarity to the case: the log of hour 1's
  viewers and channels (scale), the "eve ratio" ln(viewers at 23:00 the day
  before / viewers_1) and the pre-day ramp (how fast the audience was already
  arriving in the last hours before the day), which together separate
  rolling-midnight launches from simultaneous-global ones (whose hour 1 is
  near zero and whose curve explodes) and from early-access launches (whose
  release day is already past its peak). The free-text `unlock` note of each
  comparable is also read for those markers and for the kit's own tier notes;
* the median for hour h is hour 1's print times exp(weighted mean of r(h)),
  with each hour's ratios lightly trimmed toward the weighted median first;
* the spread for hour h is the weighted standard deviation of the
  comparables' r(h) around that mean, floored and smoothed across hours, and
  the quantiles are median * exp(z_tau * spread) with the standard normal's z
  at each level: pinball loss on the log scale rewards exactly this, a
  geometric centre with honest log-symmetric uncertainty.

The case's own history is used only through the same summary features, so a
practice case and the final are handled by one path.
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level, fuller precision than the kit's.
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]

# --- tuning constants (calibrated on the kit's practice cases and on
# leave-one-out pseudo-cases built from their comparables) ---
# Gaussian-kernel scales for the similarity features, in each feature's units.
SCALE_LOG_V1 = 1.00        # ln(hour-1 viewers)
SCALE_LOG_CH1 = 1.10       # ln(hour-1 channels)
SCALE_EVE = 0.42           # ln(viewers 23:00 eve / viewers hour 1)
SCALE_RAMP = 2.00          # ln(viewers eve / viewers 7h before eve)
KERNEL_FLOOR = 1e-6        # numerical guard only: weights are normalised
TIER_WEAK = 0.30           # kit tier "weak" analogue
TIER_EARLY_ACCESS = 0.50   # early-access / simultaneous-unlock launches
TRIM_SD = 2.2              # per-hour winsorising of log-ratios, in weighted SDs
SPREAD_FLOOR = 0.16        # smallest log spread at any hour
SPREAD_SCALE = 1.00        # global calibration multiplier on the spread
SPREAD_SQRT_BLEND = 0.35   # blend the residual spread with a sqrt-hour floor


def parse_ts(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def round2(x):
    """Round to 2 decimals, half up; whole numbers come back as int for compact JSON."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if float(value).is_integer() else value


class LaunchCurve:
    """One launch's release day, framed on its UTC day_start, plus shape features."""

    __slots__ = ("name", "day", "eve_log_ratio", "ramp", "unlock_text")

    def __init__(self, name, day, eve_log_ratio, ramp, unlock_text):
        self.name = name
        self.day = day  # {hour 1..24: (viewers, channels or None)}
        self.eve_log_ratio = eve_log_ratio  # ln(v at day_start-1h) - ln(v hour 1) or None
        self.ramp = ramp  # ln(v at day_start-1h) - ln(v at day_start-7h) or None
        self.unlock_text = unlock_text

    @property
    def v1(self):
        return self.day[1][0]

    @property
    def ch1(self):
        return self.day[1][1]

    def log_ratio(self, hour):
        viewers = self.day[hour][0]
        return math.log(viewers) - math.log(self.v1)


def build_curve(name, day_start_text, hourly, unlock_text):
    """Frame an hourly series on its release day; None when the day is unusable."""
    start = parse_ts(day_start_text)
    by_offset = {}
    for point in hourly:
        viewers = point.get("viewers")
        if viewers is None:
            continue
        offset = (parse_ts(point["from"]) - start).total_seconds() / 3600.0
        if offset == int(offset):
            by_offset[int(offset)] = (float(viewers), point.get("channels"))
    if 0 not in by_offset or not by_offset[0][0] or by_offset[0][0] < 1:
        return None
    day = {offset + 1: by_offset[offset] for offset in range(0, 24) if offset in by_offset}
    if len(day) < 21:  # hour 1 plus at least 20 of hours 2..24
        return None
    v1 = by_offset[0][0]

    def log_at(offset):
        point = by_offset.get(offset)
        if point is None or not point[0] or point[0] < 1:
            return None
        return math.log(point[0])

    eve = log_at(-1)
    eve_log_ratio = (eve - math.log(v1)) if eve is not None else None
    earlier = log_at(-7)
    ramp = (eve - earlier) if (eve is not None and earlier is not None) else None
    return LaunchCurve(name, day, eve_log_ratio, ramp, unlock_text or "")


def case_reference(case):
    """The case itself as a LaunchCurve-like reference: hour 1 known, eve from history."""
    start = parse_ts(case["day_start"])
    first = next(k for k in case["known"] if k["hour"] == 1)
    v1 = max(1.0, float(first["viewers"]))
    ch1 = first.get("channels")
    by_offset = {}
    for point in case.get("history_hourly") or []:
        viewers = point.get("viewers")
        if viewers is None:
            continue
        offset = (parse_ts(point["from"]) - start).total_seconds() / 3600.0
        if offset == int(offset):
            by_offset[int(offset)] = (float(viewers), point.get("channels"))

    def log_at(offset):
        point = by_offset.get(offset)
        if point is None or not point[0] or point[0] < 1:
            return None
        return math.log(point[0])

    eve = log_at(-1)
    eve_log_ratio = (eve - math.log(v1)) if eve is not None else None
    earlier = log_at(-7)
    ramp = (eve - earlier) if (eve is not None and earlier is not None) else None
    ref = LaunchCurve(case["game"]["name"], {1: (v1, ch1)}, eve_log_ratio, ramp, case.get("notes", ""))
    return ref


def similarity_weight(ref, curve):
    """Gaussian kernel over the shape features, times tier factors from the notes."""
    terms = []
    terms.append(((math.log(ref.v1) - math.log(curve.v1)) / SCALE_LOG_V1) ** 2)
    if ref.ch1 and curve.ch1:
        terms.append(((math.log(ref.ch1) - math.log(curve.ch1)) / SCALE_LOG_CH1) ** 2)
    if ref.eve_log_ratio is not None and curve.eve_log_ratio is not None:
        terms.append(((ref.eve_log_ratio - curve.eve_log_ratio) / SCALE_EVE) ** 2)
    if ref.ramp is not None and curve.ramp is not None:
        terms.append(((ref.ramp - curve.ramp) / SCALE_RAMP) ** 2)
    weight = math.exp(-0.5 * sum(terms)) + KERNEL_FLOOR
    text = curve.unlock_text.lower()
    if "tier: weak" in text or "tier: target-history" in text:
        weight *= TIER_WEAK
    if "early access" in text or "early-access" in text:
        weight *= TIER_EARLY_ACCESS
    if "simultaneous" in text or "single global unlock" in text or "single simultaneous" in text:
        weight *= TIER_EARLY_ACCESS
    return weight


def weighted_mean_sd(pairs):
    """pairs of (value, weight) -> (weighted mean, weighted sd)."""
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return 0.0, 0.5
    mean = sum(v * w for v, w in pairs) / total_w
    var = sum(w * (v - mean) ** 2 for v, w in pairs) / total_w
    return mean, math.sqrt(var)


def pooled_curve(ref, curves):
    """Per hour 2..24: (median log-ratio, log spread) pooled from the comparables."""
    weights = {id(c): similarity_weight(ref, c) for c in curves}
    medians = {}
    spreads = {}
    for hour in range(2, 25):
        pairs = [(c.log_ratio(hour), weights[id(c)]) for c in curves if hour in c.day]
        if not pairs:
            medians[hour] = medians.get(hour - 1, 0.0)
            spreads[hour] = spreads.get(hour - 1, 0.5)
            continue
        # Winsorise toward the weighted median so one wild launch cannot drag an hour.
        ordered = sorted(pairs)
        acc = 0.0
        median = ordered[-1][0]
        for value, w in ordered:
            acc += w
            if acc >= 0.5 * sum(p[1] for p in pairs):
                median = value
                break
        mean0, sd0 = weighted_mean_sd(pairs)
        lo, hi = median - TRIM_SD * max(sd0, 0.2), median + TRIM_SD * max(sd0, 0.2)
        trimmed = [(min(max(v, lo), hi), w) for v, w in pairs]
        mean, sd = weighted_mean_sd(trimmed)
        medians[hour] = mean
        spreads[hour] = sd
    # Smooth the spread across neighbouring hours; it should not jump hour to hour.
    smoothed = {}
    for hour in range(2, 25):
        near = [spreads[h] for h in (hour - 1, hour, hour + 1) if h in spreads]
        smoothed[hour] = sum(near) / len(near)
    return medians, smoothed


def forecast_case(case):
    if case["levels"] != LEVELS:
        raise ValueError(f"case asks for levels {case['levels']}, not {LEVELS}")
    ref = case_reference(case)
    p1 = ref.v1
    curves = []
    for comp in case["comparables"]:
        curve = build_curve(comp["name"], comp["day_start"], comp["hourly"], comp.get("unlock", ""))
        if curve is not None:
            curves.append(curve)
    rows = []
    if curves:
        medians, spreads = pooled_curve(ref, curves)
    else:  # no usable comparable: fall back to a flat, widening forecast
        medians = {h: 0.0 for h in range(2, 25)}
        spreads = {h: 0.15 * math.sqrt(h - 1) for h in range(2, 25)}
    for row in case["forecast"]:
        hour = row["hour"]
        centre = math.log(p1) + medians[hour]
        spread = spreads[hour] * SPREAD_SCALE
        spread = max(spread, SPREAD_FLOOR)
        spread = (1.0 - SPREAD_SQRT_BLEND) * spread + SPREAD_SQRT_BLEND * 0.15 * math.sqrt(hour - 1)
        quantiles = []
        for z in Z:
            q = math.exp(centre + z * spread)
            q = min(max(q, 0.01), 1_000_000_000.0)
            quantiles.append(round2(q))
        for i in range(1, 5):  # rounding must never break the ordering
            if quantiles[i] < quantiles[i - 1]:
                quantiles[i] = quantiles[i - 1]
        rows.append({"hour": hour, "q": quantiles})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
