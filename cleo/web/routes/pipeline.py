"""
Pipeline Inspector API — browse stages, inspect records, trace RT IDs, diff between stages.
All data is read live from disk (no indexing).
"""

import os
import re
import json
import glob
import time
import random
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from ...web.deps import get_current_user

router = APIRouter()

# ============================================================
# Path configuration
# ============================================================

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

STAGE_DIRS = {
    "assembled":    os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "assembled"),
    "classified":   os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "classified"),
    "addresses":    os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "addresses"),
    "parcel_links": os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "parcel_links"),
    "clean":        os.path.join(PROJECT_ROOT, "clean-data", "rt"),
}

STAGE_LABELS = {
    "assembled": "Assembled",
    "classified": "Classified",
    "addresses": "Addresses",
    "parcel_links": "Parcel Links",
    "clean": "Clean Records",
}

STAGE_ORDER = ["assembled", "classified", "addresses", "parcel_links", "clean"]

# Filename pattern: RT{ID}__{Region}__{Type}__p{Page}__pos{Position}.json
FILENAME_RE = re.compile(r'^(RT\d+)__([^_]+(?:_[^_]+)*)__([^_]+(?:-[^_]+)*)__p(\d+)__pos(\d+)\.json$')
RT_ID_RE = re.compile(r'^RT\d+$')

# ============================================================
# Cache
# ============================================================

_overview_cache: dict = {}
_file_list_cache: dict = {}


def _get_cached(cache: dict, key: str, ttl: int):
    entry = cache.get(key)
    if entry and time.time() - entry["ts"] < ttl:
        return entry["data"]
    return None


def _set_cached(cache: dict, key: str, data):
    cache[key] = {"data": data, "ts": time.time()}


# ============================================================
# Helpers
# ============================================================

def _parse_filename(filename: str) -> dict:
    """Parse metadata from a pipeline filename."""
    m = FILENAME_RE.match(filename)
    if m:
        return {
            "filename": filename,
            "rt_id": m.group(1),
            "region": m.group(2),
            "property_type": m.group(3),
            "page": f"p{m.group(4)}",
            "position": f"pos{m.group(5)}",
        }
    # Clean record: RT{ID}.json
    if filename.startswith("RT") and filename.endswith(".json"):
        return {
            "filename": filename,
            "rt_id": filename.replace(".json", ""),
            "region": None,
            "property_type": None,
            "page": None,
            "position": None,
        }
    return {"filename": filename, "rt_id": None}


def _validate_filename(filename: str):
    """Reject path traversal attempts."""
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid filename")


