#!/usr/bin/env python3
"""Gravity recording analysis for MotionTrace and Sensor Logger.

Commands:
  quality REC [REC ...]    rate, intervals, gaps and rate drift of each recording
  compare A B [A B ...]    align two simultaneous recordings (pairs) and compare values

A recording is a MotionTrace CSV (the JSON next to it is read if present), a Sensor Logger
export zip, an unzipped Sensor Logger folder, or its Gravity.csv. Glob patterns are expanded
here, so they work in PowerShell too.

Results go to --out (default: analysis/out): quality.md, quality.csv, quality.json or
compare.md, compare.csv. The Markdown table is also printed. With --plots, also a PNG per
recording / pair (matplotlib is imported only then).
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_OUT = Path(__file__).resolve().parent / "out"

# An interval at least GAP_FACTOR x the local nominal interval is a gap: one missed sample
# gives ~2x, and timestamp jitter puts it on either side of 2.0, so the threshold sits between
# one and two intervals. Lost samples per gap = round(interval / nominal) - 1.
GAP_FACTOR = 1.5
# A non-gap interval more than IRREGULAR_PCT off the local nominal is "irregular". Paired
# timestamp corrections of the sensor hub stay under ~0.7 %; a stretch of irregular intervals that
# adds up to whole intervals is a slowdown that hides lost samples without leaving a single gap.
IRREGULAR_PCT = 1.0
# Irregular intervals closer than this to each other belong to one episode.
EPISODE_JOIN_S = 1.0
# Gaps at least this long are "long breaks" (the M2 acceptance criterion).
LONG_GAP_S = 1.0
# Nominal interval = rolling median over this many intervals. The sensor rate drifts by
# hundredths of a percent per hour, so a whole-recording median would misjudge long files.
NOMINAL_WINDOW = 1001
# Window at the start and end of a recording used to measure rate drift.
DRIFT_WINDOW_S = 60.0
# Below this per-axis standard deviation (m/s^2) the phone was still and Pearson r is noise.
STATIC_STD = 0.02
# Points per line in plots; longer series are decimated.
PLOT_POINTS = 20_000


@dataclass
class Recording:
    path: Path
    name: str  # file or zip stem, used for output file names
    app: str  # "MotionTrace" | "Sensor Logger"
    t_ns: np.ndarray  # int64 timestamps used for intervals, in file order
    utc_ns: np.ndarray  # int64 UTC epoch ns, used to align two recordings
    xyz: np.ndarray  # (n, 3) float64: x, y, z in m/s^2
    info: dict = field(default_factory=dict)  # device, mode, completeness, ...
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- loading


def expand_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        if glob.has_magic(pattern):
            # MotionTrace JSON is read together with its CSV, and notes (.txt, .md) may sit next to the data,
            # so a mask like data/* skips them.
            matches = [m for m in sorted(glob.glob(pattern)) if not m.lower().endswith((".json", ".tmp", ".txt", ".md"))]
        else:
            if not Path(pattern).exists():
                sys.exit(f"{pattern}: not found")
            matches = [pattern]
        if not matches:
            sys.exit(f"No files match {pattern}")
        paths += [Path(m) for m in matches]
    return paths


def load(path: Path) -> Recording:
    if path.is_dir():
        csv = next((p for p in path.rglob("*") if p.name.lower() == "gravity.csv"), None)
        if csv is None:
            sys.exit(f"{path}: no Gravity.csv inside")
        meta = next((p for p in path.rglob("*") if p.name.lower() == "metadata.csv"), None)
        return _load_sensor_logger(path, path.name, csv.read_bytes(), meta.read_bytes() if meta else None)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            names = {Path(n).name.lower(): n for n in z.namelist()}
            if "gravity.csv" not in names:
                sys.exit(f"{path}: no Gravity.csv in the zip (was Gravity enabled in Sensor Logger?)")
            meta = z.read(names["metadata.csv"]) if "metadata.csv" in names else None
            return _load_sensor_logger(path, path.stem, z.read(names["gravity.csv"]), meta)
    data = path.read_bytes()
    header = data[:200].split(b"\n", 1)[0].decode("utf-8", "replace").strip().split(",")
    if "sensor_timestamp_ns" in header:
        return _load_motiontrace(path, data)
    if "time" in header and "x" in header:
        meta = path.with_name("Metadata.csv")
        name = path.parent.name if path.name.lower() == "gravity.csv" else path.stem
        return _load_sensor_logger(path, name, data, meta.read_bytes() if meta.exists() else None)
    sys.exit(f"{path}: unknown CSV format (header: {','.join(header)})")


def _read_csv(path: Path, data: bytes, time_cols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Read the CSV with time_cols as int64 (epoch ns don't fit a float64) and x, y, z as floats.

    Rows missing any of these columns are dropped with a warning.
    """
    warnings = []
    # A file cut off mid-write (app killed, copy interrupted) ends with a partial line, whose
    # last number may be truncated yet still parse: drop it.
    if data and not data.endswith(b"\n"):
        data = data[: data.rfind(b"\n") + 1]
        warnings.append("the last line was incomplete and is skipped")
    columns = [*time_cols, "x", "y", "z"]
    df = pd.read_csv(io.BytesIO(data), dtype=dict.fromkeys(time_cols, str))
    missing = [c for c in columns if c not in df.columns]
    if missing:
        sys.exit(f"{path}: missing columns {', '.join(missing)}")
    complete = df[columns].notna().all(axis=1)
    if not complete.all():
        warnings.append(f"{int((~complete).sum())} incomplete rows skipped")
        df = df[complete].copy()
        df[["x", "y", "z"]] = df[["x", "y", "z"]].apply(pd.to_numeric)
    for col in time_cols:
        try:
            df[col] = df[col].astype("int64")
        except (ValueError, OverflowError):
            # Float timestamps lose precision (~256 ns at epoch scale) but are still usable.
            df[col] = df[col].astype("float64").round().astype("int64")
            warnings.append(f"'{col}' is not an integer column; timestamps have reduced precision")
    return df, warnings


