from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd


def write_feature_plots(
    out_dir: str | Path,
    metrics: pd.DataFrame,
    nonlinear: pd.DataFrame,
    mse: pd.DataFrame,
    mindware_power_stats: pd.DataFrame | None = None,
) -> Path:
    out_dir = Path(out_dir)
    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    sections = [
        ("Mean HR by segment", _line_svg(metrics, "segment", "mean_hr_bpm", "Mean HR", "bpm")),
        ("RMSSD by segment", _line_svg(metrics, "segment", "rmssd_ms", "RMSSD", "ms")),
        ("Recomputed HF/RSA power by segment", _line_svg(metrics, "segment", "hf_rsa_power", "HF/RSA", "power")),
        ("Sample entropy by segment", _line_svg(nonlinear, "segment", "sample_entropy_m2_r02", "SampEn", "entropy")),
        ("Multiscale entropy, full recording", _line_svg(mse, "scale", "sample_entropy_m2_r02", "MSE", "entropy")),
    ]

    if mindware_power_stats is not None and not mindware_power_stats.empty:
        hf = mindware_power_stats[mindware_power_stats["metric"].eq("HF/RSA Power")].copy()
        hf["value"] = pd.to_numeric(hf["value"], errors="coerce")
        sections.insert(3, ("MindWare HF/RSA power by segment", _line_svg(hf, "segment", "value", "MindWare HF/RSA", "power")))

    html = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>RSA Feature Plots</title>",
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;color:#1f2933}",
        "section{margin:0 0 32px} h1{font-size:24px} h2{font-size:17px;margin-bottom:8px}",
        "svg{max-width:900px;width:100%;height:auto;border:1px solid #d9e2ec;background:#fff}",
        ".note{color:#52606d;font-size:13px;max-width:820px}</style></head><body>",
        "<h1>RSA Feature Plots</h1>",
        "<p class='note'>Plots are generated from the exported IBI series and MindWare workbook values. Recomputed spectral and entropy metrics are audit features and should be interpreted alongside SOP-edited MindWare outputs.</p>",
    ]
    for title, svg in sections:
        html.append(f"<section><h2>{escape(title)}</h2>{svg}</section>")
    html.append("</body></html>")
    path = plot_dir / "feature_plots.html"
    path.write_text("\n".join(html), encoding="utf-8")
    return path


def _line_svg(df: pd.DataFrame, x_col: str, y_col: str, label: str, unit: str) -> str:
    rows = df[[x_col, y_col]].copy()
    rows[y_col] = pd.to_numeric(rows[y_col], errors="coerce")
    rows[x_col] = pd.to_numeric(rows[x_col], errors="coerce")
    rows = rows.dropna().sort_values(x_col)
    if rows.empty:
        return "<p class='note'>No finite values available.</p>"

    width, height = 760, 300
    left, right, top, bottom = 64, 24, 24, 48
    x_min, x_max = float(rows[x_col].min()), float(rows[x_col].max())
    y_min, y_max = float(rows[y_col].min()), float(rows[y_col].max())
    if x_min == x_max:
        x_min -= 1
        x_max += 1
    if y_min == y_max:
        y_min -= 1
        y_max += 1
    y_pad = (y_max - y_min) * 0.08
    y_min -= y_pad
    y_max += y_pad

    def sx(x: float) -> float:
        return left + ((x - x_min) / (x_max - x_min)) * (width - left - right)

    def sy(y: float) -> float:
        return top + (1 - ((y - y_min) / (y_max - y_min))) * (height - top - bottom)

    pts = [(sx(float(r[x_col])), sy(float(r[y_col]))) for _, r in rows.iterrows()]
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    circles = "\n".join(
        f"<circle cx='{x:.2f}' cy='{y:.2f}' r='4' fill='#0b7285'><title>{escape(label)}: {float(rows.iloc[i][y_col]):.4g} {escape(unit)}</title></circle>"
        for i, (x, y) in enumerate(pts)
    )
    y_ticks = _ticks(y_min, y_max, 5)
    x_ticks = rows[x_col].tolist()
    grid = []
    for y in y_ticks:
        yy = sy(y)
        grid.append(f"<line x1='{left}' y1='{yy:.2f}' x2='{width-right}' y2='{yy:.2f}' stroke='#edf2f7'/>")
        grid.append(f"<text x='{left-8}' y='{yy+4:.2f}' text-anchor='end' font-size='11' fill='#52606d'>{y:.3g}</text>")
    for x in x_ticks:
        xx = sx(float(x))
        grid.append(f"<text x='{xx:.2f}' y='{height-22}' text-anchor='middle' font-size='11' fill='#52606d'>{x:g}</text>")
    return (
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{escape(label)} plot'>"
        + "\n".join(grid)
        + f"<line x1='{left}' y1='{top}' x2='{left}' y2='{height-bottom}' stroke='#9fb3c8'/>"
        + f"<line x1='{left}' y1='{height-bottom}' x2='{width-right}' y2='{height-bottom}' stroke='#9fb3c8'/>"
        + f"<polyline points='{polyline}' fill='none' stroke='#0b7285' stroke-width='2.5'/>"
        + circles
        + f"<text x='{width/2}' y='{height-6}' text-anchor='middle' font-size='12' fill='#334e68'>{escape(x_col)}</text>"
        + f"<text x='18' y='{height/2}' transform='rotate(-90 18 {height/2})' text-anchor='middle' font-size='12' fill='#334e68'>{escape(label)} ({escape(unit)})</text>"
        + "</svg>"
    )


def _ticks(lo: float, hi: float, n: int) -> list[float]:
    if n <= 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]
