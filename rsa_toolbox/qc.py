from __future__ import annotations

import pandas as pd

from .config import RSAConfig


def apply_sop_qc(editing_stats: pd.DataFrame, config: RSAConfig | None = None) -> pd.DataFrame:
    """Apply SOP_OPS227 segment exclusion criteria available in workbook exports.

    The SOP excludes segments with more than 10% edited data or more than three
    consecutive midbeats. MindWare's workbook exposes edited percentages; a
    manual-edits table can be merged later for the consecutive-midbeat rule.
    """

    config = config or RSAConfig()
    wide = editing_stats.pivot_table(index="segment", columns="metric", values="value", aggfunc="first")
    wide = wide.reset_index()

    percent_cols = [c for c in wide.columns if "Percentage" in str(c) or "% Edited" in str(c)]
    if percent_cols:
        wide["max_percent_edited"] = wide[percent_cols].apply(pd.to_numeric, errors="coerce").max(axis=1)
    else:
        wide["max_percent_edited"] = 0.0

    wide["qc_pass"] = wide["max_percent_edited"].fillna(0) <= config.max_edited_percent
    wide["qc_reason"] = wide["qc_pass"].map({True: "", False: "more than 10% edited"})
    return wide[["segment", "max_percent_edited", "qc_pass", "qc_reason"]]
