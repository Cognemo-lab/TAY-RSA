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
from .report import write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SOP_OPS227 RSA analysis from MindWare outputs.")
    parser.add_argument("root", type=Path, help="Folder containing .mwi/.mwx and HRV Analysis .xlsx files.")
    parser.add_argument("--out", type=Path, default=Path("rsa_outputs"), help="Output directory.")
    args = parser.parse_args(argv)

    recordings = discover_recordings(args.root)
    if not recordings:
        raise SystemExit(f"No RSA recordings found under {args.root}")

    config = RSAConfig()
    for rec in recordings:
        if rec.hrv_xlsx is None:
            print(f"Skipping {rec.stem}: no MindWare HRV Analysis workbook yet.")
            continue
        workbook = read_mindware_hrv_workbook(rec.hrv_xlsx)
        metrics = analyze_ibi_segments(workbook["ibi"], config)
        nonlinear = analyze_nonlinear_features(workbook["ibi"], config)
        mse = analyze_multiscale_entropy(workbook["ibi"], config)
        qc = apply_sop_qc(workbook["editing_stats"], config)
        metadata = read_mwi_metadata(rec.mwi) if rec.mwi else None
        out_dir = args.out / rec.stem
        plot_html = write_feature_plots(out_dir, metrics, nonlinear, mse, workbook["power_band_stats"])
        paths = write_outputs(
            out_dir,
            metadata,
            metrics,
            qc,
            workbook["settings"],
            workbook["hrv_stats"],
            workbook["power_band_stats"],
            nonlinear,
            mse,
            plot_html,
        )
        print(f"Wrote {rec.stem}: {paths['summary_txt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
