# GTA VI launch-day Twitch forecast

[![make.fun bounty](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/verrydimah-cpu/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/verrydimah-cpu/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

An entry for the make.fun bounty [Forecast GTA VI's launch-day Twitch viewers hour by hour](https://make.fun/bounty/gta6-twitch-ccu-forecast-01).

`main.py` (Python 3.13, standard library only, no network) is run once per
case: it reads the case file in the input directory — everything recorded up
to the end of hour 1 of the release day, that hour's viewer count included,
plus the hourly curves of dozens of past big launches — and writes one
forecast file per case: for each of hours 2 to 24, five quantiles (0.05,
0.25, 0.5, 0.75, 0.95) of that hour's concurrent viewers in the game's Twitch
category.

## How it forecasts

A console game that unlocks at midnight local time, rolling around the
world, draws a characteristic UTC-day curve: New Zealand and then Europe are
already playing before the UTC day begins, hour 1 is a lull with the UK just
in and the US still locked, and the count climbs through the European
evening and the US unlocks to a peak late in the day. The forecaster pools
the case's comparable launches instead of assuming that shape:

* each comparable with a usable release day contributes its log-ratio curve
  `ln(viewers_h) - ln(viewers_1)`;
* comparables are weighted by similarity to the case — hour-1 scale (viewers
  and channels), the "eve ratio" of the last pre-day hour to hour 1, and the
  pre-day ramp — which separates rolling-midnight launches from
  simultaneous-global ones (hour 1 near zero, then an explosion) and from
  early-access launches (release day already past its peak); each
  comparable's unlock note is read for the same markers;
* the median is hour 1's print times the pooled curve, and the spread is the
  pooled cross-launch dispersion per hour, so the quantiles are honest on
  the log scale the contest scores (pinball loss).

## Run it

```
mkdir -p out
MAKEFUN_INPUT_DIR=<dir with .in files> MAKEFUN_OUTPUT_DIR=out python3 main.py
```

With the kit's practice cases this scores a mean pinball loss of about 0.20,
against about 0.39 for the flat persistence baseline and about 0.43 for an
unweighted pooled forecast.

## License

MIT — see `LICENSE`.
