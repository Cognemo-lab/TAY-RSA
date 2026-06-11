from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RSAConfig:
    """Analysis defaults taken from SOP_OPS227 and the example HRV workbook."""

    recording_duration_s: float = 240.0
    segment_duration_s: float = 30.0
    max_edited_percent: float = 10.0
    max_consecutive_midbeats: int = 3
    ibi_min_ms: float = 300.0
    ibi_max_ms: float = 2000.0
    resample_hz: float = 4.0
    lf_band_hz: tuple[float, float] = (0.04, 0.12)
    hf_rsa_band_hz: tuple[float, float] = (0.12, 0.40)
    entropy_m: int = 2
    entropy_r_ratio: float = 0.20
    mse_max_scale: int = 10

    @property
    def expected_segments(self) -> int:
        return int(round(self.recording_duration_s / self.segment_duration_s))
