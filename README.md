# RSA Physiology Toolbox

Python toolbox for extracting Respiratory Sinus Arrhythmia (RSA), HRV, QC, and nonlinear IBI features from MindWare physiology recordings.

The recommended workflow starts from raw MindWare `.mwi/.mwx` files. The toolbox decodes the raw ECG signal, detects R peaks, derives and corrects IBIs, computes RSA/HRV features, generates QC reports, and optionally writes BIDS-derivative style outputs. MindWare HRV Analysis Excel files can also be imported when you need to compare against manually processed historical outputs.

## Quick Start

Clone the repository:

```bash
git clone git@github.com:Cognemo-lab/TAY-RSA.git
cd TAY-RSA
```

Create an environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install numpy pandas openpyxl
```

Run the default raw-data workflow:

```bash
python -m rsa_toolbox.cli /path/to/data --out /path/to/rsa_outputs
```

This is equivalent to:

```bash
python -m rsa_toolbox.cli /path/to/data --out /path/to/rsa_outputs --source raw
```

Add BIDS-derivative style outputs:

```bash
python -m rsa_toolbox.cli /path/to/data --out /path/to/rsa_outputs --source raw --bids
```

Or use the master runner for a full dataset:

```bash
python run_rsa_pipeline.py /path/to/data --out /path/to/rsa_outputs --mode raw --bids
```

## Input Data

For the raw workflow, each recording needs:

- `.mwi`: MindWare metadata/index file
- `.mwx`: raw MindWare signal file

Optional comparison files:

- `*HRV Analysis*.xlsx`: MindWare HRV Analysis workbook generated after manual signal processing/artifact correction
- `.edh2`: MindWare edit/history file, currently stored for traceability but not required by the automated raw workflow

The input folder can contain one recording or many recordings. The toolbox searches recursively and pairs files by recording stem.

Example:

```text
data/
  Raw/
    TAY01_CMH_00000001_01_SE01_RSA.mwi
    TAY01_CMH_00000001_01_SE01_RSA.mwx
  Analysis/
    TAY01_CMH_00000001_SE01_RSA_HRV Analysis.xlsx
    TAY01_CMH_00000001_SE01_RSA.edh2
```

## Processing Modes

The `--source` option controls how recordings are processed.

## Master Runner

For routine use across a full dataset, use `run_rsa_pipeline.py`. It wraps the toolbox CLI, searches recursively through all subjects, and writes a `run_manifest.txt` with the exact settings used.

Recommended raw-data run:

```bash
python run_rsa_pipeline.py ./data --out ./rsa_outputs/run_001 --mode raw --bids
```

If the dataset has both raw files and manual MindWare exports:

```bash
python run_rsa_pipeline.py ./data --out ./rsa_outputs/run_001 --mode both --bids
```

Use the MindWare-harmonized spectral estimator:

```bash
python run_rsa_pipeline.py ./data \
  --out ./rsa_outputs/run_harmonized \
  --mode raw \
  --bids \
  --spectral-preset mindware-harmonized
```

Expected input layout:

```text
data/
  Raw/
    <subject>/<visit>/<recording>.mwi
    <subject>/<visit>/<recording>.mwx
  Analysis/
    <subject>/<visit>/<recording>_HRV Analysis*.xlsx
```

Outputs:

```text
<out>/
  run_manifest.txt
  raw/
    rsa_all_subject_features.csv
    <recording_id>/
  manual/
    rsa_all_subject_features.csv
    <recording_id>/
