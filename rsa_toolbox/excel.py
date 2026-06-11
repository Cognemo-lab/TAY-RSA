from __future__ import annotations

from pathlib import Path

import pandas as pd


def _read_row_metric_sheet(path: Path, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    segment_numbers = raw.iloc[0, 1:].dropna().astype(int).tolist()
    rows = []
    for _, row in raw.iloc[1:].iterrows():
        metric = row.iloc[0]
        if pd.isna(metric):
            continue
        for idx, segment in enumerate(segment_numbers, start=1):
            rows.append(
                {
                    "segment": int(segment),
                    "metric": str(metric),
                    "value": row.iloc[idx] if idx < len(row) else None,
                }
            )
    return pd.DataFrame(rows)


def _read_ibi_sheet(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="IBI", header=None)
    segments = raw.iloc[0].dropna().astype(int).tolist()
    rows = []
    for col_idx, segment in enumerate(segments):
        for beat_idx, value in enumerate(raw.iloc[1:, col_idx].dropna(), start=1):
            rows.append({"segment": int(segment), "beat_index": beat_idx, "ibi_ms": float(value)})
    return pd.DataFrame(rows)


def read_settings(path: Path) -> dict[str, object]:
    raw = pd.read_excel(path, sheet_name="Settings", header=None)
    settings = {}
    for _, row in raw.iterrows():
        key = row.iloc[0]
        if pd.isna(key):
            continue
        settings[str(key)] = row.iloc[1] if len(row) > 1 else None
    return settings


def read_mindware_hrv_workbook(path: str | Path) -> dict[str, object]:
    """Read the HRV workbook produced by MindWare's Write All Segments step."""

    path = Path(path)
    return {
        "path": str(path),
        "settings": read_settings(path),
        "ibi": _read_ibi_sheet(path),
        "hrv_stats": _read_row_metric_sheet(path, "HRV Stats"),
        "power_band_stats": _read_row_metric_sheet(path, "Power Band Stats"),
        "editing_stats": _read_row_metric_sheet(path, "Editing Stats"),
    }
