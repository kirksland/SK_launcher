from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _split_asset_version(stem: str) -> Tuple[str, str, Optional[int]]:
    patterns = [
        re.compile(r"^(?P<base>.+?)[._-](?P<ver>v\d+)$", re.IGNORECASE),
        re.compile(r"^(?P<base>.+?)[._-](?P<ver>\d+)$", re.IGNORECASE),
        re.compile(r"^(?P<base>.+?)(?P<ver>v\d+)$", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.match(stem)
        if match:
            base = match.group("base")
            label = match.group("ver")
            digits = re.sub(r"\D", "", label)
            version_num = int(digits) if digits.isdigit() else None
            return base, label, version_num
    return stem, "current", None


def group_asset_versions(
    usd_files: List[Path],
    video_files: List[Path],
    image_files: Optional[List[Path]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    grouped: Dict[str, Dict[str, Dict[str, object]]] = {}

    def add_file(path: Path, kind: str) -> None:
        base, label, version_num = _split_asset_version(path.stem)
        base_map = grouped.setdefault(base, {})
        entry = base_map.get(label)
        if entry is None:
            entry = {
                "label": label,
                "usd": None,
                "video": None,
                "mtime": path.stat().st_mtime,
                "version_num": version_num,
            }
            base_map[label] = entry
        entry[kind] = path
        entry["mtime"] = max(float(entry["mtime"]), path.stat().st_mtime)
        if version_num is not None:
            entry["version_num"] = version_num

    for path in usd_files:
        add_file(path, "usd")
    for path in video_files:
        add_file(path, "video")
    for path in (image_files or []):
        add_file(path, "image")

    result: Dict[str, List[Dict[str, object]]] = {}
    for base, entries in grouped.items():
        entries_list = list(entries.values())

        def sort_key(entry: Dict[str, object]) -> Tuple[int, float]:
            version_num = entry.get("version_num")
            if isinstance(version_num, int):
                return (0, float(version_num))
            return (1, float(entry.get("mtime", 0.0)))

        entries_list.sort(key=sort_key, reverse=True)
        result[base] = entries_list

    return dict(sorted(result.items(), key=lambda kv: kv[0].lower()))
