from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class RecordingSet:
    stem: str
    root: Path
    mwi: Path | None = None
    mwx: Path | None = None
    edh2: Path | None = None
    hrv_xlsx: Path | None = None

    @property
    def is_raw_complete(self) -> bool:
        return self.mwi is not None and self.mwx is not None


def _base_stem(path: Path) -> str:
    name = path.name
    if "HRV Analysis" in name:
        return name.split("_HRV Analysis", 1)[0]
    return path.stem


def _recording_key(path: Path) -> str:
    stem = _base_stem(path)
    if re.match(r"^TAY\d+_CMH_\d+_\d+_SE\d+_RSA$", stem):
        return stem
    stem = re.sub(r"_\d+(?=_SE\d+_RSA$)", "", stem)
    return stem


def discover_recordings(root: str | Path) -> list[RecordingSet]:
    """Find MindWare raw files and generated HRV files under ``root``."""

    root = Path(root).expanduser().resolve()
    grouped: dict[str, dict[str, list[Path]]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".mwi", ".mwx", ".edh2", ".xlsx"}:
            continue
        if suffix == ".xlsx" and "HRV Analysis" not in path.name:
            continue
        stem = _recording_key(path)
        grouped.setdefault(stem, {}).setdefault(suffix.lstrip("."), []).append(path)

    out: list[RecordingSet] = []
    for stem, files in sorted(grouped.items()):
        max_count = max((len(paths) for paths in files.values()), default=0)
        if max_count <= 1:
            out.append(
                RecordingSet(
                    stem=stem,
                    root=root,
                    mwi=_first(files.get("mwi")),
                    mwx=_first(files.get("mwx")),
                    edh2=_first(files.get("edh2")),
                    hrv_xlsx=_first(files.get("xlsx")),
                )
            )
            continue

        contexts = sorted({path.parent for paths in files.values() for path in paths})
        for idx, context in enumerate(contexts, start=1):
            context_files = {
                suffix: _first(path for path in paths if path.parent == context)
                for suffix, paths in files.items()
            }
            duplicate_stem = f"{stem}__dup{idx:02d}"
            out.append(
                RecordingSet(
                    stem=duplicate_stem,
                    root=root,
                    mwi=context_files.get("mwi"),
                    mwx=context_files.get("mwx"),
                    edh2=context_files.get("edh2"),
                    hrv_xlsx=context_files.get("xlsx"),
                )
            )
    return out


def _first(paths: Iterable[Path] | None) -> Path | None:
    if paths is None:
        return None
    return next(iter(paths), None)


def require_files(recording: RecordingSet, names: Iterable[str]) -> None:
    missing = [name for name in names if getattr(recording, name) is None]
    if missing:
        raise FileNotFoundError(f"{recording.stem} is missing: {', '.join(missing)}")