def _load_motiontrace(path: Path, data: bytes) -> Recording:
    df, warnings = _read_csv(path, data, ["sensor_timestamp_ns", "time_utc_ns"])
    meta_path = path.with_suffix(".json")
    meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else None
    info: dict = {"app": "MotionTrace"}
    if meta is None:
        warnings.append("no JSON metadata next to the CSV")
    else:
        device, sensor, rec = meta.get("device", {}), meta.get("sensor", {}), meta.get("recording", {})
        result = meta.get("result")
        info |= {
            "device": f"{device.get('manufacturer', '?')} {device.get('model', '?')}",
            "android": device.get("androidVersion"),
            "sensor": f"{sensor.get('name', '?')} ({sensor.get('vendor', '?')})",
            "sensor_min_delay_us": sensor.get("minDelayUs"),
            "mode": rec.get("mode"),
            "requested_period_us": rec.get("requestedSamplingPeriodUs"),
            "finished": result is not None,
            "recording_error": result.get("error") if result else None,
        }
        if result is None:
            warnings.append("JSON has no 'result': the recording was cut off")
        elif result.get("error"):
            warnings.append(f"recording stopped with error: {result['error']}")
        start, stop = meta.get("clockAtStart"), meta.get("clockAtStop")
        if start and stop:
            info["utc_clock_drift_ms"] = (stop["utcOffsetNs"] - start["utcOffsetNs"]) / 1e6
    return Recording(
        path=path,
        name=path.stem,
        app="MotionTrace",
        t_ns=df["sensor_timestamp_ns"].to_numpy(),
        utc_ns=df["time_utc_ns"].to_numpy(),
        xyz=df[["x", "y", "z"]].to_numpy("float64"),
        info=info,
        warnings=warnings,
    )


def _load_sensor_logger(path: Path, name: str, data: bytes, meta_data: bytes | None) -> Recording:
    # Sensor Logger writes "time,seconds_elapsed,z,y,x": always index by name.
    df, warnings = _read_csv(path, data, ["time"])
    info: dict = {"app": "Sensor Logger"}
    if meta_data:
        meta = pd.read_csv(io.BytesIO(meta_data), dtype=str).iloc[0].dropna().to_dict()
        info["sensor_logger_metadata"] = meta
        keys = {k.lower().replace(" ", ""): v for k, v in meta.items()}
        info["device"] = keys.get("devicename") or keys.get("device")
        info["platform"] = keys.get("platform")
        info["app_version"] = keys.get("appversion")
    else:
        warnings.append("no Metadata.csv: export the zip to keep device info")
    if "seconds_elapsed" in df:
        info["samples_before_start"] = int((pd.to_numeric(df["seconds_elapsed"], errors="coerce") < 0).sum())
    return Recording(
        path=path,
        name=name,
        app="Sensor Logger",
        t_ns=df["time"].to_numpy(),
        utc_ns=df["time"].to_numpy(),
        xyz=df[["x", "y", "z"]].to_numpy("float64"),
        info=info,
        warnings=warnings,
    )


