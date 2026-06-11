from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import RSAConfig


def analyze_ibi_segments(ibi: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    """Compute segment-level HRV/RSA metrics from MindWare IBI columns."""

    config = config or RSAConfig()
    rows = []
    for segment, seg in ibi.groupby("segment"):
        values = seg["ibi_ms"].dropna().astype(float).to_numpy()
        values = values[(values >= config.ibi_min_ms) & (values <= config.ibi_max_ms)]
        metrics = _analyze_segment(values, config)
        metrics["segment"] = int(segment)
        rows.append(metrics)
    cols = ["segment", "n_ibi", "mean_ibi_ms", "mean_hr_bpm", "sdnn_ms", "rmssd_ms",
            "lf_power", "hf_rsa_power", "lf_hf_ratio", "hf_peak_hz"]
    return pd.DataFrame(rows)[cols]


def analyze_nonlinear_features(ibi: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    """Compute nonlinear HRV features from segment-level IBI series."""

    config = config or RSAConfig()
    rows = []
    for segment, seg in ibi.groupby("segment"):
        values = _valid_ibi(seg["ibi_ms"], config)
        features = _nonlinear_segment(values, config)
        features["segment"] = int(segment)
        rows.append(features)
    cols = [
        "segment",
        "n_ibi",
        "cv_ibi",
        "poincare_sd1_ms",
        "poincare_sd2_ms",
        "sd1_sd2_ratio",
        "sample_entropy_m2_r02",
    ]
    return pd.DataFrame(rows)[cols]


def analyze_multiscale_entropy(ibi: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    """Compute multiscale entropy on the full recording IBI sequence."""

    config = config or RSAConfig()
    ordered = ibi.sort_values(["segment", "beat_index"])
    values = _valid_ibi(ordered["ibi_ms"], config)
    rows = []
    for scale in range(1, config.mse_max_scale + 1):
        coarse = _coarse_grain(values, scale)
        rows.append(
            {
                "scope": "full_recording",
                "scale": scale,
                "n_points": int(coarse.size),
                "sample_entropy_m2_r02": sample_entropy(coarse, config.entropy_m, config.entropy_r_ratio),
            }
        )
    return pd.DataFrame(rows)


def _valid_ibi(values: pd.Series, config: RSAConfig) -> np.ndarray:
    out = values.dropna().astype(float).to_numpy()
    return out[(out >= config.ibi_min_ms) & (out <= config.ibi_max_ms)]


def _analyze_segment(ibi_ms: np.ndarray, config: RSAConfig) -> dict[str, float]:
    if ibi_ms.size == 0:
        return _empty_metrics()

    mean_ibi = float(np.mean(ibi_ms))
    out = {
        "n_ibi": int(ibi_ms.size),
        "mean_ibi_ms": mean_ibi,
        "mean_hr_bpm": float(60000.0 / mean_ibi) if mean_ibi else math.nan,
        "sdnn_ms": float(np.std(ibi_ms, ddof=1)) if ibi_ms.size > 1 else 0.0,
        "rmssd_ms": float(np.sqrt(np.mean(np.diff(ibi_ms) ** 2))) if ibi_ms.size > 1 else 0.0,
        "lf_power": math.nan,
        "hf_rsa_power": math.nan,
        "lf_hf_ratio": math.nan,
        "hf_peak_hz": math.nan,
    }
    powers = _band_powers(ibi_ms, config)
    out.update(powers)
    return out


def _nonlinear_segment(ibi_ms: np.ndarray, config: RSAConfig) -> dict[str, float]:
    if ibi_ms.size == 0:
        return {
            "n_ibi": 0,
            "cv_ibi": math.nan,
            "poincare_sd1_ms": math.nan,
            "poincare_sd2_ms": math.nan,
            "sd1_sd2_ratio": math.nan,
            "sample_entropy_m2_r02": math.nan,
        }

    mean_ibi = float(np.mean(ibi_ms))
    sd = float(np.std(ibi_ms, ddof=1)) if ibi_ms.size > 1 else 0.0
    diff = np.diff(ibi_ms)
    sd1 = float(np.sqrt(np.var(diff, ddof=1) / 2.0)) if diff.size > 1 else math.nan
    sd2_term = (2.0 * sd * sd) - (0 if math.isnan(sd1) else sd1 * sd1)
    sd2 = float(np.sqrt(max(sd2_term, 0.0))) if ibi_ms.size > 2 else math.nan
    return {
        "n_ibi": int(ibi_ms.size),
        "cv_ibi": float(sd / mean_ibi) if mean_ibi else math.nan,
        "poincare_sd1_ms": sd1,
        "poincare_sd2_ms": sd2,
        "sd1_sd2_ratio": float(sd1 / sd2) if sd2 and not math.isnan(sd1) else math.nan,
        "sample_entropy_m2_r02": sample_entropy(ibi_ms, config.entropy_m, config.entropy_r_ratio),
    }


def sample_entropy(values: np.ndarray, m: int = 2, r_ratio: float = 0.2) -> float:
    """Sample entropy using Chebyshev distance and r = r_ratio * SD."""

    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if x.size <= m + 2:
        return math.nan
    sd = float(np.std(x, ddof=1))
    if sd == 0.0 or math.isnan(sd):
        return math.nan
    r = r_ratio * sd
    count_m = _template_match_count(x, m, r)
    count_m1 = _template_match_count(x, m + 1, r)
    if count_m == 0 or count_m1 == 0:
        return math.nan
    return float(-math.log(count_m1 / count_m))


def _template_match_count(x: np.ndarray, m: int, r: float) -> int:
    templates = np.array([x[i : i + m] for i in range(x.size - m + 1)])
    count = 0
    for i in range(len(templates) - 1):
        distances = np.max(np.abs(templates[i + 1 :] - templates[i]), axis=1)
        count += int(np.count_nonzero(distances <= r))
    return count


def _coarse_grain(values: np.ndarray, scale: int) -> np.ndarray:
    if scale <= 1:
        return values
    n = values.size // scale
    if n == 0:
        return np.array([], dtype=float)
    return values[: n * scale].reshape(n, scale).mean(axis=1)


def _empty_metrics() -> dict[str, float]:
    return {
        "n_ibi": 0,
        "mean_ibi_ms": math.nan,
        "mean_hr_bpm": math.nan,
        "sdnn_ms": math.nan,
        "rmssd_ms": math.nan,
        "lf_power": math.nan,
        "hf_rsa_power": math.nan,
        "lf_hf_ratio": math.nan,
        "hf_peak_hz": math.nan,
    }


def _band_powers(ibi_ms: np.ndarray, config: RSAConfig) -> dict[str, float]:
    if ibi_ms.size < 4:
        return {}

    beat_times = np.cumsum(ibi_ms) / 1000.0
    beat_times = beat_times - beat_times[0]
    duration = beat_times[-1]
    if duration <= 2.0 / config.hf_rsa_band_hz[0]:
        return {}

    t = np.arange(0.0, duration, 1.0 / config.resample_hz)
    if t.size < 8:
        return {}

    hp = np.interp(t, beat_times, ibi_ms)
    hp = hp - np.mean(hp)
    window = np.hanning(hp.size)
    freqs = np.fft.rfftfreq(hp.size, d=1.0 / config.resample_hz)
    psd = (np.abs(np.fft.rfft(hp * window)) ** 2) / (config.resample_hz * np.sum(window ** 2))

    lf = _integrate_band(freqs, psd, config.lf_band_hz)
    hf = _integrate_band(freqs, psd, config.hf_rsa_band_hz)
    hf_mask = (freqs >= config.hf_rsa_band_hz[0]) & (freqs <= config.hf_rsa_band_hz[1])
    hf_peak = float(freqs[hf_mask][np.argmax(psd[hf_mask])]) if np.any(hf_mask) else math.nan
    return {
        "lf_power": lf,
        "hf_rsa_power": hf,
        "lf_hf_ratio": float(lf / hf) if hf and not math.isnan(hf) else math.nan,
        "hf_peak_hz": hf_peak,
    }


def _integrate_band(freqs: np.ndarray, psd: np.ndarray, band: tuple[float, float]) -> float:
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if np.count_nonzero(mask) < 2:
        return math.nan
    return float(np.trapz(psd[mask], freqs[mask]))
