# RSA Physiology Toolbox

This repository contains a Python toolbox for extracting and quality-checking Respiratory Sinus Arrhythmia (RSA) and HRV features directly from raw MindWare `.mwi/.mwx` recordings generated according to `SOP_OPS227`.

The main workflow is designed to reduce reliance on proprietary MindWare HRV software by decoding raw ECG recordings, detecting R peaks, deriving IBIs, computing HRV/RSA features, and exporting QC-ready analysis tables. MindWare HRV Analysis Excel workbooks can still be imported when available for validation, comparison, or backwards compatibility.

## What It Does

- Finds raw MindWare RSA files in an input folder
- Decodes raw `.mwi/.mwx` recordings
- Detects R peaks from the raw ECG channel
- Derives segment-level IBI series
- Reads `.mwi` acquisition metadata
- Extracts segment-level HRV/RSA metrics
- Applies raw peak/IBI QC checks
- Computes nonlinear IBI features and multiscale entropy
- Generates CSV, JSON, text, and browser-viewable HTML plot outputs
- Writes one-row-per-subject/session feature tables for downstream analyses
- Optionally imports MindWare HRV Analysis workbooks for comparison with manually processed outputs

## Required Inputs

The raw workflow requires the files produced at acquisition:

- `.mwi`: MindWare metadata/index file
- `.mwx`: raw MindWare signal file

Optional comparison files:

- `.edh2`: MindWare edit/history file generated after manual artifact correction
- `*HRV Analysis*.xlsx`: MindWare HRV Analysis workbook generated with `File > Write All Segments`

The raw pathway can run from paired `.mwi/.mwx` files without the `.edh2` file or the HRV Analysis workbook.

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

By default, the master script uses the raw-data workflow. The following command is equivalent to adding `--source raw`:

Raw-data workflow:

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs --source raw
```

The input folder can contain one recording or many recordings. The pipeline searches recursively for supported files.

## Processing Modes

The master script can funnel each recording through one of three processing modes with `--source`.

### `--source raw`

Recommended and default workflow when the goal is to analyze data without relying on proprietary MindWare HRV software.

This mode uses paired `.mwi/.mwx` files, decodes the raw ECG channel, detects R peaks, creates IBIs, computes HRV/nonlinear/MSE features, and writes raw detection QC files.

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs --source raw
```

### `--source auto`

Convenience workflow for mixed folders.

Uses raw automatic processing when only `.mwi/.mwx` files are present. If a MindWare HRV Analysis workbook is also present, the current implementation uses the workbook path for that recording so previously processed datasets can still be reproduced.

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs --source auto
```

### `--source mindware`

Uses only MindWare-processed HRV Analysis workbooks. This mode is useful for validation, comparison to historical analyses, or reproducing manually processed outputs.

Recordings without an HRV Analysis workbook are skipped.

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs --source mindware
```

When validating the raw pipeline, run both `--source raw` and `--source mindware` on the same recordings and compare `rsa_subject_features.csv`, `rsa_segment_metrics.csv`, and the peak/IBI counts.

## File Pairing

The toolbox searches for:

- `.mwi`
- `.mwx`
- optional `.edh2`
- optional `.xlsx` files containing `HRV Analysis` in the filename

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

| Output | `raw` | `mindware` | Notes |
|---|---:|---:|---|
| `rsa_summary.txt` | yes | yes | Text summary |
| `rsa_subject_features.csv` | yes | yes | One row per recording |
| `rsa_all_subject_features.csv` | yes | yes | One row per processed recording |
| `rsa_segment_metrics.csv` | yes | yes | Computed from raw-detected IBI or workbook IBI |
| `rsa_segment_qc.csv` | yes | yes | Raw detection QC or workbook editing QC |
| `rsa_nonlinear_features.csv` | yes | yes | Segment nonlinear features |
| `rsa_multiscale_entropy.csv` | yes | yes | Full-recording MSE |
| `mwi_metadata.json` | yes | yes, if `.mwi` exists | Raw metadata |
| `plots/feature_plots.html` | yes | yes | Browser-viewable plots |
| `raw_detected_peaks.csv` | yes | no | Automatic R peaks |
| `raw_detected_ibi.csv` | yes | no | Raw-derived IBI values |
| `mindware_hrv_stats_long.csv` | no | yes | Imported MindWare HRV Stats |
| `mindware_power_band_stats_long.csv` | no | yes | Imported MindWare Power Band Stats |

### `rsa_summary.txt`

Text summary of the run, including:

- source file information
- raw acquisition metadata
- number of analyzed segments
- number of pass-QC segments
- mean HF/RSA power
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
- mean/median/min/max nonlinear features
- multiscale entropy values by scale
- multiscale entropy summary values
- raw peak counts when raw mode is used
- mean/median/min/max MindWare HRV/RSA metrics when workbook comparison files are available

In `auto` mode, the `source` column records which pathway was used for each recording.

### `<output_folder>/rsa_all_subject_features.csv`

Combined one-row-per-recording table across all processed recordings.

Use this file for merging RSA features with clinical, behavioral, or demographic datasets.

### `mindware_hrv_stats_long.csv`

