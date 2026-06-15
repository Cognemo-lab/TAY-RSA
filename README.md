# RSA Physiology Toolbox

This repository contains a Python toolbox for extracting and quality-checking Respiratory Sinus Arrhythmia (RSA) and HRV features from MindWare outputs generated according to `SOP_OPS227`.

The toolbox is intended for analysts who have MindWare RSA recordings, MindWare HRV Analysis Excel exports, or both.

## What It Does

- Finds MindWare RSA files in an input folder
- Imports MindWare HRV Analysis Excel workbooks
- Reads `.mwi` acquisition metadata
- Extracts segment-level HRV/RSA metrics
- Applies available SOP-derived QC checks
- Computes additional audit and nonlinear IBI features
- Generates CSV, JSON, text, and browser-viewable HTML plot outputs
- Writes one-row-per-subject/session feature tables for downstream analyses
- Routes each recording through a MindWare-processed or raw automatic pathway from one command-line entry point

## Required Inputs

Each recording should include the MindWare files produced during acquisition and artifact correction:

- `.mwi`: MindWare metadata/index file
- `.mwx`: raw MindWare signal file
- `.edh2`: MindWare edit/history file generated after artifact correction
- `*HRV Analysis*.xlsx`: MindWare HRV Analysis workbook generated with `File > Write All Segments`

The HRV Analysis workbook is required for the MindWare-processed pathway. The raw pathway can run from paired `.mwi/.mwx` files without the workbook.

## Installation

Clone the repository:

```bash
git clone git@github.com:Cognemo-lab/TAY-RSA.git
cd TAY-RSA
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install numpy pandas openpyxl
```

## Running The Toolbox

The master entry point is `rsa_toolbox.cli`. Run it from the repository root:

```bash
python -m rsa_toolbox.cli /path/to/rsa_input_folder --out /path/to/rsa_output_folder
```

Example:

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs
```

The input folder can contain one recording or many recordings. The pipeline searches recursively for supported files.

## Processing Modes

The master script can funnel each recording through one of three processing modes with `--source`.

### `--source auto`

Recommended default.

Uses the MindWare HRV Analysis workbook when one is present. If no workbook is found, it falls back to automatic raw ECG processing from paired `.mwi/.mwx` files.

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs --source auto
```

### `--source mindware`

Uses only MindWare-processed HRV Analysis workbooks. This is the recommended mode for primary SOP-derived RSA/HRV analyses.

Recordings without an HRV Analysis workbook are skipped.

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs --source mindware
```

### `--source raw`

Uses only automatic raw processing from paired `.mwi/.mwx` files. This mode decodes the raw ECG channel, detects R peaks, creates IBIs, computes HRV/nonlinear/MSE features, and writes raw detection QC files.

This mode is useful when MindWare workbook exports are unavailable or when comparing automatic detection to MindWare-edited outputs. It should be validated against manually corrected MindWare outputs before replacing SOP-derived analyses.

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs --source raw
```

## File Pairing

The toolbox searches for:

- `.mwi`
- `.mwx`
- `.edh2`
- `.xlsx` files containing `HRV Analysis` in the filename

Files are paired by recording stem. The pairing logic tolerates small naming differences between raw files and MindWare workbook exports, such as an extra visit/run token in the raw filename.

## Outputs

Each recording gets a separate output folder:

```text
<output_folder>/<recording_id>/
```

A combined subject/session feature table is also written to:

```text
<output_folder>/rsa_all_subject_features.csv
```

Output availability depends on the processing mode:

| Output | `mindware` | `raw` | Notes |
|---|---:|---:|---|
| `rsa_summary.txt` | yes | yes | Text summary |
| `rsa_subject_features.csv` | yes | yes | One row per recording |
| `rsa_all_subject_features.csv` | yes | yes | One row per processed recording |
| `rsa_segment_metrics.csv` | yes | yes | Computed from workbook IBI or raw-detected IBI |
| `rsa_segment_qc.csv` | yes | yes | Workbook editing QC or raw detection QC |
| `rsa_nonlinear_features.csv` | yes | yes | Segment nonlinear features |
| `rsa_multiscale_entropy.csv` | yes | yes | Full-recording MSE |
| `mwi_metadata.json` | yes, if `.mwi` exists | yes | Raw metadata |
| `plots/feature_plots.html` | yes | yes | Browser-viewable plots |
| `mindware_hrv_stats_long.csv` | yes | no | Imported MindWare HRV Stats |
| `mindware_power_band_stats_long.csv` | yes | no | Imported MindWare Power Band Stats |
| `raw_detected_peaks.csv` | no | yes | Automatic R peaks |
| `raw_detected_ibi.csv` | no | yes | Raw-derived IBI values |

