#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from rsa_toolbox.cli import main as rsa_cli_main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Master runner for the RSA physiology toolbox. Point this at a dataset "
            "folder and it will process all available recordings recursively."
        )
    )
    parser.add_argument(
        "dataset_root",
        type=Path,
        help="Dataset folder. Expected layout is usually DATASET/Raw and optional DATASET/Analysis.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("rsa_outputs/master_run"),
        help="Output folder for all generated results.",
    )
    parser.add_argument(
        "--mode",
        choices=("raw", "manual", "both", "auto"),
        default="raw",
        help=(
            "Pipeline mode. 'raw' processes .mwi/.mwx files, 'manual' imports "
            "MindWare HRV workbooks, 'both' runs raw and manual separately, and "
            "'auto' lets the toolbox choose per recording."
        ),
    )
    parser.add_argument(
        "--raw-folder",
        default="Raw",
        help="Name or path of the raw-data folder relative to dataset_root. Use '.' if dataset_root is the raw folder.",
    )
    parser.add_argument(
        "--analysis-folder",
        default="Analysis",
        help="Name or path of the manual MindWare analysis folder relative to dataset_root.",
    )
    parser.add_argument(
        "--bids",
        action="store_true",
        help="Write BIDS-derivative style outputs for raw/auto runs.",
    )
    parser.add_argument(
        "--spectral-preset",
        choices=("default", "mindware-harmonized"),
        default="default",
        help="Frequency-domain estimator preset to pass to the toolbox.",
    )
    parser.add_argument(
        "--spectral-power-scale",
        type=float,
        default=1.0,
        help="Multiplicative scale for absolute LF and HF/RSA powers.",
    )
    parser.add_argument(
        "--bids-task",
        default="rest",
        help="BIDS task label for derivative filenames.",
    )
    args = parser.parse_args(argv)

    dataset_root = args.dataset_root.expanduser().resolve()
    out_root = args.out.expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    runs: list[tuple[str, Path, Path, list[str]]] = []
    if args.mode in {"raw", "both"}:
        raw_root = _resolve_child(dataset_root, args.raw_folder)
        runs.append(("raw", raw_root, out_root / "raw", ["--source", "raw"]))
    elif args.mode == "manual":
        analysis_root = _resolve_child(dataset_root, args.analysis_folder)
        runs.append(("manual", analysis_root, out_root / "manual", ["--source", "mindware"]))
    elif args.mode == "auto":
        runs.append(("auto", dataset_root, out_root / "auto", ["--source", "auto"]))

    if args.mode == "both":
        analysis_root = _resolve_child(dataset_root, args.analysis_folder)
        runs.append(("manual", analysis_root, out_root / "manual", ["--source", "mindware"]))

    manifest_lines = [
        "RSA toolbox master run",
        f"Started: {datetime.now().isoformat(timespec='seconds')}",
        f"Dataset root: {dataset_root}",
        f"Output root: {out_root}",
        f"Mode: {args.mode}",
        f"Spectral preset: {args.spectral_preset}",
        f"Spectral power scale: {args.spectral_power_scale}",
        f"BIDS derivatives requested: {args.bids}",
        "",
    ]

    exit_code = 0
    for label, input_root, output_dir, mode_args in runs:
        if not input_root.exists():
            manifest_lines.append(f"Skipped {label}: input folder not found: {input_root}")
            print(f"Skipping {label}: input folder not found: {input_root}")
            continue

        cli_args = [
            str(input_root),
            "--out",
            str(output_dir),
            *mode_args,
            "--spectral-preset",
            args.spectral_preset,
            "--spectral-power-scale",
            str(args.spectral_power_scale),
            "--bids-task",
            args.bids_task,
        ]
        if args.bids and label in {"raw", "auto"}:
            cli_args.append("--bids")

        manifest_lines.append(f"Running {label}: python -m rsa_toolbox.cli {' '.join(cli_args)}")
        print(f"\n=== Running {label} workflow ===")
        print(f"Input:  {input_root}")
        print(f"Output: {output_dir}")
        try:
            run_code = rsa_cli_main(cli_args)
        except SystemExit as exc:
            run_code = int(exc.code or 0)
        if run_code != 0:
            exit_code = run_code
            manifest_lines.append(f"Run failed: {label} exited with code {run_code}")
            break
        manifest_lines.append(f"Completed {label}: {output_dir}")

    manifest_lines.append("")
    manifest_lines.append(f"Finished: {datetime.now().isoformat(timespec='seconds')}")
    manifest_lines.append(f"Exit code: {exit_code}")
    manifest = out_root / "run_manifest.txt"
    manifest.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"\nRun manifest: {manifest}")
    return exit_code


def _resolve_child(dataset_root: Path, child: str) -> Path:
    path = Path(child).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (dataset_root / path).resolve()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