Long-format import of MindWare's HRV Stats sheet. This file is generated only in `--source mindware` mode and is mainly intended for validation or historical comparison.

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

Long-format import of MindWare's Power Band Stats sheet. This file is generated only in `--source mindware` mode and is mainly intended for validation or historical comparison.

Common metrics include:

- `LF Power`
- `LF Peak Power Frequency`
- `HF/RSA Power`
- `HF/RSA Peak Power Frequency`
- `LF/HF Ratio`

### `rsa_segment_metrics.csv`

HRV/RSA metrics computed from the IBI series used by the selected pathway.

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

In `raw` mode, this file is computed from automatically detected R peaks in the raw ECG trace. In `mindware` mode, it is computed from the IBI sheet exported by MindWare.

Use the raw-mode version as the main open pipeline output. Use the MindWare-mode version for comparison to manually processed exports.

### `rsa_segment_qc.csv`

Segment-level QC for the selected pathway.

Columns include:

- `segment`
- `max_percent_edited`
- `qc_pass`
- `qc_reason`

In `raw` mode, QC is based on raw peak count and implausible IBI percentage. In `mindware` mode, QC is based on available exported editing statistics, including the SOP rule to fail segments with more than 10% edited data.

### `raw_detected_peaks.csv`

Generated only when raw automatic peak detection is used. This file is central for reviewing the raw pipeline.

Columns include:

- `peak_index`
- `sample_index`
- `time_s`
- `ecg_value`
- `detector_value`

### `raw_detected_ibi.csv`

Generated only when raw automatic peak detection is used. This file is the raw-derived IBI series used for HRV/RSA and nonlinear feature extraction.

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

This file is generated in both `raw` and `mindware` modes. The raw-mode version is computed from raw-detected IBIs.

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

This file is generated in both `raw` and `mindware` modes. The raw-mode version is computed from raw-detected IBIs.

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
- MindWare HF/RSA power by segment when workbook comparison files are used
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
- Review `raw_detected_peaks.csv`, `raw_detected_ibi.csv`, and raw peak counts.
- Inspect unusually high LF/HF ratio segments.
- Inspect missing entropy values at larger MSE scales.
- Open `feature_plots.html` and look for abrupt segment outliers.
- When using workbook comparison mode, also review `max_percent_edited` and `% Normal Peaks` from the MindWare editing statistics.

The SOP also states that a segment should not be used if there are more than 3 consecutive midbeats. This rule cannot currently be fully automated from the HRV Analysis workbook alone because detailed consecutive-midbeat events are not exposed in the workbook.

## Analysis Recommendations

For analyses using the open raw pipeline:

1. Run `--source raw` to compute all features directly from `.mwi/.mwx` recordings.
2. Restrict analyses to pass-QC segments from `rsa_segment_qc.csv`.
3. Review `raw_detected_peaks.csv`, `raw_detected_ibi.csv`, and `feature_plots.html` for peak-detection quality.
4. Use `rsa_subject_features.csv` or `rsa_all_subject_features.csv` for downstream subject/session-level analyses.
5. If MindWare workbook exports are available, run `--source mindware` separately to validate raw-derived features against manually processed outputs.

Common subject/session-level features include:

- mean raw-derived HF/RSA power across pass-QC segments
- mean raw-derived RMSSD
- mean raw-derived SDNN
- mean raw-derived heart rate
- mean raw-derived LF/HF ratio
- valid segment count
- percent segments passing QC
- mean segment sample entropy
- full-recording multiscale entropy area under the curve

## Validation Notes

The raw automatic path decodes the observed MindWare Mobile `.mwi/.mwx` packet format and detects R peaks from the ECG channel using an automatic detector. This is the intended non-proprietary analysis path.

MindWare HRV Analysis Excel imports are retained as an optional validation pathway. They can help compare raw-derived results against manually corrected historical outputs, but they are not required to run the raw pipeline.

Before using raw-mode outputs as primary analysis variables in a study, validate the detector on a representative sample by comparing raw-derived peak counts, IBIs, and subject-level metrics with manually reviewed data.

## Troubleshooting

### No recordings found

Check that the input folder contains paired `.mwi/.mwx` files for raw mode, or HRV Analysis workbooks for MindWare comparison mode.

### Recording skipped

In raw mode, the recording likely does not have paired `.mwi/.mwx` files. In MindWare mode, the recording likely does not have an HRV Analysis workbook.

### Entropy values are blank

Blank entropy values usually mean the segment or coarse-grained series had too few valid template matches. This is common for short 30-second segments.

### Raw metrics do not match MindWare workbook metrics

Some differences are expected because the raw pathway uses automatic R-peak detection, while MindWare workbook outputs may reflect manual edits and proprietary processing choices. Use side-by-side comparisons to tune and validate the raw workflow.

## Current Limitations

- Raw `.mwx` signal decoding is implemented for the observed MindWare Mobile packet layout only and may need validation on additional devices/software versions.
- Consecutive-midbeat QC cannot yet be fully automated without detailed edit-event export or validated `.edh2` parsing.
- Segment-level entropy is statistically fragile because each segment has a small number of IBIs.
- Frequency-domain recomputation is not a validated clone of MindWare.