### `rsa_summary.txt`

Text summary of the run, including:

- source file information
- MindWare workbook metadata
- number of analyzed segments
- number of pass-QC segments
- mean MindWare HF/RSA power
- mean recomputed HF/RSA power
- mean RMSSD
- mean sample entropy
- full-recording multiscale entropy area under the curve
- path to the HTML feature plots
- path to the subject/session feature table

### `rsa_subject_features.csv`

One-row subject/session table for the recording.

This file aggregates pass-QC segments into fixed features, including:

- recording ID
- parsed subject ID
- source mode: `mindware` or `raw`
- segment counts and percent passing QC
- subject/session QC pass flag
- mean/median/min/max computed HRV metrics
- mean/median/min/max MindWare HRV/RSA metrics when available
- mean/median/min/max nonlinear features
- multiscale entropy values by scale
- multiscale entropy summary values
- raw peak counts when raw mode is used

In `auto` mode, the `source` column records which pathway was used for each recording.

### `<output_folder>/rsa_all_subject_features.csv`

Combined one-row-per-recording table across all processed recordings.

Use this file for merging RSA features with clinical, behavioral, or demographic datasets.

### `mindware_hrv_stats_long.csv`

Long-format import of MindWare's HRV Stats sheet. These are primary SOP-derived HRV outputs.

Common metrics include:

- `Mean Heart Rate`
- `Mean IBI`
- `AVNN`
- `SDNN`
- `RMSSD`
- `NN50`
- `pNN50`
- `RSA`
- `# of R's Found`
- segment start/end/duration fields

### `mindware_power_band_stats_long.csv`

Long-format import of MindWare's Power Band Stats sheet. These are primary SOP-derived frequency-domain outputs.

Common metrics include:

- `LF Power`
- `LF Peak Power Frequency`
- `HF/RSA Power`
- `HF/RSA Peak Power Frequency`
- `LF/HF Ratio`

### `rsa_segment_metrics.csv`

Transparent recomputation from the IBI series used by the selected pathway.

Metrics include:

- `n_ibi`
- `mean_ibi_ms`
- `mean_hr_bpm`
- `sdnn_ms`
- `rmssd_ms`
- `lf_power`
- `hf_rsa_power`
- `lf_hf_ratio`
- `hf_peak_hz`

In `mindware` mode, this file is computed from the IBI sheet exported by MindWare. In `raw` mode, it is computed from automatically detected R peaks in the raw ECG trace.

Use this file for audit and exploratory analysis. It is not intended to be an exact clone of MindWare's proprietary calculations.

### `rsa_segment_qc.csv`

Segment-level QC for the selected pathway.

Columns include:

- `segment`
- `max_percent_edited`
- `qc_pass`
- `qc_reason`

Implemented SOP rule:

- fail segment if more than 10% of the segment was edited

In `mindware` mode, QC is based on available exported editing statistics. In `raw` mode, workbook editing percentages are not available, so QC is based on raw peak count and implausible IBI percentage.

### `raw_detected_peaks.csv`

Generated only when raw automatic peak detection is used.

Columns include:

- `peak_index`
- `sample_index`
- `time_s`
- `ecg_value`
- `detector_value`

### `raw_detected_ibi.csv`

Generated only when raw automatic peak detection is used.

Columns include:

- `segment`
- `beat_index`
- `ibi_ms`

### `rsa_nonlinear_features.csv`

Additional segment-level nonlinear IBI features:

- `cv_ibi`
- `poincare_sd1_ms`
- `poincare_sd2_ms`
- `sd1_sd2_ratio`
- `sample_entropy_m2_r02`

Segment-level entropy should be interpreted cautiously because 30-second windows contain a limited number of IBIs.

This file is generated in both `mindware` and `raw` modes. The underlying IBI source differs by mode.

### `rsa_multiscale_entropy.csv`

Full-recording multiscale entropy computed from the exported IBI series.

Columns include:

- `scope`
- `scale`
- `n_points`
- `sample_entropy_m2_r02`

Entropy parameters:

- embedding dimension: `m = 2`
- tolerance: `r = 0.2 * SD`
- coarse-graining scales: `1-10`

Blank entropy values can occur when too few valid template matches are available at a scale.

This file is generated in both `mindware` and `raw` modes. The underlying IBI source differs by mode.

### `mwi_metadata.json`

Metadata read from the raw `.mwi` SQLite file, including:

- file information
- devices
- channel labels
- channel groups
- event timing
- packet ranges

Use this file for acquisition traceability and metadata QC.

### `plots/feature_plots.html`

Self-contained browser-viewable plot report.

The report includes:

- mean HR by segment
- RMSSD by segment
- recomputed HF/RSA power by segment
- MindWare HF/RSA power by segment
- sample entropy by segment
- full-recording multiscale entropy curve

Open this file in any web browser.

## QC Guidance

For a standard `SOP_OPS227` recording, expect:

- 4 minutes of recording
- 8 segments
- 30 seconds per segment
- low or zero percent edited when signal quality is good
- no segment with more than 10% edited data

Recommended QC checks:

- Confirm expected segments are present.
- Confirm all or most segments pass QC.
- Review `max_percent_edited`.
- Review `% Normal Peaks` in the MindWare editing statistics.
- Inspect unusually high LF/HF ratio segments.
- Inspect missing entropy values at larger MSE scales.
- Open `feature_plots.html` and look for abrupt segment outliers.
- In raw mode, review `raw_detected_peaks.csv`, `raw_detected_ibi.csv`, and raw peak counts before using the outputs analytically.

The SOP also states that a segment should not be used if there are more than 3 consecutive midbeats. This rule cannot currently be fully automated from the HRV Analysis workbook alone because detailed consecutive-midbeat events are not exposed in the workbook.

## Analysis Recommendations

For primary study analyses:

1. Use `mindware_hrv_stats_long.csv` and `mindware_power_band_stats_long.csv` as the source of SOP-derived HRV/RSA metrics.
2. Restrict analyses to pass-QC segments from `rsa_segment_qc.csv`.
3. Aggregate valid segments to subject/session-level features when needed.
4. Use `rsa_subject_features.csv` or `rsa_all_subject_features.csv` for downstream subject/session-level analyses.
5. Treat recomputed, raw-derived, and nonlinear features as exploratory or secondary features unless separately validated.

Common subject/session-level features include:

- mean MindWare `HF/RSA Power` across pass-QC segments
- mean MindWare `RSA` across pass-QC segments
- mean `RMSSD`
- mean `SDNN`
- mean `Mean Heart Rate`
- mean `LF/HF Ratio`
- valid segment count
- percent segments passing QC
- mean segment sample entropy
- full-recording multiscale entropy area under the curve

## Validation Notes

The canonical SOP-derived HRV/RSA metrics are the values imported from the MindWare HRV Analysis Excel workbook.

The toolbox also recomputes some metrics from the exported IBI series. These recomputed metrics are useful for reproducibility checks, exploratory analyses, and QC, but they should not be treated as exact replacements for MindWare's proprietary HRV/RSA calculations. MindWare may use proprietary handling of edited beats, interpolation, detrending, windowing, and spectral integration.

The raw automatic path decodes the observed MindWare Mobile `.mwi/.mwx` packet format and detects R peaks from the ECG channel using a simple automatic detector. This path is intended to reduce reliance on manual workbook exports, but it should be validated against MindWare-edited outputs before being used as the primary analysis source.

## Troubleshooting

### No recordings found

Check that the input folder contains supported MindWare files or HRV Analysis workbooks.

### Recording skipped

The recording likely does not have a MindWare HRV Analysis workbook. Run MindWare artifact correction and `Write All Segments` first.

### Entropy values are blank

Blank entropy values usually mean the segment or coarse-grained series had too few valid template matches. This is common for short 30-second segments.

### Recomputed metrics do not match MindWare

This is expected. Treat recomputed metrics as audit or exploratory features, not primary SOP-derived values.

## Current Limitations

- Raw `.mwx` signal decoding is implemented for the observed MindWare Mobile packet layout only and may need validation on additional devices/software versions.
- Consecutive-midbeat QC cannot yet be fully automated without detailed edit-event export or validated `.edh2` parsing.
- Segment-level entropy is statistically fragile because each segment has a small number of IBIs.
- Frequency-domain recomputation is not a validated clone of MindWare.