def _safe_path(stage_dir: str, filename: str) -> str:
    """Build and validate a file path."""
    _validate_filename(filename)
    full = os.path.join(stage_dir, filename)
    real = os.path.realpath(full)
    if not real.startswith(os.path.realpath(stage_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")
    return full


def _read_json(path: str) -> dict:
    """Read a JSON file, return its content."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=404, detail=f"File not found or invalid: {e}")


def _file_meta(path: str) -> dict:
    """Get file metadata."""
    try:
        st = os.stat(path)
        return {
            "file_size": st.st_size,
            "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        }
    except OSError:
        return {"file_size": 0, "modified_at": None}


def _list_json_files(stage_dir: str) -> list[str]:
    """List and sort JSON files in a directory (cached 30s)."""
    cached = _get_cached(_file_list_cache, stage_dir, 30)
    if cached is not None:
        return cached
    files = sorted(f for f in os.listdir(stage_dir) if f.endswith('.json'))
    _set_cached(_file_list_cache, stage_dir, files)
    return files


def _sample_files(stage_dir: str, files: list[str], n: int = 500) -> list[dict]:
    """Read a random sample of files and return their content."""
    sample = random.sample(files, min(n, len(files)))
    results = []
    for f in sample:
        try:
            with open(os.path.join(stage_dir, f), 'r') as fh:
                results.append(json.load(fh))
        except Exception:
            pass
    return results


def _compute_health(stage: str, stage_dir: str, files: list[str]) -> dict | None:
    """Compute health metrics by sampling records at a stage."""
    if not files:
        return None

    if stage == "assembled":
        sample = _sample_files(stage_dir, files, 500)
        verified = sum(1 for r in sample if r.get("join_verified") is True)
        return {
            "sample_size": len(sample),
            "metrics": {
                "join_verified": {
                    "true": verified,
                    "false": len(sample) - verified,
                    "rate": round(verified / len(sample), 3) if sample else 0,
                }
            }
        }

    if stage == "addresses":
        sample = _sample_files(stage_dir, files, 500)
        geocodable = 0
        total_addrs = 0
        for r in sample:
            prop = r.get("property", {})
            for addr in prop.get("addresses", []):
                total_addrs += 1
                if addr.get("geocodable"):
                    geocodable += 1
        return {
            "sample_size": len(sample),
            "metrics": {
                "geocodable": {
                    "true": geocodable,
                    "false": total_addrs - geocodable,
                    "rate": round(geocodable / total_addrs, 3) if total_addrs else 0,
                }
            }
        }

    if stage == "parcel_links":
        sample = _sample_files(stage_dir, files, 500)
        methods: dict[str, int] = {}
        for r in sample:
            m = r.get("method", "unknown")
            methods[m] = methods.get(m, 0) + 1
        resolved = sum(v for k, v in methods.items() if k not in ("unresolved", "error", "unknown"))
        return {
            "sample_size": len(sample),
            "metrics": {
                "method": methods,
                "resolved_rate": round(resolved / len(sample), 3) if sample else 0,
            }
        }

    return None


def _deep_diff(a, b, path="") -> list[dict]:
    """Recursive deep diff between two values."""
    changes = []
    if isinstance(a, dict) and isinstance(b, dict):
        all_keys = set(a.keys()) | set(b.keys())
        for key in sorted(all_keys):
            key_path = f"{path}.{key}" if path else key
            if key not in a:
                changes.append({"path": key_path, "type": "added", "value": b[key]})
            elif key not in b:
                changes.append({"path": key_path, "type": "removed", "value": a[key]})
            else:
                changes.extend(_deep_diff(a[key], b[key], key_path))
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            key_path = f"{path}[{i}]"
            if i >= len(a):
                changes.append({"path": key_path, "type": "added", "value": b[i]})
            elif i >= len(b):
                changes.append({"path": key_path, "type": "removed", "value": a[i]})
            else:
                changes.extend(_deep_diff(a[i], b[i], key_path))
    elif a != b:
        changes.append({"path": path or "(root)", "type": "changed", "old": a, "new": b})
    return changes


# ============================================================
# Endpoints
# ============================================================

@router.get("/overview")
def pipeline_overview(user=Depends(get_current_user)):
    """Dashboard with counts and health metrics per stage."""
    cached = _get_cached(_overview_cache, "overview", 60)
    if cached:
        return cached

    stages = []
    for name in STAGE_ORDER:
        stage_dir = STAGE_DIRS[name]
        files = _list_json_files(stage_dir)
        health = _compute_health(name, stage_dir, files)
        stages.append({
            "name": name,
            "label": STAGE_LABELS[name],
            "file_count": len(files),
            "health": health,
        })

    result = {
        "stages": stages,
        "cached_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _set_cached(_overview_cache, "overview", result)
    return result


@router.get("/stages/{stage}")
def browse_stage(
    stage: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: str = None,
    sort: str = "filename",
    order: str = "asc",
    user=Depends(get_current_user),
):
    """Browse records at a pipeline stage."""
    if stage not in STAGE_DIRS:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Valid: {', '.join(STAGE_ORDER)}")

    files = _list_json_files(STAGE_DIRS[stage])

    if order == "desc":
        files = list(reversed(files))

    if search:
        search_lower = search.lower()
        files = [f for f in files if search_lower in f.lower()]

    total = len(files)
    offset = (page - 1) * per_page
    page_files = files[offset:offset + per_page]

    results = [_parse_filename(f) for f in page_files]

    return {
        "stage": stage,
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/record/{stage}/{filename:path}")
def read_record(stage: str, filename: str, user=Depends(get_current_user)):
    """Read a single pipeline record's JSON."""
    if stage not in STAGE_DIRS:
        raise HTTPException(status_code=400, detail="Invalid stage")

    path = _safe_path(STAGE_DIRS[stage], filename)
    data = _read_json(path)
    meta = _file_meta(path)

    return {
        "stage": stage,
        "filename": filename,
        **meta,
        "data": data,
    }


@router.get("/trace/{rt_id}")
def trace_rt_id(rt_id: str, user=Depends(get_current_user)):
    """Full lifecycle trace for an RT ID across all stages."""
    if not RT_ID_RE.match(rt_id):
        raise HTTPException(status_code=400, detail="Invalid RT ID format. Expected RT followed by digits.")

    result: dict = {"rt_id": rt_id, "classifications": [], "stages": {}}

    # Clean record (direct lookup)
    clean_path = os.path.join(STAGE_DIRS["clean"], f"{rt_id}.json")
    if os.path.exists(clean_path):
        clean_data = _read_json(clean_path)
        result["stages"]["clean"] = {
            "filename": f"{rt_id}.json",
            "data": clean_data,
            **_file_meta(clean_path),
        }
    else:
        result["stages"]["clean"] = None

    # Flat stages (glob for RT ID)
    for stage in ["assembled", "classified", "addresses", "parcel_links"]:
        stage_dir = STAGE_DIRS[stage]
        pattern = os.path.join(stage_dir, f"{rt_id}__*.json")
        matches = sorted(glob.glob(pattern))

        entries = []
        for match_path in matches:
            fname = os.path.basename(match_path)
            data = _read_json(match_path)
            meta = _file_meta(match_path)
            entry = {"filename": fname, "data": data, **meta}
            entries.append(entry)

            # Build classifications from assembled stage
            if stage == "assembled":
                parsed = _parse_filename(fname)
                if parsed.get("region"):
                    # Extract position number from the assembled data or filename
                    pos_match = re.search(r'pos(\d+)', fname)
                    result["classifications"].append({
                        "source_folder": f"{parsed['region']}/{parsed['property_type']}/{parsed['page']}",
                        "position": int(pos_match.group(1)) if pos_match else 0,
                        "region": parsed["region"],
                        "property_type": parsed["property_type"],
                        "page": parsed["page"],
                    })

        result["stages"][stage] = entries

    # Extracted stage (different structure — use source_folder from classifications)
    extracted_entries = []
    extracted_base = os.path.join(PROJECT_ROOT, "engines", "rt", "pipeline", "extracted")
    for cls in result["classifications"]:
        source_dir = os.path.join(extracted_base, cls["source_folder"])
        if not os.path.isdir(source_dir):
            continue
        pos = cls["position"]
        files_found = {}
        for prefix in ["detail", "export", "results"]:
            fname = f"{prefix}_{pos:03d}.json"
            fpath = os.path.join(source_dir, fname)
            if os.path.exists(fpath):
                try:
                    files_found[prefix] = {
                        "filename": fname,
                        "data": _read_json(fpath),
                        **_file_meta(fpath),
                    }
                except Exception:
                    files_found[prefix] = {"filename": fname, "error": "Could not read"}
        if files_found:
            extracted_entries.append({
                "source_folder": cls["source_folder"],
                "position": pos,
                "files": files_found,
            })
    result["stages"]["extracted"] = extracted_entries

    # Raw stage (just report existence, don't read HTML)
    raw_base = os.path.join(PROJECT_ROOT, "raw-data", "rt", "pages")
    raw_entries = []
    for cls in result["classifications"]:
        source_dir = os.path.join(raw_base, cls["source_folder"])
        if not os.path.isdir(source_dir):
            continue
        pos = cls["position"]
        files_found = {}
        for fname in [f"detail_{pos:03d}.html", "results.html", "export.json"]:
            fpath = os.path.join(source_dir, fname)
            files_found[fname.split('.')[0]] = {
                "filename": fname,
                "exists": os.path.exists(fpath),
                **(_file_meta(fpath) if os.path.exists(fpath) else {}),
            }
        raw_entries.append({
            "source_folder": cls["source_folder"],
            "position": pos,
            "files": files_found,
        })
    result["stages"]["raw"] = raw_entries

    return result


@router.get("/raw-preview/{source_folder:path}/{position}")
def raw_preview(source_folder: str, position: int, user=Depends(get_current_user)):
    """Return a text snippet of the raw HTML detail file for display in the flow view."""
    _validate_filename(source_folder)
    raw_base = os.path.join(PROJECT_ROOT, "raw-data", "rt", "pages")
    detail_path = os.path.join(raw_base, source_folder, f"detail_{position:03d}.html")

    real = os.path.realpath(detail_path)
    if not real.startswith(os.path.realpath(raw_base)):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not os.path.exists(detail_path):
        raise HTTPException(status_code=404, detail="Raw HTML file not found")

    with open(detail_path, 'r', errors='replace') as f:
        content = f.read()

    return {
        "source_folder": source_folder,
        "position": position,
        "filename": f"detail_{position:03d}.html",
        "content": content,
        **_file_meta(detail_path),
    }


@router.get("/diff/{rt_id}")
def diff_stages(
    rt_id: str,
    stage_from: str = Query(...),
    stage_to: str = Query(...),
    filename: str = Query(None),
    user=Depends(get_current_user),
):
    """Compute a structured diff between two stages for an RT ID."""
    if not RT_ID_RE.match(rt_id):
        raise HTTPException(status_code=400, detail="Invalid RT ID")

    for s in [stage_from, stage_to]:
        if s not in STAGE_DIRS:
            raise HTTPException(status_code=400, detail=f"Invalid stage: {s}")

    def _load_record(stage: str) -> tuple[str, dict]:
        stage_dir = STAGE_DIRS[stage]
        if stage == "clean":
            fname = f"{rt_id}.json"
            path = os.path.join(stage_dir, fname)
        else:
            if filename:
                fname = filename
                path = _safe_path(stage_dir, fname)
            else:
                pattern = os.path.join(stage_dir, f"{rt_id}__*.json")
                matches = sorted(glob.glob(pattern))
                if not matches:
                    raise HTTPException(status_code=404, detail=f"No record found for {rt_id} at stage {stage}")
                path = matches[0]
                fname = os.path.basename(path)
        return fname, _read_json(path)

    fname_from, data_from = _load_record(stage_from)
    fname_to, data_to = _load_record(stage_to)

    changes = _deep_diff(data_from, data_to)
    added = sum(1 for c in changes if c["type"] == "added")
    removed = sum(1 for c in changes if c["type"] == "removed")
    changed = sum(1 for c in changes if c["type"] == "changed")

    return {
        "rt_id": rt_id,
        "stage_from": stage_from,
        "stage_to": stage_to,
        "filename_from": fname_from,
        "filename_to": fname_to,
        "changes": changes[:500],  # Cap to prevent massive responses
        "summary": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "total": added + removed + changed,
        },
        "from_data": data_from,
        "to_data": data_to,
    }
