from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rsa_toolbox.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main([str(ROOT), "--out", str(ROOT / "rsa_outputs")]))
