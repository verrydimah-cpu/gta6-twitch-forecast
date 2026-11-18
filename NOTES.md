# Method notes

## What is being forecast

For each hour h = 2..24 of the release day (UTC), the mean concurrent viewers
of the game's Twitch category, given only what is known at the end of hour 1:
hour 1's print, the pre-day history, and 38–42 past launches' full hourly
curves ("comparables"), each framed on its own UTC release day.

## Why pooling, and why these weights

The UTC framing is doing quiet work: every comparable unlocked at midnight
local time somewhere, so "hour of the UTC day" lines the launches up by
which regions were awake and unlocked, not by time since unlock. The pooled
log-ratio curve therefore already encodes the day's rhythm (pre-dawn lull,
US-east unlock step at hour 5–6, US-west at hour 8–9, evening peak around
hours 18–22, late decay).

The pool is not uniform, because the set mixes three different animals:

* rolling-midnight console launches — the target shape;
* simultaneous-global launches (a single unlock instant, often 14:00Z):
  hour 1 is a near-empty category and ratios reach 100–2000x;
* early-access launches: the real peak happened days earlier, so the release
  day starts high and sags.

Four cheap features separate them and are all computable for the case itself
at the checkpoint: ln(hour-1 viewers), ln(hour-1 channels), the eve ratio
ln(v(23:00 day-1) / v(hour 1)), and the ramp ln(v(eve) / v(eve-6h)). A
Gaussian kernel on those, times a factor read from each comparable's unlock
note ("simultaneous", "single global unlock", "early access", the kit's
"Tier: weak"), gives the weights. A small unweighted-pool blend and a
per-hour winsorise keep any single launch from dominating.

## Spread

Pinball loss on the log scale is minimised by true quantiles of ln(viewers).
The spread per hour is the weighted SD of the comparables' log-ratios around
the pooled centre — it is small in the lull (every launch agrees the early
hours are quiet) and wide near the peak (launches disagree by 2–3x there),
which matches how the day actually behaves. It is floored, smoothed across
neighbouring hours, and blended slightly with the persistence baseline's
sqrt-hour widening so a thin hour of data cannot produce a cocky interval.

## Calibration

Constants were tuned on the kit's four practice cases (true answers are the
same SullyGnome hourly series the kit documents) and on 37 leave-one-out
pseudo-cases built from the practice comparables. Result: practice mean
pinball ≈ 0.20 vs ≈ 0.39 for the house persistence baseline and ≈ 0.43 for
an unweighted pooled forecast; leave-one-out ≈ 0.43 vs ≈ 0.93 / ≈ 0.78.
The residual hard cases in leave-one-out are the simultaneous-global
launches themselves (Silksong, Wukong), whose day is close to unforecastable
from hour 1 — they are also the launches least similar to GTA VI, so the
kernel gives them little say in the final.

## Risks

* The final's prints are minute-read means, the practice's are hourly
  averages; the log-ratio shapes transfer, the levels are anchored to the
  case's own hour 1 either way.
* If GTA VI's hour 1 lands far outside the comparables' scale range, the
  kernel leans on the eve/ramp features and the global blend — the forecast
  degrades toward the pooled shape rather than toward flat.
* Everything is a pure function of the case file: no randomness, no clock,
  no network, so the grader's two runs agree byte for byte.
