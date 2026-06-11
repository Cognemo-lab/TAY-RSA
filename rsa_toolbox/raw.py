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
    con = sqlite3.connect(mwi_path)
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
    filtered = _simple_ecg_filter(x, fs)
    signal = filtered if abs(np.nanmax(filtered)) >= abs(np.nanmin(filtered)) else -filtered

    edge = int(round(fs))
    core = signal[edge:-edge] if signal.size > 2 * edge else signal
    threshold = float(np.nanpercentile(core, config.raw_peak_threshold_percentile))
    min_distance = int(round(config.raw_peak_min_distance_s * fs))
    refine = max(1, int(round(0.04 * fs)))

    peaks: list[int] = []
    last = -10**9
    start = max(1, edge)
    stop = min(signal.size - 1, signal.size - max(1, int(round(0.05 * fs))))
    for idx in range(start, stop):
        if signal[idx] <= threshold:
            continue
        if signal[idx] < signal[idx - 1] or signal[idx] <= signal[idx + 1]:
            continue
        if idx - last < min_distance:
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
            rows.append({"segment": segment, "beat_index": beat_index, "ibi_ms": float(ibi_ms)})
    return pd.DataFrame(rows, columns=["segment", "beat_index", "ibi_ms"])


def raw_peak_qc(peaks: pd.DataFrame, ibi: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    config = config or RSAConfig()
    peak_times = peaks["time_s"].dropna().astype(float).to_numpy()
    rows = []
    for segment in range(1, config.expected_segments + 1):
        start = (segment - 1) * config.segment_duration_s
        end = segment * config.segment_duration_s
        n_peaks = int(np.count_nonzero((peak_times >= start) & (peak_times < end)))
        seg_ibi = ibi[ibi["segment"].eq(segment)]["ibi_ms"].astype(float)
        invalid = seg_ibi[(seg_ibi < config.ibi_min_ms) | (seg_ibi > config.ibi_max_ms)]
        invalid_pct = float(100.0 * len(invalid) / len(seg_ibi)) if len(seg_ibi) else math.nan
        qc_pass = n_peaks >= 20 and (math.isnan(invalid_pct) or invalid_pct <= config.max_edited_percent)
        reason = ""
        if n_peaks < 20:
            reason = "low raw peak count"
        elif not math.isnan(invalid_pct) and invalid_pct > config.max_edited_percent:
            reason = "more than 10% implausible raw IBI values"
        rows.append(
            {
                "segment": segment,
                "raw_peak_count": n_peaks,
                "raw_ibi_count": int(len(seg_ibi)),
                "raw_invalid_ibi_percent": invalid_pct,
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


def _simple_ecg_filter(values: np.ndarray, sampling_hz: float) -> np.ndarray:
    baseline_window = max(3, int(round(sampling_hz)))
    smooth_window = max(3, int(round(0.01 * sampling_hz)))
    baseline = np.convolve(values, np.ones(baseline_window) / baseline_window, mode="same")
    high_passed = values - baseline
    return np.convolve(high_passed, np.ones(smooth_window) / smooth_window, mode="same")


def _ecg_column(samples: pd.DataFrame) -> str:
    for col in samples.columns:
        if col != "time_s" and "ecg" in col.lower():
            return col
    raise ValueError("No ECG column found in decoded raw samples.")
