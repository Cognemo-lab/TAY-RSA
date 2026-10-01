import unittest
from dataclasses import replace

import numpy as np

from rsa_toolbox.config import RSAConfig
from rsa_toolbox.hrv import _band_powers, _integrate_band


class SpectralIntegrationTests(unittest.TestCase):
    # Synthetic inputs keep these regression checks independent of participant
    # data. They cover spectral integration, not peak detection or QC decisions.
    def test_linear_psd_has_expected_integral(self):
        # Use a linear power spectral density (PSD) so the trapezoidal rule
        # should match the exact integral: integral(2*f + 1) = f**2 + f.
        freqs = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
        psd = 2 * freqs + 1
        # First use band edges on existing bins; then use edges between bins
        # to exercise interpolation. These cover both former np.trapz calls.
        for interpolate, band in [(False, (0.1, 0.4)), (True, (0.12, 0.38))]:
            with self.subTest(interpolate_edges=interpolate):
                low, high = band
                expected = (high**2 + high) - (low**2 + low)
                self.assertAlmostEqual(
                    _integrate_band(freqs, psd, band, interpolate), expected
                )

    def test_spectral_presets_produce_finite_positive_band_powers(self):
        # Construct 300 interbeat intervals (IBIs) around 800 ms. A nominal
        # 0.8-second beat spacing gives oscillations near 0.08 Hz (LF) and
        # 0.25 Hz (HF), providing nonzero power in both configured bands.
        beats = np.arange(300)
        ibi = 800 + 40 * np.sin(2 * np.pi * 0.08 * 0.8 * beats)
        ibi += 20 * np.sin(2 * np.pi * 0.25 * 0.8 * beats)
        default = RSAConfig()
        # Exercise the default and MindWare-harmonized spectral settings,
        # including their different windows, detrending, and edge handling.
        harmonized = replace(
            default,
            spectral_window="blackman",
            spectral_detrend="linear",
            spectral_interpolate_band_edges=True,
        )
        for config in (default, harmonized):
            with self.subTest(window=config.spectral_window):
                powers = _band_powers(ibi, config)
                # Check that the full spectral calculation completes and gives
                # usable powers and a ratio. This catches the NumPy API crash;
                # it does not establish agreement with manual MindWare results.
                for key in ("lf_power", "hf_rsa_power", "lf_hf_ratio"):
                    self.assertTrue(np.isfinite(powers[key]))
                    self.assertGreater(powers[key], 0)


if __name__ == "__main__":
    unittest.main()