```

The `manual/` folder is created only when `--mode manual` or `--mode both` is used.

### `--source raw`

Recommended default. Uses paired `.mwi/.mwx` files and does not require proprietary MindWare preprocessing outputs.

```bash
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw --source raw
```

This mode:

- decodes the ECG channel from raw MindWare files
- detects R peaks using an adaptive detector
- converts R peaks to IBI
- flags and corrects likely IBI artifacts
- computes HRV/RSA, nonlinear, and MSE features
- writes raw peak/IBI audit files
- writes QC summaries and plots

### `--source mindware`

Uses MindWare HRV Analysis Excel workbooks. Use this for validation or reproducing manually processed historical outputs.

```bash
python -m rsa_toolbox.cli ./data/Analysis --out ./rsa_outputs/mindware --source mindware
```

This mode:

- imports the MindWare IBI table
- imports MindWare HRV and power-band statistics
- applies available SOP-style editing QC from workbook fields
- recomputes toolbox metrics from the workbook IBI series

### `--source auto`

Convenience mode for mixed folders. The current implementation uses raw processing when only raw files are available, and uses workbook processing when a MindWare HRV workbook is available.

```bash
python -m rsa_toolbox.cli ./data --out ./rsa_outputs/auto --source auto
```

## What The Raw Pipeline Does

The raw pipeline is implemented in `rsa_toolbox/raw.py`, `rsa_toolbox/hrv.py`, and `rsa_toolbox/qc.py`.

1. **Read MindWare raw files**
   - Opens `.mwi` metadata as SQLite.
   - Reads `.mwx` packet payloads.
   - Finds the ECG channel.
   - Applies channel calibration.

2. **Detect R peaks**
   - Removes ECG baseline.
   - Smooths the ECG trace.
   - Computes a derivative-squared QRS energy envelope.
   - Uses adaptive thresholding with percentile and median absolute deviation criteria.
   - Uses a `0.32 s` refractory interval.
   - Refines peaks to local maxima.

3. **Create IBI series**
   - Converts consecutive R-peak times into IBI values.
   - Splits the recording into 30-second segments.
   - Stores the original interval as `raw_ibi_ms`.

4. **Correct IBI artifacts**
   - Flags IBIs outside the physiologic range:
     - `<300 ms`
     - `>2000 ms`
   - Flags local IBI outliers relative to neighboring intervals.
   - Interpolates corrected values when possible.
   - Stores the corrected interval as `ibi_ms`.
   - Preserves `artifact_flag`, `artifact_reason`, and `corrected` columns for auditability.

5. **Apply QC**
   - Checks raw peak count per segment.
   - Checks implausible raw IBI percentage.
   - Checks percentage of automatically corrected IBIs.
   - Uses a default maximum artifact/correction threshold of `10%` per segment.

6. **Compute features**
   - HRV/RSA metrics by segment.
   - Nonlinear IBI metrics by segment.
   - Full-recording multiscale entropy.
   - Subject/session summary features across pass-QC segments.

## Main Outputs

Each recording gets a folder:

```text
<output_folder>/<recording_id>/
```

The cohort-level summary is:

```text
<output_folder>/rsa_all_subject_features.csv
```

| File | Created in raw mode | Created in mindware mode | Purpose |
|---|---:|---:|---|
| `rsa_summary.txt` | yes | yes | Human-readable processing summary |
| `rsa_subject_features.csv` | yes | yes | One-row summary for one recording |
| `rsa_all_subject_features.csv` | yes | yes | One-row summary across all processed recordings |
| `rsa_segment_metrics.csv` | yes | yes | Segment-level HRV/RSA metrics computed by the toolbox |
| `rsa_segment_qc.csv` | yes | yes | Segment-level QC decisions |
| `rsa_nonlinear_features.csv` | yes | yes | Segment-level nonlinear IBI features |
| `rsa_multiscale_entropy.csv` | yes | yes | Full-recording multiscale entropy curve |
| `plots/feature_plots.html` | yes | yes | Browser-viewable plots |
| `mwi_metadata.json` | yes | yes, if `.mwi` exists | Acquisition metadata from `.mwi` |
| `raw_detected_peaks.csv` | yes | no | Automated R-peak detections |
| `raw_detected_ibi.csv` | yes | no | Raw and corrected beat-level IBI series |
| `mindware_hrv_stats_long.csv` | no | yes | Imported MindWare HRV Stats sheet |
| `mindware_power_band_stats_long.csv` | no | yes | Imported MindWare Power Band Stats sheet |

## How To Interpret Key Outputs

### `rsa_segment_qc.csv`

Use this first. It tells you which segments are usable.

Important columns in raw mode:

- `segment`: 30-second segment number
- `raw_peak_count`: number of detected R peaks in the segment
- `raw_ibi_count`: number of IBI values in the segment
- `raw_invalid_ibi_percent`: percentage of raw IBIs outside physiologic range
- `raw_artifact_corrected_percent`: percentage of IBIs flagged/corrected by the automated pipeline
- `qc_pass`: whether the segment passed QC
- `qc_reason`: reason a segment failed

Recommended interpretation:

- Prefer recordings with all or most segments passing QC.
- Review any segment with more than `10%` corrected or invalid IBIs.
- Treat failed segments as excluded from subject-level summaries.

### `raw_detected_peaks.csv`

Use this to audit peak detection.

Important columns:

- `peak_index`
- `sample_index`
- `time_s`
- `ecg_value`
- `detector_value`
- `qrs_energy`

Large jumps in detected peak timing, unusually low peak counts, or extreme detector values should trigger manual review.

### `raw_detected_ibi.csv`

Use this to audit artifact correction.

Important columns:

- `segment`
- `beat_index`
- `raw_ibi_ms`: original interval from detected R peaks
- `ibi_ms`: corrected interval used for analysis
- `artifact_flag`: whether the raw interval was flagged
- `artifact_reason`: why it was flagged
- `corrected`: whether an interpolated value was written

For transparent reporting, keep both `raw_ibi_ms` and `ibi_ms`. The toolbox computes HRV/RSA metrics from `ibi_ms`.

### `rsa_segment_metrics.csv`

Segment-level HRV/RSA metrics:

- `n_ibi`
- `mean_ibi_ms`
- `mean_hr_bpm`
- `sdnn_ms`
- `rmssd_ms`
- `lf_power`
- `hf_rsa_power`
- `lf_hf_ratio`
- `hf_peak_hz`
- `lf_power_uncalibrated`
- `hf_rsa_power_uncalibrated`
- `spectral_power_scale`

Recommended interpretation:

- `mean_hr_bpm` and `mean_ibi_ms` are generally the most stable automated outputs.
- `sdnn_ms` and `rmssd_ms` are sensitive to missed/extra beats, but improved artifact correction makes them much more reliable.
- Absolute `lf_power` and `hf_rsa_power` are most sensitive to PSD normalization, interpolation, windowing, and band-integration choices. When aligning the automated pipeline to a validated manual/MindWare reference, use `--spectral-power-scale` to apply a validation-derived multiplicative scale to LF and HF/RSA powers.
- `lf_power_uncalibrated` and `hf_rsa_power_uncalibrated` preserve the original toolbox PSD estimates for auditability.
- `lf_hf_ratio` is unchanged by multiplicative spectral scaling and is often more robust across PSD normalization conventions.
- If the goal is to harmonize the automated spectral estimator with MindWare-style outputs, use `--spectral-preset mindware-harmonized`. This preset uses Blackman windowing, linear detrending, and interpolated LF/HF band-edge integration. These settings improve spectral agreement by changing the shape of the PSD estimate rather than applying only a fixed calibration constant.

### `rsa_nonlinear_features.csv`

Segment-level nonlinear features:

- `cv_ibi`
- `poincare_sd1_ms`
- `poincare_sd2_ms`
- `sd1_sd2_ratio`
- `sample_entropy_m2_r02`

Segment-level entropy should be interpreted cautiously because 30-second windows often contain relatively few IBIs.

### `rsa_multiscale_entropy.csv`

Full-recording multiscale entropy:

- `scale`
- `n_points`
- `sample_entropy_m2_r02`

Defaults:

- embedding dimension: `m = 2`
- tolerance: `r = 0.2 * SD`
- scales: `1-10`

Blank values usually mean too few valid template matches were available at that scale.

### `rsa_subject_features.csv` and `rsa_all_subject_features.csv`

Use these for downstream statistics. These files aggregate pass-QC segments into one row per recording.

Common analysis variables:

- `computed_mean_hr_bpm_mean`
- `computed_mean_ibi_ms_mean`
- `computed_sdnn_ms_mean`
- `computed_rmssd_ms_mean`
- `computed_hf_rsa_power_mean`
- `computed_lf_hf_ratio_mean`
- `n_segments_pass_qc`
- `percent_segments_pass_qc`
- `subject_qc_pass`
- `nonlinear_sample_entropy_m2_r02_mean`
- `mse_auc_sum`
- `mse_mean_entropy`

Recommended interpretation:

- Use `subject_qc_pass` and `percent_segments_pass_qc` to filter or stratify analyses.
- For strict analyses, retain only recordings with all expected segments passing QC.
- For more permissive analyses, retain recordings with enough pass-QC segments and include valid segment count as a covariate or sensitivity check.

## BIDS-Derivative Style Export

Use `--bids` to write BIDS-style derivatives in addition to the standard toolbox outputs:

```bash
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw --source raw --bids
```

Default BIDS derivative location:

```text
<output_folder>/derivatives/rsa-toolbox/
```

Custom location:

```bash
python -m rsa_toolbox.cli ./data/Raw \
  --out ./rsa_outputs/raw \
  --source raw \
  --bids-out ./bids_derivatives/rsa-toolbox
