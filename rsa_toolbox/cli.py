from __future__ import annotations

import argparse
from pathlib import Path

from .config import RSAConfig
from .dataset import discover_recordings
from .excel import read_mindware_hrv_workbook
from .hrv import analyze_ibi_segments, analyze_multiscale_entropy, analyze_nonlinear_features
from .mindware import read_mwi_metadata
from .plots import write_feature_plots
from .qc import apply_sop_qc
from .raw import detect_r_peaks_from_raw, peaks_to_ibi, raw_peak_qc, read_mindware_raw_signal
from .report import write_outputs
from .subject import build_subject_features, write_cohort_subject_features


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SOP_OPS227 RSA analysis from MindWare outputs or raw files.")
    parser.add_argument("root", type=Path, help="Folder containing .mwi/.mwx and HRV Analysis .xlsx files.")
    parser.add_argument("--out", type=Path, default=Path("rsa_outputs"), help="Output directory.")
    parser.add_argument(
        "--source",
        choices=("auto", "mindware", "raw"),
        default="auto",
        help="Use MindWare workbook outputs, raw automatic peak detection, or auto fallback.",
    )
    args = parser.parse_args(argv)

    recordings = discover_recordings(args.root)
    if not recordings:
        raise SystemExit(f"No RSA recordings found under {args.root}")

    config = RSAConfig()
    subject_feature_rows = []
    for rec in recordings:
        use_raw = args.source == "raw" or (args.source == "auto" and rec.hrv_xlsx is None)
        if args.source == "mindware" and rec.hrv_xlsx is None:
            print(f"Skipping {rec.stem}: no MindWare HRV Analysis workbook yet.")
            continue
        raw_peaks = None
        raw_ibi = None
        workbook = None
        mindware_hrv_stats = None
        mindware_power_stats = None
        settings = None

        if use_raw:
            if rec.mwi is None or rec.mwx is None:
                print(f"Skipping {rec.stem}: raw source requires paired .mwi and .mwx files.")
                continue
            raw_signal = read_mindware_raw_signal(rec.mwi, rec.mwx, config)
            raw_peaks = detect_r_peaks_from_raw(raw_signal, config)
            raw_ibi = peaks_to_ibi(raw_peaks, config)
            analysis_ibi = raw_ibi
            qc = raw_peak_qc(raw_peaks, raw_ibi, config)
        else:
            if rec.hrv_xlsx is None:
                print(f"Skipping {rec.stem}: no MindWare HRV Analysis workbook yet.")
                continue
            workbook = read_mindware_hrv_workbook(rec.hrv_xlsx)
            analysis_ibi = workbook["ibi"]
            qc = apply_sop_qc(workbook["editing_stats"], config)
            mindware_hrv_stats = workbook["hrv_stats"]
            mindware_power_stats = workbook["power_band_stats"]
            settings = workbook["settings"]

        metrics = analyze_ibi_segments(analysis_ibi, config)
        nonlinear = analyze_nonlinear_features(analysis_ibi, config)
        mse = analyze_multiscale_entropy(analysis_ibi, config)
        metadata = read_mwi_metadata(rec.mwi) if rec.mwi else None
        source_label = "raw" if use_raw else "mindware"
        subject_features = build_subject_features(
            rec.stem,
            source_label,
            metrics,
            qc,
            nonlinear,
            mse,
            settings,
            metadata,
            mindware_hrv_stats,
            mindware_power_stats,
            raw_peaks,
        )
        subject_feature_rows.append(subject_features)
        out_dir = args.out / rec.stem
        plot_html = write_feature_plots(out_dir, metrics, nonlinear, mse, mindware_power_stats)
        paths = write_outputs(
            out_dir,
            metadata,
            metrics,
            qc,
            settings,
            mindware_hrv_stats,
            mindware_power_stats,
            nonlinear,
            mse,
            plot_html,
            raw_peaks,
            raw_ibi,
            subject_features,
        )
        print(f"Wrote {rec.stem}: {paths['summary_txt']}")
    cohort_path = write_cohort_subject_features(args.out, subject_feature_rows)
    if cohort_path is not None:
        print(f"Wrote cohort subject features: {cohort_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
