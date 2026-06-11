from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def write_outputs(
    out_dir: str | Path,
    metadata: dict | None,
    computed_metrics: pd.DataFrame,
    qc: pd.DataFrame,
    settings: dict | None = None,
    mindware_hrv_stats: pd.DataFrame | None = None,
    mindware_power_stats: pd.DataFrame | None = None,
    nonlinear_features: pd.DataFrame | None = None,
    mse_curve: pd.DataFrame | None = None,
    plot_html: Path | None = None,
    raw_peaks: pd.DataFrame | None = None,
    raw_ibi: pd.DataFrame | None = None,
    subject_features: pd.DataFrame | None = None,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "metrics_csv": out_dir / "rsa_segment_metrics.csv",
        "qc_csv": out_dir / "rsa_segment_qc.csv",
        "summary_txt": out_dir / "rsa_summary.txt",
    }
    computed_metrics.to_csv(paths["metrics_csv"], index=False)
    qc.to_csv(paths["qc_csv"], index=False)
    if mindware_hrv_stats is not None:
        paths["mindware_hrv_csv"] = out_dir / "mindware_hrv_stats_long.csv"
        mindware_hrv_stats.to_csv(paths["mindware_hrv_csv"], index=False)
    if mindware_power_stats is not None:
        paths["mindware_power_csv"] = out_dir / "mindware_power_band_stats_long.csv"
        mindware_power_stats.to_csv(paths["mindware_power_csv"], index=False)
    if nonlinear_features is not None:
        paths["nonlinear_csv"] = out_dir / "rsa_nonlinear_features.csv"
        nonlinear_features.to_csv(paths["nonlinear_csv"], index=False)
    if mse_curve is not None:
        paths["mse_csv"] = out_dir / "rsa_multiscale_entropy.csv"
        mse_curve.to_csv(paths["mse_csv"], index=False)
    if plot_html is not None:
        paths["plots_html"] = Path(plot_html)
    if raw_peaks is not None:
        paths["raw_peaks_csv"] = out_dir / "raw_detected_peaks.csv"
        raw_peaks.to_csv(paths["raw_peaks_csv"], index=False)
    if raw_ibi is not None:
        paths["raw_ibi_csv"] = out_dir / "raw_detected_ibi.csv"
        raw_ibi.to_csv(paths["raw_ibi_csv"], index=False)
    if subject_features is not None:
        paths["subject_features_csv"] = out_dir / "rsa_subject_features.csv"
        subject_features.to_csv(paths["subject_features_csv"], index=False)
    if metadata is not None:
        paths["metadata_json"] = out_dir / "mwi_metadata.json"
        paths["metadata_json"].write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _write_summary(paths["summary_txt"], computed_metrics, qc, settings, mindware_power_stats, nonlinear_features, mse_curve, plot_html, subject_features)
    return paths


def _write_summary(
    path: Path,
    metrics: pd.DataFrame,
    qc: pd.DataFrame,
    settings: dict | None,
    mindware_power_stats: pd.DataFrame | None,
    nonlinear_features: pd.DataFrame | None,
    mse_curve: pd.DataFrame | None,
    plot_html: Path | None,
    subject_features: pd.DataFrame | None,
) -> None:
    merged = metrics.merge(qc, on="segment", how="left")
    passed = merged[merged["qc_pass"].fillna(False)]
    lines = ["RSA preprocessing and analysis summary", ""]
    if settings:
        for key in ["File Name", "Version", "Date", "Start Time", "End Time", "Segment Time"]:
            if key in settings:
                lines.append(f"{key}: {settings[key]}")
        lines.append("")
    lines.append(f"Segments analyzed: {len(merged)}")
    lines.append(f"Segments passing SOP QC: {len(passed)}")
    if not passed.empty:
        if mindware_power_stats is not None and not mindware_power_stats.empty:
            hf = mindware_power_stats[mindware_power_stats["metric"].eq("HF/RSA Power")].copy()
            hf["value"] = pd.to_numeric(hf["value"], errors="coerce")
            hf = hf[hf["segment"].isin(passed["segment"])]
            if not hf.empty:
                lines.append(f"Mean MindWare HF/RSA power across passing segments: {hf['value'].mean():.6g}")
        lines.append(f"Mean recomputed HF/RSA power across passing segments: {passed['hf_rsa_power'].mean():.6g}")
        lines.append(f"Mean RMSSD across passing segments: {passed['rmssd_ms'].mean():.6g} ms")
        if nonlinear_features is not None and not nonlinear_features.empty:
            entropy = pd.to_numeric(nonlinear_features["sample_entropy_m2_r02"], errors="coerce")
            lines.append(f"Mean segment sample entropy: {entropy.mean():.6g}")
        if mse_curve is not None and not mse_curve.empty:
            mse = pd.to_numeric(mse_curve["sample_entropy_m2_r02"], errors="coerce")
            lines.append(f"Full-recording MSE AUC: {mse.sum():.6g}")
    failed = merged[~merged["qc_pass"].fillna(False)]
    if not failed.empty:
        lines.append("")
        lines.append("Failed segments:")
        for _, row in failed.iterrows():
            reason = row.get("qc_reason") or "unspecified"
            lines.append(f"- Segment {int(row['segment'])}: {reason}")
    if plot_html is not None:
        lines.append("")
        lines.append(f"Feature plots: {plot_html}")
    if subject_features is not None:
        lines.append("Subject/session features: rsa_subject_features.csv")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