```

Change the BIDS task label:

```bash
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw --source raw --bids --bids-task rest
```

The BIDS-style export includes:

```text
<bids_derivative_root>/
  dataset_description.json
  README
  participants.tsv
  participants.json
  sub-<label>/
    ses-<label>/
      physio/
        sub-<label>_ses-<label>_task-rest_run-<label>_recording-rsa_desc-rpeaks_events.tsv
        sub-<label>_ses-<label>_task-rest_run-<label>_recording-rsa_desc-preprocIbi_timeseries.tsv
        sub-<label>_ses-<label>_task-rest_run-<label>_recording-rsa_desc-segmentMetrics_timeseries.tsv
        sub-<label>_ses-<label>_task-rest_run-<label>_recording-rsa_desc-segmentQc_timeseries.tsv
        sub-<label>_ses-<label>_task-rest_run-<label>_recording-rsa_desc-nonlinear_timeseries.tsv
        sub-<label>_ses-<label>_task-rest_run-<label>_recording-rsa_desc-mse_timeseries.tsv
        sub-<label>_ses-<label>_task-rest_run-<label>_recording-rsa_desc-summary_features.tsv
```

Each TSV has a JSON sidecar documenting columns and pipeline settings.

Notes:

- These are BIDS-derivative style outputs, not raw BIDS physiology files.
- R peaks are written as `events.tsv` files with `onset`, `duration`, and `trial_type`.
- Corrected beat-level IBIs are written as derivative `timeseries.tsv` files.
- `dataset_description.json` includes `DatasetType: derivative` and `GeneratedBy` provenance.

## Comparing Automated Raw Outputs To Manual MindWare Outputs

To validate against manually processed data, run the two pathways separately:

```bash
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw --source raw
python -m rsa_toolbox.cli ./data/Analysis --out ./rsa_outputs/mindware --source mindware
```

Then compare subject/session outputs across:

- `rsa_outputs/raw/rsa_all_subject_features.csv`
- `rsa_outputs/mindware/rsa_all_subject_features.csv`

Only compare metrics that were actually present in the original manual/MindWare extraction:

- mean HR
- mean IBI
- SDNN
- RMSSD
- HF/RSA power
- LF/HF ratio

Do not treat entropy or MSE as original manual outputs. Entropy and MSE are additional toolbox-derived features that can be computed from either IBI source, but they were not part of the original manual MindWare assessment.

## Recommended Analysis Workflow

1. Run the raw pipeline:

```bash
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw --source raw --bids
```

2. Open each recording's `rsa_summary.txt` and `plots/feature_plots.html`.

3. Review `rsa_segment_qc.csv`.

4. Inspect `raw_detected_ibi.csv` for high artifact correction rates.

5. Use `rsa_all_subject_features.csv` for downstream analyses.

6. If manual MindWare outputs are available, run `--source mindware` and compare manual-assessed metrics.

7. Report:

- number of processed recordings
- number/percentage of pass-QC segments
- any excluded segments or recordings
- whether raw automated metrics were validated against manual outputs
- whether entropy/MSE were treated as automated-only features

## Troubleshooting

### No recordings found

Check that the input folder contains paired `.mwi/.mwx` files for raw mode, or `*HRV Analysis*.xlsx` files for MindWare mode.

### Recording skipped

In raw mode, the recording likely does not have both `.mwi` and `.mwx`. In MindWare mode, the recording likely does not have an HRV Analysis workbook.

### Many segments fail QC

Check:

- low `raw_peak_count`
- high `raw_invalid_ibi_percent`
- high `raw_artifact_corrected_percent`
- abrupt HR/RMSSD/HF power outliers in `feature_plots.html`

### Entropy values are blank

This usually means too few valid template matches were available. This is common for short segments or high MSE scales.

### Automated metrics do not match MindWare

Some differences are expected because:

- raw mode uses automated R-peak detection
- MindWare outputs may include manual edits
- spectral power depends on interpolation, detrending, windowing, and band definitions

Mean HR and mean IBI should usually agree most closely. HF/RSA power and LF/HF ratio are typically the most sensitive to processing differences.

## Current Limitations

- Raw `.mwx` decoding has been implemented for the observed MindWare Mobile packet layout and should be validated on any new acquisition setup.
- Consecutive-midbeat QC from SOP_OPS227 is not fully automated unless detailed edit-event information is available.
- Segment-level sample entropy is fragile because 30-second windows contain limited IBIs.
- Frequency-domain metrics are not guaranteed to be exact clones of MindWare's proprietary computations.
- `rsa_toolbox/physio.py` only provides a helper for adding TAPAS PhysIO to MATLAB's path; PhysIO is not used by the active Python RSA pipeline.

## Command Reference

```bash
python -m rsa_toolbox.cli ROOT [--out OUT] [--source raw|mindware|auto] [--bids] [--bids-out BIDS_OUT] [--bids-task TASK]
```

Common examples:

```bash
# Raw workflow
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw --source raw

# Raw workflow plus BIDS-style derivatives
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw --source raw --bids

# Raw workflow with validation-derived absolute spectral-power scaling
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw_scaled --source raw --spectral-power-scale 7.140679

# Raw workflow with MindWare-harmonized spectral estimator
python -m rsa_toolbox.cli ./data/Raw --out ./rsa_outputs/raw_harmonized --source raw --spectral-preset mindware-harmonized

# Manual MindWare workbook workflow
python -m rsa_toolbox.cli ./data/Analysis --out ./rsa_outputs/mindware --source mindware

# Mixed folder convenience workflow
python -m rsa_toolbox.cli ./data --out ./rsa_outputs/auto --source auto
```
