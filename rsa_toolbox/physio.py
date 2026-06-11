from __future__ import annotations

from pathlib import Path


def write_physio_path_helper(out_path: str | Path, physio_root: str | Path) -> Path:
    """Write a small MATLAB helper that adds the referenced PhysIO toolbox.

    PhysIO is designed for physiological noise regressors in fMRI workflows.
    The SOP_OPS227 resting RSA workflow still needs MindWare R-peak editing or
    an equivalent ECG peak-detection implementation; this helper is included so
    future fMRI-linked RSA work can reuse the same PhysIO setup path.
    """

    out_path = Path(out_path)
    physio_root = Path(physio_root).expanduser()
    text = f"""function rsa_add_physio()\n% Add TAPAS PhysIO code used by the AFSP project.\nphysioRoot = '{physio_root.as_posix()}';\naddpath(genpath(fullfile(physioRoot, 'code')));\nif exist('tapas_physio_version', 'file')\n    fprintf('PhysIO version: %s\\n', tapas_physio_version());\nelse\n    warning('PhysIO code was not found on the MATLAB path.');\nend\nend\n"""
    out_path.write_text(text, encoding="utf-8")
    return out_path
