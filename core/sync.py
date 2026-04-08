from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

Manifest = Dict[str, Tuple[float, int, Optional[str]]]


def load_manifest(path: Path) -> Optional[Manifest]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    manifest: Manifest = {}
    for k, v in data.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, list) or len(v) not in (2, 3):
            continue
        mtime, size = v[0], v[1]
        digest = v[2] if len(v) == 3 else None
        if isinstance(mtime, (int, float)) and isinstance(size, int):
            if digest is not None and not isinstance(digest, str):
                digest = None
            manifest[k] = (float(mtime), int(size), digest)
    return manifest


def build_manifest(
    root: Path,
    *,
    max_entries: int = 20000,
    time_budget: float = 0.6,
    exclude_dirs: Optional[Iterable[str]] = None,
    hash_max_bytes: int = 2_000_000,
    include_roots: Optional[Iterable[str]] = None,
    include_exts: Optional[Iterable[str]] = None,
) -> Manifest:
    exclude = {d.lower() for d in (exclude_dirs or [])}
    include = [r.strip("/\\") for r in (include_roots or []) if r.strip("/\\")]
    include_set = {r.lower() for r in include}
    include_exts_set = {e.lower() for e in (include_exts or [])}
    manifest: Manifest = {}
    start = time.time()
    count = 0
    if include:
        stack = [root / r for r in include]
    else:
        stack = [root]
    while stack:
        if count >= max_entries or (time.time() - start) > time_budget:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if count >= max_entries or (time.time() - start) > time_budget:
                        break
                    name_lower = entry.name.lower()
                    if entry.is_dir(follow_symlinks=False):
                        if name_lower in exclude:
                            continue
                        if current == root and include_set and name_lower not in include_set:
                            continue
                        stack.append(Path(entry.path))
                        continue
                    try:
                        stat = entry.stat()
                    except OSError:
                        continue
                    if include_exts_set:
                        ext = Path(entry.name).suffix.lower()
                        if ext and ext not in include_exts_set:
                            continue
                    rel = str(Path(entry.path).relative_to(root)).replace("\\", "/")
                    digest = None
                    if stat.st_size <= hash_max_bytes:
                        digest = _hash_file(Path(entry.path))
                    manifest[rel] = (float(stat.st_mtime), int(stat.st_size), digest)
                    count += 1
        except OSError:
            continue
    return manifest


def diff_manifests(
    local: Manifest,
    server: Manifest,
    baseline: Optional[Manifest] = None,
    *,
    mtime_epsilon: float = 0.5,
) -> Dict[str, list[str]]:
    to_push: list[str] = []
    to_pull: list[str] = []
    conflicts: list[str] = []
    keys = set(local.keys()) | set(server.keys())
    for key in sorted(keys):
        l = local.get(key)
        s = server.get(key)
        if l is None and s is not None:
            to_pull.append(key)
            continue
        if s is None and l is not None:
            to_push.append(key)
            continue
        if l is None or s is None:
            continue
        if baseline is not None:
            b = baseline.get(key)
            if b is not None:
                if _changed_since(l, b, mtime_epsilon) and _changed_since(s, b, mtime_epsilon):
                    conflicts.append(key)
                    continue
        if _newer(l, s, mtime_epsilon):
            to_push.append(key)
        elif _newer(s, l, mtime_epsilon):
            to_pull.append(key)
    return {
        "push": to_push,
        "pull": to_pull,
        "conflicts": conflicts,
    }


def manifest_path(root: Path) -> Path:
    return root / ".skyforge_sync" / "manifest.json"


def save_manifest(root: Path, manifest: Manifest) -> None:
    sync_dir = root / ".skyforge_sync"
    sync_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_path(root)
    serial: Dict[str, list] = {}
    for k, v in manifest.items():
        mtime, size, digest = v
        if digest:
            serial[k] = [mtime, size, digest]
        else:
            serial[k] = [mtime, size]
    path.write_text(json.dumps(serial, indent=2), encoding="utf-8")


