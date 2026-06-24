from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


def build_subject_features(
    recording_id: str,
    source: str,
    metrics: pd.DataFrame,
    qc: pd.DataFrame,
    nonlinear_features: pd.DataFrame | None = None,
    mse_curve: pd.DataFrame | None = None,
    settings: dict | None = None,
    metadata: dict | None = None,
    mindware_hrv_stats: pd.DataFrame | None = None,
    mindware_power_stats: pd.DataFrame | None = None,
    raw_peaks: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Create a one-row subject/session feature table."""

    row: dict[str, Any] = {
        "recording_id": recording_id,
        "subject_id": _subject_id_from_recording(recording_id),
        "source": source,
    }

    if settings:
        for key, out_key in {
            "Version": "mindware_version",
            "Date": "mindware_date",
            "Time": "mindware_time",
            "File Name": "mindware_file_name",
            "Start Time": "settings_start_time_s",
            "End Time": "settings_end_time_s",
            "Segment Time": "settings_segment_time_s",
        }.items():
            if key in settings:
                row[out_key] = settings[key]

    if metadata:
        info = metadata.get("file_information", {})
        row["mwi_label"] = info.get("label")
        row["mwi_time_base_hz"] = info.get("time_base")
        row["mwi_file_duration_ticks"] = info.get("file_duration")

    merged = metrics.merge(qc[["segment", "qc_pass"]], on="segment", how="left")
    passed = merged[merged["qc_pass"].fillna(False)]
    row["n_segments"] = int(len(merged))
    row["n_segments_pass_qc"] = int(len(passed))
    row["percent_segments_pass_qc"] = _percent(len(passed), len(merged))
    row["subject_qc_pass"] = bool(len(passed) > 0 and len(passed) == len(merged))

    if "max_percent_edited" in qc:
        edited = pd.to_numeric(qc["max_percent_edited"], errors="coerce")
        row["max_percent_edited"] = _finite_max(edited)
        row["mean_percent_edited"] = _finite_mean(edited)
    if "raw_peak_count" in qc:
        row["raw_total_peaks"] = int(pd.to_numeric(qc["raw_peak_count"], errors="coerce").fillna(0).sum())
        row["raw_min_segment_peaks"] = _finite_min(pd.to_numeric(qc["raw_peak_count"], errors="coerce"))
    if raw_peaks is not None:
        row["raw_detected_total_peaks"] = int(len(raw_peaks))

    for col in [
        "n_ibi",
        "mean_ibi_ms",
        "mean_hr_bpm",
        "sdnn_ms",
        "rmssd_ms",
        "lf_power",
        "hf_rsa_power",
        "lf_hf_ratio",
        "hf_peak_hz",
        "lf_power_uncalibrated",
        "hf_rsa_power_uncalibrated",
        "spectral_power_scale",
    ]:
        _add_summary_stats(row, passed, col, f"computed_{col}")

    for col in [
        "spectral_window",
        "spectral_detrend",
        "spectral_interpolate_band_edges",
        "spectral_time_mode",
    ]:
        if col in passed and not passed.empty:
            row[f"computed_{col}"] = passed[col].iloc[0]

    if nonlinear_features is not None and not nonlinear_features.empty:
        nonlin = nonlinear_features.merge(qc[["segment", "qc_pass"]], on="segment", how="left")
        nonlin_passed = nonlin[nonlin["qc_pass"].fillna(False)]
        for col in [
            "cv_ibi",
            "poincare_sd1_ms",
            "poincare_sd2_ms",
            "sd1_sd2_ratio",
            "sample_entropy_m2_r02",
        ]:
            _add_summary_stats(row, nonlin_passed, col, f"nonlinear_{col}")

    if mse_curve is not None and not mse_curve.empty:
        entropy = pd.to_numeric(mse_curve["sample_entropy_m2_r02"], errors="coerce")
        row["mse_auc_sum"] = _finite_sum(entropy)
        row["mse_mean_entropy"] = _finite_mean(entropy)
        row["mse_n_valid_scales"] = int(entropy.notna().sum())
        for _, mse_row in mse_curve.iterrows():
            scale = int(mse_row["scale"])
            row[f"mse_scale_{scale}"] = mse_row["sample_entropy_m2_r02"]

    if mindware_hrv_stats is not None and not mindware_hrv_stats.empty:
        _add_mindware_metric_summaries(
            row,
            mindware_hrv_stats,
            passed["segment"],
            {
                "Mean Heart Rate": "mindware_mean_heart_rate",
                "Mean IBI": "mindware_mean_ibi",
                "AVNN": "mindware_avnn",
                "SDNN": "mindware_sdnn",
                "RMSSD": "mindware_rmssd",
                "NN50": "mindware_nn50",
                "pNN50": "mindware_pnn50",
                "RSA": "mindware_rsa",
                "# of R's Found": "mindware_r_found",
            },
        )

    if mindware_power_stats is not None and not mindware_power_stats.empty:
        _add_mindware_metric_summaries(
            row,
            mindware_power_stats,
            passed["segment"],
            {
                "LF Power": "mindware_lf_power",
                "HF/RSA Power": "mindware_hf_rsa_power",
                "LF/HF Ratio": "mindware_lf_hf_ratio",
                "LF Peak Power Frequency": "mindware_lf_peak_hz",
                "HF/RSA Peak Power Frequency": "mindware_hf_rsa_peak_hz",
            },
        )

    return pd.DataFrame([row])


def _subject_id_from_recording(recording_id: str) -> str:
    match = re.match(r"(.+?)(?:_\d+)?_SE\d+_RSA$", recording_id)
    if match:
        return match.group(1)
    return recording_id


def _add_summary_stats(row: dict[str, Any], frame: pd.DataFrame, col: str, prefix: str) -> None:
    if col not in frame:
        return
    values = pd.to_numeric(frame[col], errors="coerce")
    row[f"{prefix}_mean"] = _finite_mean(values)
    row[f"{prefix}_median"] = _finite_median(values)
    row[f"{prefix}_min"] = _finite_min(values)
    row[f"{prefix}_max"] = _finite_max(values)


def _add_mindware_metric_summaries(
    row: dict[str, Any],
    stats: pd.DataFrame,
    pass_segments: pd.Series,
    mapping: dict[str, str],
) -> None:
    pass_set = set(pd.to_numeric(pass_segments, errors="coerce").dropna().astype(int))
    for metric_name, prefix in mapping.items():
        values = stats[stats["metric"].eq(metric_name)].copy()
        if pass_set:
            values = values[values["segment"].isin(pass_set)]
        series = pd.to_numeric(values["value"], errors="coerce")
        row[f"{prefix}_mean"] = _finite_mean(series)
        row[f"{prefix}_median"] = _finite_median(series)
        row[f"{prefix}_min"] = _finite_min(series)
        row[f"{prefix}_max"] = _finite_max(series)


def write_cohort_subject_features(out_dir: str | Path, rows: list[pd.DataFrame]) -> Path | None:
    if not rows:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = pd.concat(rows, ignore_index=True, sort=False)
    path = out_dir / "rsa_all_subject_features.csv"
    combined.to_csv(path, index=False)
    return path


def _percent(numerator: int, denominator: int) -> float:
    return float(100.0 * numerator / denominator) if denominator else math.nan


def _finite_mean(values: pd.Series) -> float:
    values = values.dropna()
    return float(values.mean()) if len(values) else math.nan


def _finite_median(values: pd.Series) -> float:
    values = values.dropna()
    return float(values.median()) if len(values) else math.nan


def _finite_min(values: pd.Series) -> float:
    values = values.dropna()
    return float(values.min()) if len(values) else math.nan


def _finite_max(values: pd.Series) -> float:
    values = values.dropna()
    return float(values.max()) if len(values) else math.nan


def _finite_sum(values: pd.Series) -> float:
    values = values.dropna()
    return float(values.sum()) if len(values) else math.nan
