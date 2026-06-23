from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import RSAConfig


@dataclass(frozen=True)
class RawSignal:
    sampling_hz: float
    samples: pd.DataFrame


def read_mindware_raw_signal(
    mwi_path: str | Path,
    mwx_path: str | Path,
    config: RSAConfig | None = None,
) -> RawSignal:
    """Decode calibrated raw samples from a MindWare ``.mwi/.mwx`` pair.

    The implementation supports the packet layout observed in MindWare Mobile
    RSA files: indexed packets in ``.mwi`` and interleaved 24-bit signed channel
    samples in ``.mwx`` for the ECG/Z0/dZdt channel group.
    """

    config = config or RSAConfig()
    mwi_path = Path(mwi_path)
    mwx_bytes = Path(mwx_path).read_bytes()
    con = sqlite3.connect(f"file:{mwi_path.resolve()}?immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    try:
        group_id = _find_ecg_group(con)
        channels = con.execute(
            """
            select channel_id, interleav_index, label
            from channel
            where channel_group_id = ?
            order by interleav_index
            """,
            (group_id,),
        ).fetchall()
        group = con.execute("select * from channel_group where group_id = ?", (group_id,)).fetchone()
        file_info = con.execute("select time_base from file_information").fetchone()
        rows = con.execute(
            """
            select start_time_offset, end_time_offset, offset
            from data
            where channel_group_id = ?
            order by start_time_offset
            """,
            (group_id,),
        ).fetchall()
        calibrations = {row["channel_id"]: _read_calibration(con, row["channel_id"]) for row in channels}
    finally:
        con.close()

    channel_count = int(group["channel_count"])
    sample_width = _sample_width_bytes(int(group["data_type"]))
    labels = [str(row["label"]) for row in channels]
    arrays = []
    times = []
    for row in rows:
        n_samples = int(row["end_time_offset"] - row["start_time_offset"] + 1)
        payload_bytes = n_samples * channel_count * sample_width
        header_len = _infer_packet_header_length(mwx_bytes, int(row["offset"]), payload_bytes, sample_width)
        payload = mwx_bytes[int(row["offset"]) + header_len : int(row["offset"]) + header_len + payload_bytes]
        arr = _decode_interleaved(payload, n_samples, channel_count, sample_width)
        arrays.append(arr)
        ticks = np.arange(int(row["start_time_offset"]), int(row["end_time_offset"]) + 1)
        time_base = float(file_info["time_base"] or config.raw_sampling_hz)
        times.append(ticks / time_base)

    raw = np.vstack(arrays)
    time_s = np.concatenate(times)
    calibrated = {}
    for idx, channel in enumerate(channels):
        slope, intercept = calibrations[int(channel["channel_id"])]
        calibrated[labels[idx]] = raw[:, idx] * slope + intercept
    df = pd.DataFrame({"time_s": time_s, **calibrated})
    sampling_hz = float(file_info["time_base"] or config.raw_sampling_hz)
    return RawSignal(sampling_hz=sampling_hz, samples=df)


def detect_r_peaks_from_raw(raw: RawSignal, config: RSAConfig | None = None) -> pd.DataFrame:
    """Detect R peaks from the calibrated ECG channel."""

    config = config or RSAConfig()
    ecg_col = _ecg_column(raw.samples)
    x = raw.samples[ecg_col].astype(float).to_numpy()
    fs = raw.sampling_hz
    filtered = _ecg_preprocess(x, fs)
    signal = filtered if abs(np.nanpercentile(filtered, 99.5)) >= abs(np.nanpercentile(filtered, 0.5)) else -filtered
    energy = _qrs_energy(signal, fs)

    edge = int(round(fs))
    core_signal = signal[edge:-edge] if signal.size > 2 * edge else signal
    core_energy = energy[edge:-edge] if energy.size > 2 * edge else energy
    amplitude_threshold = float(np.nanpercentile(core_signal, config.raw_peak_threshold_percentile))
    energy_threshold = _adaptive_threshold(core_energy, config.raw_peak_adaptive_mad_multiplier)
    min_distance = int(round(config.raw_peak_min_distance_s * fs))
    refine = max(1, int(round(0.05 * fs)))

    peaks: list[int] = []
    last = -10**9
    start = max(1, edge)
    stop = min(signal.size - 1, signal.size - max(1, int(round(0.05 * fs))))
    for idx in range(start, stop):
        if energy[idx] <= energy_threshold and signal[idx] <= amplitude_threshold:
            continue
        if signal[idx] < signal[idx - 1] or signal[idx] <= signal[idx + 1]:
            continue
        if idx - last < min_distance:
            if peaks and signal[idx] > signal[peaks[-1]]:
                lo = max(start, idx - refine)
                hi = min(stop, idx + refine + 1)
                peak = lo + int(np.nanargmax(signal[lo:hi]))
                if peak - (peaks[-2] if len(peaks) > 1 else -10**9) >= min_distance:
                    peaks[-1] = peak
                    last = peak
            continue
        lo = max(start, idx - refine)
        hi = min(stop, idx + refine + 1)
        peak = lo + int(np.nanargmax(signal[lo:hi]))
        if peak - last >= min_distance:
            peaks.append(peak)
            last = peak

    peak_idx = np.asarray(peaks, dtype=int)
    return pd.DataFrame(
        {
            "peak_index": np.arange(1, peak_idx.size + 1),
            "sample_index": peak_idx,
            "time_s": peak_idx / fs,
            "ecg_value": x[peak_idx],
            "detector_value": signal[peak_idx],
            "qrs_energy": energy[peak_idx],
        }
    )


def peaks_to_ibi(peaks: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    """Convert raw-detected peaks to segment-level IBI rows."""

    config = config or RSAConfig()
    peak_times = peaks["time_s"].dropna().astype(float).to_numpy()
    rows = []
    for segment in range(1, config.expected_segments + 1):
        start = (segment - 1) * config.segment_duration_s
        end = segment * config.segment_duration_s
        segment_peaks = peak_times[(peak_times >= start) & (peak_times < end)]
        ibis = np.diff(segment_peaks) * 1000.0
        for beat_index, ibi_ms in enumerate(ibis, start=1):
            rows.append({"segment": segment, "beat_index": beat_index, "raw_ibi_ms": float(ibi_ms), "ibi_ms": float(ibi_ms)})
    return pd.DataFrame(rows, columns=["segment", "beat_index", "raw_ibi_ms", "ibi_ms"])


def correct_ibi_artifacts(ibi: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    """Flag and interpolate likely raw IBI artifacts.

    The corrected ``ibi_ms`` column is used for analysis. Original values are
    retained in ``raw_ibi_ms`` so every automated correction remains auditable.
    """

    config = config or RSAConfig()
    if ibi.empty:
        return ibi.assign(
            artifact_flag=pd.Series(dtype=bool),
            artifact_reason=pd.Series(dtype=str),
            corrected=pd.Series(dtype=bool),
        )

    out = ibi.copy()
    if "raw_ibi_ms" not in out.columns:
        out["raw_ibi_ms"] = out["ibi_ms"]
    out["artifact_flag"] = False
    out["artifact_reason"] = ""
    out["corrected"] = False

    corrected_segments = []
    for segment, seg in out.groupby("segment", sort=True):
        seg = seg.sort_values("beat_index").copy()
        raw_values = seg["raw_ibi_ms"].astype(float).to_numpy()
        flags, reasons = _artifact_mask(raw_values, config)
        corrected = raw_values.astype(float).copy()
        if np.any(flags):
            valid = np.isfinite(corrected) & ~flags
            if np.count_nonzero(valid) >= 2:
                x = np.arange(corrected.size, dtype=float)
                corrected[flags] = np.interp(x[flags], x[valid], corrected[valid])
            else:
                corrected[flags] = np.nan
        seg["artifact_flag"] = flags
        seg["artifact_reason"] = reasons
        seg["corrected"] = flags & np.isfinite(corrected)
        seg["ibi_ms"] = corrected
        corrected_segments.append(seg)
    return pd.concat(corrected_segments, ignore_index=True)


def raw_peak_qc(peaks: pd.DataFrame, ibi: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    config = config or RSAConfig()
    peak_times = peaks["time_s"].dropna().astype(float).to_numpy()
    rows = []
    for segment in range(1, config.expected_segments + 1):
        start = (segment - 1) * config.segment_duration_s
        end = segment * config.segment_duration_s
        n_peaks = int(np.count_nonzero((peak_times >= start) & (peak_times < end)))
        seg_ibi = ibi[ibi["segment"].eq(segment)]["ibi_ms"].astype(float)
        raw_col = "raw_ibi_ms" if "raw_ibi_ms" in ibi.columns else "ibi_ms"
        raw_seg_ibi = ibi[ibi["segment"].eq(segment)][raw_col].astype(float)
        invalid = raw_seg_ibi[(raw_seg_ibi < config.ibi_min_ms) | (raw_seg_ibi > config.ibi_max_ms)]
        invalid_pct = float(100.0 * len(invalid) / len(seg_ibi)) if len(seg_ibi) else math.nan
        artifact_pct = math.nan
        if "artifact_flag" in ibi.columns and len(seg_ibi):
            artifact_pct = float(100.0 * ibi[ibi["segment"].eq(segment)]["artifact_flag"].fillna(False).astype(bool).sum() / len(seg_ibi))
        qc_pass = (
            n_peaks >= 20
            and (math.isnan(invalid_pct) or invalid_pct <= config.max_edited_percent)
            and (math.isnan(artifact_pct) or artifact_pct <= config.max_edited_percent)
        )
        reason = ""
        if n_peaks < 20:
            reason = "low raw peak count"
        elif not math.isnan(invalid_pct) and invalid_pct > config.max_edited_percent:
            reason = "more than 10% implausible raw IBI values"
        elif not math.isnan(artifact_pct) and artifact_pct > config.max_edited_percent:
            reason = "more than 10% automatically corrected IBI values"
        rows.append(
            {
                "segment": segment,
                "raw_peak_count": n_peaks,
                "raw_ibi_count": int(len(seg_ibi)),
                "raw_invalid_ibi_percent": invalid_pct,
                "raw_artifact_corrected_percent": artifact_pct,
                "qc_pass": qc_pass,
                "qc_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def _find_ecg_group(con: sqlite3.Connection) -> int:
    row = con.execute("select channel_group_id from channel where lower(label) like '%ecg%' limit 1").fetchone()
    if row is None:
        raise ValueError("Could not find an ECG channel in the .mwi file.")
    return int(row["channel_group_id"])


def _read_calibration(con: sqlite3.Connection, channel_id: int) -> tuple[float, float]:
    row = con.execute(
        "select data from post_process where channel_id = ? and label = 'Calibration' limit 1",
        (channel_id,),
    ).fetchone()
    if row is None:
        return 1.0, 0.0
    text = row["data"].decode("utf-8")
    match = re.match(r"([0-9.eE+-]+)\*x\+([0-9.eE+-]+)", text)
    if not match:
        return 1.0, 0.0
    return float(match.group(1)), float(match.group(2))


def _sample_width_bytes(data_type: int) -> int:
    if data_type == 5:
        return 3
    if data_type == 3:
        return 2
    raise ValueError(f"Unsupported MindWare data_type: {data_type}")


def _infer_packet_header_length(data: bytes, offset: int, payload_bytes: int, sample_width: int) -> int:
    for header_len in (15, 12, 16, 24, 32, 38):
        if offset + header_len + payload_bytes <= len(data):
            return header_len
    return 15 if sample_width == 3 else 38


def _decode_interleaved(payload: bytes, n_samples: int, channel_count: int, sample_width: int) -> np.ndarray:
    values = []
    for idx in range(0, len(payload), sample_width):
        chunk = payload[idx : idx + sample_width]
        if len(chunk) < sample_width:
            break
        value = int.from_bytes(chunk, "big", signed=False)
        sign_bit = 1 << (sample_width * 8 - 1)
        full_range = 1 << (sample_width * 8)
        if value & sign_bit:
            value -= full_range
        values.append(value)
    arr = np.asarray(values, dtype=float)
    return arr[: n_samples * channel_count].reshape(n_samples, channel_count)


def _ecg_preprocess(values: np.ndarray, sampling_hz: float) -> np.ndarray:
    baseline_window = max(3, int(round(0.70 * sampling_hz)))
    smooth_window = max(3, int(round(0.012 * sampling_hz)))
    baseline = _moving_average(values, baseline_window)
    high_passed = values - baseline
    return _moving_average(high_passed, smooth_window)


def _qrs_energy(signal: np.ndarray, sampling_hz: float) -> np.ndarray:
    derivative = np.gradient(signal)
    squared = derivative * derivative
    integration_window = max(3, int(round(0.12 * sampling_hz)))
    return _moving_average(squared, integration_window)


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values.astype(float)
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(values, kernel, mode="same")


def _adaptive_threshold(values: np.ndarray, mad_multiplier: float) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return math.inf
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    robust = median + mad_multiplier * 1.4826 * mad
    percentile = float(np.nanpercentile(finite, 90.0))
    return max(robust, percentile)


def _artifact_mask(values: np.ndarray, config: RSAConfig) -> tuple[np.ndarray, np.ndarray]:
    flags = np.zeros(values.size, dtype=bool)
    reasons = np.full(values.size, "", dtype=object)
    finite = np.isfinite(values)
    physiologic = finite & (values >= config.ibi_min_ms) & (values <= config.ibi_max_ms)
    flags |= ~physiologic
    reasons[~physiologic] = "outside physiologic range"

    for idx, value in enumerate(values):
        if not physiologic[idx]:
            continue
        lo = max(0, idx - 3)
        hi = min(values.size, idx + 4)
        neighbors = np.delete(values[lo:hi], idx - lo)
        neighbors = neighbors[
            np.isfinite(neighbors)
            & (neighbors >= config.ibi_min_ms)
            & (neighbors <= config.ibi_max_ms)
        ]
        if neighbors.size < 3:
            continue
        local_median = float(np.median(neighbors))
        if local_median <= 0:
            continue
        abs_delta = abs(float(value) - local_median)
        rel_delta = abs_delta / local_median
        if rel_delta > config.raw_artifact_local_deviation_ratio and abs_delta > config.raw_artifact_local_deviation_ms:
            flags[idx] = True
            reasons[idx] = "local IBI outlier"
    return flags, reasons


def _ecg_column(samples: pd.DataFrame) -> str:
    for col in samples.columns:
        if col != "time_s" and "ecg" in col.lower():
            return col
    raise ValueError("No ECG column found in decoded raw samples.")