def build_sync_plan(
    local_root: Path,
    server_root: Path,
    *,
    exclude_dirs: Optional[Iterable[str]] = None,
    include_roots: Optional[Iterable[str]] = None,
    include_exts: Optional[Iterable[str]] = None,
    time_budget: float = 0.5,
    max_entries: int = 20000,
) -> Dict[str, object]:
    local_manifest = build_manifest(
        local_root,
        exclude_dirs=exclude_dirs,
        include_roots=include_roots,
        include_exts=include_exts,
        time_budget=time_budget,
        max_entries=max_entries,
    )
    server_manifest = build_manifest(
        server_root,
        exclude_dirs=exclude_dirs,
        include_roots=include_roots,
        include_exts=include_exts,
        time_budget=time_budget,
        max_entries=max_entries,
    )
    baseline = load_manifest(manifest_path(local_root))
    diff = diff_manifests(local_manifest, server_manifest, baseline=baseline)
    return {
        "local_manifest": local_manifest,
        "server_manifest": server_manifest,
        "baseline": baseline,
        "diff": diff,
    }


def apply_sync_plan(
    local_root: Path,
    server_root: Path,
    diff: Dict[str, list[str]],
    *,
    mode: str,
) -> Dict[str, int]:
    ts = time.strftime("%Y%m%d_%H%M%S")
    local_backup = local_root / ".skyforge_sync" / "backups" / ts / "local"
    server_backup = server_root / ".skyforge_sync" / "backups" / ts / "server"
    conflict_root = local_root / ".skyforge_sync" / "conflicts" / ts
    counts = {"pushed": 0, "pulled": 0, "conflicts": 0, "skipped": 0}

    conflicts = diff.get("conflicts", [])
    if conflicts:
        for rel in conflicts:
            _copy_conflict(local_root, server_root, rel, conflict_root)
            counts["conflicts"] += 1

    if mode in ("push", "sync"):
        for rel in diff.get("push", []):
            if rel in conflicts:
                counts["skipped"] += 1
                continue
            if _copy_with_backup(local_root, server_root, rel, server_backup):
                counts["pushed"] += 1

    if mode in ("pull", "sync"):
        for rel in diff.get("pull", []):
            if rel in conflicts:
                counts["skipped"] += 1
                continue
            if _copy_with_backup(server_root, local_root, rel, local_backup):
                counts["pulled"] += 1

    return counts


def _copy_with_backup(src_root: Path, dst_root: Path, rel: str, backup_root: Path) -> bool:
    src = src_root / rel
    dst = dst_root / rel
    if not src.exists() or not src.is_file():
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            backup = backup_root / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            try:
                import shutil
                shutil.copy2(dst, backup)
            except Exception:
                pass
        import shutil
        shutil.copy2(src, dst)
        return True
    except Exception:
        return False


def _copy_conflict(local_root: Path, server_root: Path, rel: str, conflict_root: Path) -> None:
    local_src = local_root / rel
    server_src = server_root / rel
    try:
        if local_src.exists() and local_src.is_file():
            dst = conflict_root / "local" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(local_src, dst)
        if server_src.exists() and server_src.is_file():
            dst = conflict_root / "server" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(server_src, dst)
    except Exception:
        pass


def _hash_file(path: Path) -> Optional[str]:
    try:
        import hashlib
        h = hashlib.sha1()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 128), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _changed_since(current: Tuple[float, int, Optional[str]], base: Tuple[float, int, Optional[str]], eps: float) -> bool:
    c_m, c_s, c_h = current
    b_m, b_s, b_h = base
    if c_s != b_s:
        return True
    if c_h and b_h and c_h != b_h:
        return True
    return c_m > b_m + eps


def _newer(a: Tuple[float, int, Optional[str]], b: Tuple[float, int, Optional[str]], eps: float) -> bool:
    a_m, a_s, a_h = a
    b_m, b_s, b_h = b
    if a_s != b_s:
        return a_m > b_m + eps
    if a_h and b_h and a_h != b_h:
        return True if a_m >= b_m - eps else False
    return a_m > b_m + eps
