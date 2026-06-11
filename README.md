# RSA Physiology Toolbox

This repository contains a Python toolbox for extracting and quality-checking Respiratory Sinus Arrhythmia (RSA) and HRV features from MindWare outputs generated according to `SOP_OPS227`.

The toolbox is intended for analysts who already have MindWare RSA recordings and MindWare HRV Analysis Excel exports.

## What It Does

- Finds MindWare RSA files in an input folder
- Imports MindWare HRV Analysis Excel workbooks
- Reads `.mwi` acquisition metadata
- Extracts segment-level HRV/RSA metrics
- Applies available SOP-derived QC checks
- Computes additional audit and nonlinear IBI features
- Generates CSV, JSON, text, and browser-viewable HTML plot outputs

## Required Inputs

Each recording should include the MindWare files produced during acquisition and artifact correction:

- `.mwi`: MindWare metadata/index file
- `.mwx`: raw MindWare signal file
- `.edh2`: MindWare edit/history file generated after artifact correction
- `*HRV Analysis*.xlsx`: MindWare HRV Analysis workbook generated with `File > Write All Segments`

The HRV Analysis workbook is required for feature extraction. Recordings without this workbook are skipped.

## Installation

Clone the repository:

```bash
git clone git@github.com:andreeadiaconescu/TAY-RSA.git
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

Run the command-line pipeline from the repository root:

```bash
python -m rsa_toolbox.cli /path/to/rsa_input_folder --out /path/to/rsa_output_folder
```

Example:

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs
```

The input folder can contain one recording or many recordings. The pipeline searches recursively for supported files.

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

Transparent recomputation from the exported IBI series.

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

Use this file for audit and exploratory analysis. It is not intended to be an exact clone of MindWare's proprietary calculations.

### `rsa_segment_qc.csv`

Segment-level QC based on available exported editing statistics.

Columns include:

- `segment`
- `max_percent_edited`
- `qc_pass`
- `qc_reason`

Implemented SOP rule:

- fail segment if more than 10% of the segment was edited

### `rsa_nonlinear_features.csv`

Additional segment-level nonlinear IBI features:

- `cv_ibi`
- `poincare_sd1_ms`
- `poincare_sd2_ms`
- `sd1_sd2_ratio`
- `sample_entropy_m2_r02`

Segment-level entropy should be interpreted cautiously because 30-second windows contain a limited number of IBIs.

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

The SOP also states that a segment should not be used if there are more than 3 consecutive midbeats. This rule cannot currently be fully automated from the HRV Analysis workbook alone because detailed consecutive-midbeat events are not exposed in the workbook.

## Analysis Recommendations

For primary study analyses:

1. Use `mindware_hrv_stats_long.csv` and `mindware_power_band_stats_long.csv` as the source of SOP-derived HRV/RSA metrics.
2. Restrict analyses to pass-QC segments from `rsa_segment_qc.csv`.
3. Aggregate valid segments to subject/session-level features when needed.
4. Treat recomputed and nonlinear features as exploratory or secondary features unless separately validated.

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

- Raw `.mwx` signal decoding is not implemented.
- Consecutive-midbeat QC cannot yet be fully automated without detailed edit-event export or validated `.edh2` parsing.
- Segment-level entropy is statistically fragile because each segment has a small number of IBIs.
- Frequency-domain recomputation is not a validated clone of MindWare.