# ---------------------------------------------------------------- quality


@dataclass
class Quality:
    metrics: dict
    gaps: list[dict]
    # Series for plots.
    t_s: np.ndarray  # time of each interval's end, s from the first sample
    dt_ms: np.ndarray
    gap_mask: np.ndarray
    irregular: np.ndarray
    minute_t_s: np.ndarray
    minute_rate: np.ndarray


def timestamp_resolution(dt: np.ndarray) -> str:
    for step, label in ((1_000_000, "1 ms"), (1_000, "1 us")):
        if dt.size and np.all(dt % step == 0):
            return label
    return "1 ns"


def mean_rate(dt_ms: np.ndarray, gap_mask: np.ndarray) -> float:
    ok = dt_ms[~gap_mask & (dt_ms > 0)]
    return 1e3 / ok.mean() if ok.size else float("nan")


def analyze_quality(rec: Recording) -> Quality:
    t = rec.t_ns
    if t.size < 3:
        sys.exit(f"{rec.path}: fewer than 3 samples")
    dt = np.diff(t)
    dt_ms = dt / 1e6
    t_s = (t[1:] - t[0]) / 1e9
    duration_s = (t[-1] - t[0]) / 1e9

    nominal = pd.Series(np.where(dt > 0, dt_ms, np.nan)).rolling(NOMINAL_WINDOW, center=True, min_periods=1).median()
    nominal = nominal.bfill().ffill().to_numpy()
    gap_mask = dt_ms >= GAP_FACTOR * nominal
    missing = np.maximum(np.round(dt_ms[gap_mask] / nominal[gap_mask]) - 1, 1)
    lost = int(missing.sum())
    gap_ms = dt_ms[gap_mask]

    regular = ~gap_mask & (dt > 0)
    deviation_us = (dt_ms[regular] - nominal[regular]) * 1e3
    irregular = regular & (np.abs(dt_ms / nominal - 1) * 100 > IRREGULAR_PCT)
    irregular_t = t_s[irregular]
    episodes = int(irregular_t.size and 1 + (np.diff(irregular_t) > EPISODE_JOIN_S).sum())
    # Samples missing by elapsed time: how many nominal intervals the recording spans beyond the
    # samples it has. Counts gaps and slowdowns alike; jitter and paired corrections cancel out.
    lost_by_time = float((dt_ms[dt > 0] / nominal[dt > 0]).sum() - (dt > 0).sum())
    median_ms = float(np.median(dt_ms[dt > 0]))

    # Rate drift: mean regular interval in the first vs the last window.
    window = min(DRIFT_WINDOW_S, duration_s / 4)
    first, last = t_s <= window, t_s >= duration_s - window
    rate_first = mean_rate(dt_ms[first], gap_mask[first])
    rate_last = mean_rate(dt_ms[last], gap_mask[last])

    # Mean rate within each minute of sensor time: shows drift, and dips where samples were lost.
    by_minute = pd.DataFrame({"m": (t - t[0]) // 60_000_000_000, "t": t}).groupby("m")["t"].agg(["min", "max", "count"])
    by_minute = by_minute[by_minute["count"] > 1]
    minute_rate = ((by_minute["count"] - 1) / ((by_minute["max"] - by_minute["min"]) / 1e9)).to_numpy()
    minute_t_s = ((by_minute["min"] + by_minute["max"]) / 2 - t[0]).to_numpy() / 1e9

    norm = np.linalg.norm(rec.xyz, axis=1)
    gaps = sorted(
        (
            {"at_s": round(float(s), 3), "length_ms": round(float(d), 3), "missing_samples": int(m)}
            for s, d, m in zip(t_s[gap_mask] - gap_ms / 1e3, gap_ms, missing)
        ),
        key=lambda g: -g["length_ms"],
    )
    info = rec.info
    metrics = {
        "app": rec.app,
        "device": info.get("device"),
        "mode": info.get("mode"),
        "finished": info.get("finished"),
        "duration_s": duration_s,
        "samples": int(t.size),
        "rate_hz": (t.size - 1) / duration_s,
        "interval_median_ms": median_ms,
        "interval_std_us": float(deviation_us.std()) if deviation_us.size else float("nan"),
        "interval_p99_9_ms": float(np.percentile(dt_ms, 99.9)),
        "interval_max_ms": float(dt_ms.max()),
        "interval_max_vs_median_pct": (float(dt_ms.max()) / median_ms - 1) * 100,
        "gaps": int(gap_mask.sum()),
        "long_gaps": int((gap_ms >= LONG_GAP_S * 1e3).sum()),
        "longest_gap_ms": float(gap_ms.max()) if gap_ms.size else 0.0,
        "lost_samples": lost,
        "completeness_pct": 100.0 * (t.size - 1) / (t.size - 1 + lost),
        "irregular_intervals": int(irregular.sum()),
        "irregular_episodes": episodes,
        "lost_samples_by_time": lost_by_time,
        "non_monotonic": int((dt < 0).sum()),
        "duplicate_timestamps": int((dt == 0).sum()),
        "rate_start_hz": rate_first,
        "rate_end_hz": rate_last,
        "rate_drift_pct": (rate_last / rate_first - 1) * 100,
        "timestamp_resolution": timestamp_resolution(dt),
        "norm_mean": float(norm.mean()),
        "norm_std": float(norm.std()),
        "samples_before_start": info.get("samples_before_start"),
        "utc_clock_drift_ms": info.get("utc_clock_drift_ms"),
    }
    return Quality(metrics, gaps, t_s, dt_ms, gap_mask, irregular, minute_t_s, minute_rate)


def _decimate(n: int) -> slice:
    return slice(None, None, max(1, n // PLOT_POINTS))


def _pyplot():
    # Imported on demand: plots are optional (--plots).
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def plot_quality(rec: Recording, q: Quality, out: Path) -> None:
    plt = _pyplot()
    m = q.metrics
    fig, ax = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle(
        f"{rec.name} — {rec.app}, {m['device'] or '?'}, {m['mode'] or ''}\n"
        f"{m['duration_s'] / 60:.1f} min, {m['samples']} samples, {m['rate_hz']:.3f} Hz, "
        f"gaps {m['gaps']}, lost {m['lost_samples']}, irregular episodes {m['irregular_episodes']}, "
        f"lost by elapsed time {m['lost_samples_by_time']:.1f}"
    )
    minutes = q.t_s / 60
    a = ax[0, 0]
    regular = ~q.gap_mask
    a.plot(minutes[regular], q.dt_ms[regular], ",", color="tab:blue", rasterized=True)
    a.plot(minutes[q.irregular], q.dt_ms[q.irregular], ".", color="tab:orange", ms=3, label="irregular")
    a.plot(minutes[q.gap_mask], q.dt_ms[q.gap_mask], "o", color="tab:red", ms=4, label="gap")
    a.set(title="Interval between samples", xlabel="time, min", ylabel="interval, ms")
    if q.gap_mask.any():
        a.set_yscale("log")
    if q.gap_mask.any() or q.irregular.any():
        a.legend(loc="upper right")
    a.grid(alpha=0.3)

    a = ax[0, 1]
    lo, hi = np.percentile(q.dt_ms, [0.01, 99.99])
    pad = max(hi - lo, 1e-3) * 0.5
    a.hist(np.clip(q.dt_ms, lo - pad, hi + pad), bins=200, color="tab:blue")
    a.set(title="Interval histogram (clipped to 0.01–99.99 percentile)", xlabel="interval, ms", ylabel="count")
    a.set_yscale("log")
    a.grid(alpha=0.3)

    a = ax[1, 0]
    a.plot(q.minute_t_s / 60, q.minute_rate, ".-", color="tab:green")
    a.set(title="Mean rate per minute", xlabel="time, min", ylabel="rate, Hz")
    a.ticklabel_format(axis="y", useOffset=False)
    a.grid(alpha=0.3)

    a = ax[1, 1]
    s = _decimate(rec.xyz.shape[0])
    t_min = (rec.t_ns[s] - rec.t_ns[0]) / 60e9
    for i, axis in enumerate("xyz"):
        a.plot(t_min, rec.xyz[s, i], lw=0.7, label=axis)
    a.set(title="Gravity", xlabel="time, min", ylabel="m/s²")
    a.legend(loc="upper right")
    a.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------- compare


def _sorted_unique(rec: Recording) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(rec.utc_ns, kind="stable")
    t, v = rec.utc_ns[order], rec.xyz[order]
    keep = np.r_[True, np.diff(t) > 0]
    return t[keep], v[keep]


def _resample(t_s: np.ndarray, v: np.ndarray, grid_s: np.ndarray) -> np.ndarray:
    """Linear interpolation onto grid_s; NaN outside the recording and inside its gaps."""
    out = np.column_stack([np.interp(grid_s, t_s, v[:, i]) for i in range(3)])
    max_span = GAP_FACTOR * np.median(np.diff(t_s))
    idx = np.clip(np.searchsorted(t_s, grid_s), 1, t_s.size - 1)
    span = t_s[idx] - t_s[idx - 1]
    valid = (span <= max_span) & (grid_s >= t_s[0]) & (grid_s <= t_s[-1])
    out[~valid] = np.nan
    return out


def _xcorr_lag(ya: np.ndarray, yb: np.ndarray, fs: float, max_lag_s: float) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Coarse lag (s) such that b(t + lag) ~ a(t), plus the normalized peak and the curve.

    Correlates first differences summed over axes: gravity itself changes slowly, so the
    correlation of raw values has a peak too broad to place within a grid step.
    """
    a = np.diff(ya, axis=0)
    b = np.diff(yb, axis=0)
    a = np.nan_to_num(a - np.nanmean(a, axis=0))
    b = np.nan_to_num(b - np.nanmean(b, axis=0))
    n = a.shape[0]
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    corr = np.zeros(nfft)
    for i in range(3):
        corr += np.fft.irfft(np.conj(np.fft.rfft(a[:, i], nfft)) * np.fft.rfft(b[:, i], nfft), nfft)
    corr /= np.sqrt((a**2).sum() * (b**2).sum()) or 1.0
    k = int(min(max_lag_s * fs, n - 1))
    lags = np.arange(-k, k + 1)
    curve = corr[lags % nfft]
    peak = int(np.argmax(curve))
    return lags[peak] / fs, float(curve[peak]), lags / fs, curve


def _refine_lag(ya: np.ndarray, tb_s: np.ndarray, vb: np.ndarray, grid: np.ndarray, lag_s: float, step_s: float) -> float:
    """The lag minimizing RMSE between a and the shifted b, searched coarse-to-fine around lag_s."""

    def rmse(lag: float) -> float:
        d = ya - _resample(tb_s - lag, vb, grid)
        return float(np.sqrt(np.nanmean(d**2)))

    for span, step in ((2 * step_s, step_s / 10), (step_s / 10, step_s / 200)):
        candidates = lag_s + np.arange(-span, span + step / 2, step)
        lag_s = float(candidates[np.argmin([rmse(c) for c in candidates])])
    return lag_s


def _match_samples(ta: np.ndarray, tb: np.ndarray, lag_ns: int, tol_ns: float | None = None):
    """Pair each a sample with the nearest b sample at tb - lag_ns, keeping pairs within tol_ns.

    Returns indices into a, indices into b and the time differences (b - a), in ns.
    """
    tb_shifted = tb - lag_ns
    idx = np.clip(np.searchsorted(tb_shifted, ta), 1, tb.size - 1)
    left, right = tb_shifted[idx - 1], tb_shifted[idx]
    nearest = np.where(np.abs(ta - left) <= np.abs(right - ta), idx - 1, idx)
    diff = tb_shifted[nearest] - ta
    ok = np.ones(diff.size, bool) if tol_ns is None else np.abs(diff) <= tol_ns
    return np.nonzero(ok)[0], nearest[ok], diff[ok]


def _event_offset(ta: np.ndarray, tb: np.ndarray, lag_ns: int, period_ns: float) -> tuple[float, float]:
    """Circular mean of the nearest-sample time differences modulo the sample period.

    If both apps got the same sensor events (one phone, one sensor), the differences cluster
    at one phase and the concentration is near 1; for unrelated timing it is near 0.
    Returns (offset ns in [-period/2, period/2], concentration 0..1).
    """
    _, _, diff = _match_samples(ta, tb, lag_ns)
    c = np.exp(2j * np.pi * diff / period_ns).mean()
    return float(np.angle(c) / (2 * np.pi) * period_ns), float(np.abs(c))


def analyze_pair(ra: Recording, rb: Recording, grid_hz: float, max_lag_s: float) -> tuple[dict, dict]:
    ta, va = _sorted_unique(ra)
    tb, vb = _sorted_unique(rb)
    start, end = max(ta[0], tb[0]), min(ta[-1], tb[-1])
    if end - start < 10e9:
        sys.exit(f"{ra.name} / {rb.name}: overlap is under 10 s — record both apps at the same time")
    ta, va = ta[(ta >= start) & (ta <= end)], va[(ta >= start) & (ta <= end)]
    tb, vb = tb[(tb >= start) & (tb <= end)], vb[(tb >= start) & (tb <= end)]
    # Relative float seconds: epoch nanoseconds don't fit a float64 exactly.
    ta_s, tb_s = (ta - start) / 1e9, (tb - start) / 1e9
    grid = np.arange(0.0, (end - start) / 1e9, 1.0 / grid_hz)
    ya, yb = _resample(ta_s, va, grid), _resample(tb_s, vb, grid)
    lag_s, peak, lags, curve = _xcorr_lag(ya, yb, grid_hz, max_lag_s)
    static = bool(np.all(np.nanstd(ya, axis=0) < STATIC_STD))
    if static:
        lag_s, lag_source = 0.0, "none (phone was still)"
    else:
        lag_s = _refine_lag(ya, tb_s, vb, grid, lag_s, 1.0 / grid_hz)
        lag_source = "cross-correlation + RMSE"

    # One phone, one sensor: both apps get the same events, so pair samples exactly.
    period_ns = float(min(np.median(np.diff(ta)), np.median(np.diff(tb))))
    offset_ns, concentration = _event_offset(ta, tb, round(lag_s * 1e9), period_ns)
    pa = pb = diff = np.empty(0, np.int64)
    lag_ns = round(lag_s * 1e9)
    if concentration > 0.9:
        base_ns = round(lag_s * 1e9 + offset_ns)
        # The phase fixes the lag modulo one period; the values pick the right sample.
        best = None
        for k in (0,) if static else (-2, -1, 0, 1, 2):
            lag_ns = base_ns + round(k * period_ns)
            ia, ib, d = _match_samples(ta, tb, lag_ns, period_ns / 4)
            score = np.median(np.abs(va[ia] - vb[ib])) if ia.size else np.inf
            if best is None or score < best[0]:
                best = (score, lag_ns, ia, ib, d)
        _, lag_ns, pa, pb, diff = best
        lag_s = (lag_ns + float(np.median(diff))) / 1e9
        lag_source += " + sample matching"
    # The overlap was cut by raw UTC, before the lag was known: a sample at its edge may have its
    # pair just outside. Count only samples whose pair would fall inside the other recording.
    tol = period_ns / 4
    a_in = (ta >= tb[0] - lag_ns - tol) & (ta <= tb[-1] - lag_ns + tol)
    b_in = (tb - lag_ns >= ta[0] - tol) & (tb - lag_ns <= ta[-1] + tol)
    same_events = pa.size > 0.5 * min(ta.size, tb.size)
    value_diff = np.abs(va[pa] - vb[pb])
    same_value = np.all(value_diff <= 1e-5 * np.maximum(1.0, np.abs(va[pa])), axis=1)

    yb_shifted = _resample(tb_s - lag_s, vb, grid)
    both = ~np.isnan(ya).any(axis=1) & ~np.isnan(yb_shifted).any(axis=1)
    da, db = ya[both], yb_shifted[both]
    metrics: dict = {
        "a": ra.name,
        "b": rb.name,
        "overlap_s": (end - start) / 1e9,
        "grid_hz": grid_hz,
        "lag_ms": lag_s * 1e3,
        "lag_source": lag_source,
        "xcorr_peak": peak,
        "static": static,
        "same_events": same_events,
        "matched_samples_a_pct": 100.0 * pa.size / max(int(a_in.sum()), 1),
        "matched_samples_b_pct": 100.0 * pb.size / max(int(b_in.sum()), 1),
        "matched_time_diff_us_max": float(np.abs(diff - np.median(diff)).max()) / 1e3 if same_events else None,
        "matched_identical_pct": 100.0 * float(same_value.mean()) if same_events else None,
        "matched_max_abs_diff": float(value_diff.max()) if same_events else None,
    }
    for i, axis in enumerate("xyz"):
        d = da[:, i] - db[:, i]
        r = np.corrcoef(da[:, i], db[:, i])[0, 1] if da[:, i].std() >= STATIC_STD else float("nan")
        metrics |= {
            f"pearson_{axis}": float(r),
            f"rmse_{axis}": float(np.sqrt(np.mean(d**2))),
            f"bias_{axis}": float(d.mean()),
            f"std_{axis}": float(da[:, i].std()),
        }
    norm_d = np.linalg.norm(da, axis=1) - np.linalg.norm(db, axis=1)
    metrics["rmse_norm"] = float(np.sqrt(np.mean(norm_d**2)))
    plot_data = {"grid": grid[both], "ya": da, "yb": db, "lags": lags, "curve": curve}
    return metrics, plot_data


def plot_pair(m: dict, data: dict, out: Path) -> None:
    plt = _pyplot()
    fig, ax = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle(
        f"{m['a']} vs {m['b']}\noverlap {m['overlap_s']:.0f} s, lag {m['lag_ms']:.3f} ms ({m['lag_source']}), "
        f"r = {m['pearson_x']:.4f} / {m['pearson_y']:.4f} / {m['pearson_z']:.4f}"
    )
    s = _decimate(data["grid"].size)
    t = data["grid"][s] / 60
    colors = ("tab:blue", "tab:orange", "tab:green")
    for i, axis in enumerate("xyz"):
        ax[0].plot(t, data["ya"][s, i], color=colors[i], lw=0.8, label=f"{axis} A")
        ax[0].plot(t, data["yb"][s, i], color=colors[i], lw=0.8, ls="--", label=f"{axis} B")
        ax[1].plot(t, data["ya"][s, i] - data["yb"][s, i], color=colors[i], lw=0.7, label=axis)
    ax[0].set(title=f"A = {m['a']}, B = {m['b']} (B shifted by the lag)", xlabel="time, min", ylabel="m/s²")
    ax[1].set(title="A − B", xlabel="time, min", ylabel="m/s²")
    ax[2].plot(data["lags"] * 1e3, data["curve"], color="tab:purple")
    ax[2].axvline(m["lag_ms"], color="tab:red", lw=0.8)
    ax[2].set(title="Cross-correlation of first differences (sum over axes, normalized)", xlabel="lag of B, ms", ylabel="correlation")
    for a in ax:
        a.grid(alpha=0.3)
    ax[0].legend(ncol=3, loc="upper right", fontsize=8)
    ax[1].legend(ncol=3, loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------- output


def _fmt(value, digits: int) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return "—" if np.isnan(value) else f"{value:.{digits}f}"
    return str(value)


QUALITY_ROWS = [
    ("app", "App", 0),
    ("device", "Device", 0),
    ("mode", "Mode", 0),
    ("finished", "Finished normally (JSON has result)", 0),
    ("duration_s", "Duration, s", 1),
    ("samples", "Samples", 0),
    ("rate_hz", "Mean rate, Hz", 3),
    ("interval_median_ms", "Median interval, ms", 4),
    ("interval_std_us", "Interval std (no gaps), µs", 2),
    ("interval_p99_9_ms", "Interval 99.9th percentile, ms", 4),
    ("interval_max_ms", "Max interval, ms", 3),
    ("interval_max_vs_median_pct", "Max interval vs median, %", 2),
    ("gaps", f"Gaps (≥ {GAP_FACTOR:g}× nominal)", 0),
    ("long_gaps", f"Long gaps (≥ {LONG_GAP_S:g} s)", 0),
    ("longest_gap_ms", "Longest gap, ms", 1),
    ("lost_samples", "Lost samples (estimate)", 0),
    ("completeness_pct", "Completeness, %", 4),
    ("irregular_intervals", f"Irregular intervals (> {IRREGULAR_PCT:g} % off nominal, not gaps)", 0),
    ("irregular_episodes", "Irregular episodes", 0),
    ("lost_samples_by_time", "Lost samples by elapsed time", 1),
    ("non_monotonic", "Non-monotonic timestamps", 0),
    ("duplicate_timestamps", "Duplicate timestamps", 0),
    ("rate_start_hz", "Rate, first minute, Hz", 3),
    ("rate_end_hz", "Rate, last minute, Hz", 3),
    ("rate_drift_pct", "Rate drift, %", 4),
    ("timestamp_resolution", "Timestamp resolution", 0),
    ("norm_mean", "Mean gravity magnitude, m/s²", 4),
    ("samples_before_start", "Samples before start (Sensor Logger)", 0),
    ("utc_clock_drift_ms", "UTC vs monotonic clock drift, ms", 3),
]

COMPARE_ROWS = [
    ("overlap_s", "Overlap, s", 1),
    ("lag_ms", "Lag of B, ms", 3),
    ("lag_source", "Lag from", 0),
    ("xcorr_peak", "Cross-correlation peak", 4),
    ("same_events", "Same sensor events in A and B", 0),
    ("matched_samples_a_pct", "A samples with a pair in B, %", 2),
    ("matched_samples_b_pct", "B samples with a pair in A, %", 2),
    ("matched_time_diff_us_max", "Paired timestamps spread, µs", 2),
    ("matched_identical_pct", "Paired samples with equal values, %", 2),
    ("matched_max_abs_diff", "Paired samples max abs(A−B), m/s²", 6),
    *[(f"pearson_{a}", f"Pearson r, {a}", 5) for a in "xyz"],
    *[(f"rmse_{a}", f"RMSE {a}, m/s²", 5) for a in "xyz"],
    *[(f"bias_{a}", f"Mean A−B, {a}, m/s²", 5) for a in "xyz"],
    *[(f"std_{a}", f"Signal std A, {a}, m/s²", 4) for a in "xyz"],
    ("rmse_norm", "RMSE of magnitude, m/s²", 5),
]


def markdown_table(columns: list[str], rows: list[tuple[str, str, int]], records: list[dict]) -> str:
    lines = ["| | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns)]
    for key, title, digits in rows:
        if all(r.get(key) is None for r in records):
            continue
        lines.append(f"| {title} | " + " | ".join(_fmt(r.get(key), digits) for r in records) + " |")
    return "\n".join(lines) + "\n"


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(type(o))


def cmd_quality(args) -> None:
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    records, details = [], []
    for path in expand_paths(args.recordings):
        rec = load(path)
        print(f"{rec.name}: {rec.t_ns.size} samples ({rec.app})", file=sys.stderr)
        for w in rec.warnings:
            print(f"  warning: {w}", file=sys.stderr)
        q = analyze_quality(rec)
        if args.plots:
            plot_quality(rec, q, out / f"{rec.name}.png")
        records.append(q.metrics | {"name": rec.name})
        details.append({"name": rec.name, "path": str(rec.path), "info": rec.info, "warnings": rec.warnings,
                        "metrics": q.metrics, "gaps_longest_first": q.gaps[:100]})
    table = markdown_table([r["name"] for r in records], QUALITY_ROWS, records)
    (out / "quality.md").write_text(table, "utf-8")
    pd.DataFrame(records).set_index("name").to_csv(out / "quality.csv")
    (out / "quality.json").write_text(json.dumps(details, indent=2, ensure_ascii=False, default=_json_default), "utf-8")
    print(table)
    print(f"Results: {out}", file=sys.stderr)


def cmd_compare(args) -> None:
    paths = expand_paths(args.recordings)
    if len(paths) % 2:
        sys.exit("compare takes pairs: A B [A B ...]")
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for pa, pb in zip(paths[::2], paths[1::2]):
        ra, rb = load(pa), load(pb)
        m, data = analyze_pair(ra, rb, args.grid_hz, args.max_lag)
        print(f"{ra.name} vs {rb.name}: lag {m['lag_ms']:.3f} ms", file=sys.stderr)
        if m["static"]:
            print("  note: the phone was still, Pearson r is not meaningful; compare RMSE and bias", file=sys.stderr)
        if args.plots:
            plot_pair(m, data, out / f"compare_{ra.name}__{rb.name}.png")
        records.append(m)
    table = markdown_table([f"{r['a']} vs {r['b']}" for r in records], COMPARE_ROWS, records)
    (out / "compare.md").write_text(table, "utf-8")
    pd.DataFrame(records).to_csv(out / "compare.csv", index=False)
    print(table)
    print(f"Results: {out}", file=sys.stderr)


def main() -> None:
    # Windows consoles and pipes default to a legacy code page; the tables use µ, ×, ≥.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    q = sub.add_parser("quality", help="rate, intervals, gaps and drift of each recording")
    q.add_argument("recordings", nargs="+")
    q.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    q.add_argument("--plots", action="store_true", help="also draw a PNG per recording")
    q.set_defaults(func=cmd_quality)
    c = sub.add_parser("compare", help="compare simultaneous recordings, given as pairs A B")
    c.add_argument("recordings", nargs="+")
    c.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    c.add_argument("--plots", action="store_true", help="also draw a PNG per pair")
    c.add_argument("--grid-hz", type=float, default=100.0, help="common grid rate (default 100)")
    c.add_argument("--max-lag", type=float, default=2.0, help="max lag searched, s (default 2)")
    c.set_defaults(func=cmd_compare)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
