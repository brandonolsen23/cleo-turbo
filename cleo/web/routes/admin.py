"""
Admin routes — server management and system configuration.
All endpoints require admin role.
"""

import json
import os
import subprocess
import shutil
import time
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from ..deps import get_db, require_admin
from ...analytics.groups import refresh_group_analytics

router = APIRouter()

# Project root (cleo-turbo/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REBUILD_SCRIPT = PROJECT_ROOT / "rebuild.py"
STATUS_FILE = PROJECT_ROOT / "data" / "rebuild-status.json"
PIPELINE_RUNNER = PROJECT_ROOT / "engines" / "rt" / "pipeline_runner.py"
PIPELINE_STATUS_FILE = PROJECT_ROOT / "data" / "pipeline-status.json"
PIPELINE_LOG_FILE = PROJECT_ROOT / "data" / "pipeline-runner.log"

# New orchestrator
RT_ENGINE_DIR = PROJECT_ROOT / "engines" / "rt"
PROCESS_SCRIPT = RT_ENGINE_DIR / "process.py"
PROCESS_LOG = RT_ENGINE_DIR / "pipeline" / "_processing_log.jsonl"
PROCESS_MARKER = RT_ENGINE_DIR / "pipeline" / "_reprocess.json"
PROCESS_RUN_LOG = PROJECT_ROOT / "data" / "process-run.log"
PROCESS_RUN_STATUS = PROJECT_ROOT / "data" / "process-run-status.json"


def _is_rebuild_running():
    """Check if a rebuild process is currently active."""
    if not STATUS_FILE.exists():
        return False
    try:
        with open(STATUS_FILE) as f:
            status = json.load(f)
        if not status.get("running"):
            return False
        # Check if the PID is still alive
        pid = status.get("pid")
        if pid:
            try:
                os.kill(pid, 0)  # Signal 0 = check existence
                return True
            except OSError:
                # Process is gone — mark as failed
                status["running"] = False
                status["phase"] = "error"
                status["error"] = "Rebuild process died unexpectedly"
                with open(STATUS_FILE, "w") as f:
                    json.dump(status, f)
                return False
        return False
    except Exception:
        return False


@router.post("/rebuild-db")
def rebuild_database(user=Depends(require_admin)):
    """
    Spawn the compiler as a background subprocess.
    Returns immediately — poll /api/admin/rebuild-status for progress.
    """
    if _is_rebuild_running():
        raise HTTPException(status_code=409, detail="A rebuild is already running")

    try:
        # Spawn rebuild.py as a fully detached subprocess
        proc = subprocess.Popen(
            ["python3", "-u", str(REBUILD_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            stdout=open(PROJECT_ROOT / "data" / "rebuild.log", "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,  # Detach from parent process group
        )
        return {
            "success": True,
            "message": "Rebuild started in background",
            "pid": proc.pid,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start rebuild: {e}")


@router.get("/rebuild-status")
def rebuild_status(user=Depends(require_admin)):
    """Poll the current rebuild status."""
    if not STATUS_FILE.exists():
        return {"running": False, "phase": "idle", "message": "No rebuild has been run"}

    try:
        with open(STATUS_FILE) as f:
            status = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"running": False, "phase": "unknown", "message": "Could not read status file"}

    # If status says running, verify the process is still alive
    if status.get("running") and status.get("pid"):
        try:
            os.kill(status["pid"], 0)
        except OSError:
            status["running"] = False
            status["phase"] = "error"
            status["message"] = "Rebuild process died unexpectedly"

    # Add table counts if rebuild is in progress (for live progress)
    if status.get("running"):
        try:
            from ...database.connection import get_connection
            conn = get_connection()
            counts = {}
            for table in ["groups", "contacts", "transactions", "properties", "pois", "gw_assessments"]:
                try:
                    counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except Exception:
                    counts[table] = 0
            conn.close()
            status["live_counts"] = counts
        except Exception:
            pass

    return status


@router.post("/clear-cache")
def clear_python_cache(user=Depends(require_admin)):
    """Delete all __pycache__ directories and .pyc files."""
    removed = []
    for dirpath, dirnames, filenames in os.walk(str(PROJECT_ROOT)):
        # Skip node_modules and .git
        if "node_modules" in dirpath or ".git" in dirpath:
            continue
        if "__pycache__" in dirnames:
            cache_dir = os.path.join(dirpath, "__pycache__")
            shutil.rmtree(cache_dir, ignore_errors=True)
            removed.append(os.path.relpath(cache_dir, str(PROJECT_ROOT)))
    return {
        "success": True,
        "removed_count": len(removed),
        "removed": removed[:20],  # Cap output
    }


@router.post("/restart-backend")
def restart_backend(user=Depends(require_admin)):
    """
    Trigger a backend restart by touching a Python file.
    Only works when uvicorn is running with --reload.
    """
    sentinel = PROJECT_ROOT / "cleo" / "web" / "_restart_sentinel.py"
    sentinel.write_text(f"# Auto-touched to trigger uvicorn reload at {time.time()}\n")
    return {
        "success": True,
        "message": "Touched sentinel file — uvicorn will reload if running with --reload",
    }


@router.get("/status")
def server_status(db=Depends(get_db), user=Depends(require_admin)):
    """Return basic server health info."""
    from ...database.connection import DB_PATH

    # DB file stats
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    db_modified = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0

    # Row counts for key tables
    counts = {}
    for table in ["properties", "transactions", "contacts", "groups", "deals", "lists"]:
        try:
            row = db.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            counts[table] = row["cnt"]
        except Exception:
            counts[table] = None

    return {
        "db_path": DB_PATH,
        "db_size_mb": round(db_size / (1024 * 1024), 1),
        "db_last_modified": db_modified,
        "table_counts": counts,
    }


# ============================================================
# Pipeline Runner
# ============================================================

@router.post("/run-pipeline")
def run_pipeline(stage: str = "all", admin=Depends(require_admin)):
    """Trigger the pipeline runner as a detached subprocess."""
    if not PIPELINE_RUNNER.exists():
        raise HTTPException(status_code=500, detail="Pipeline runner script not found")

    args = [str(PIPELINE_RUNNER), stage]
    log_fh = open(PIPELINE_LOG_FILE, "a")

    proc = subprocess.Popen(
        ["python3"] + args,
        cwd=str(PROJECT_ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    return {
        "status": "started",
        "stage": stage,
        "pid": proc.pid,
    }


@router.post("/refresh-analytics")
def refresh_analytics(db=Depends(get_db), admin=Depends(require_admin)):
    """Full refresh of group analytics for all groups."""
    start = time.time()
    count = refresh_group_analytics(db)
    elapsed = round(time.time() - start, 1)
    return {
        "success": True,
        "groups_refreshed": count,
        "elapsed_seconds": elapsed,
    }


@router.get("/pipeline-status")
def pipeline_status(admin=Depends(require_admin)):
    """Get current pipeline runner status."""
    if not PIPELINE_STATUS_FILE.exists():
        return {"status": "idle", "message": "No pipeline has been run"}

    try:
        with open(PIPELINE_STATUS_FILE) as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError):
        return {"status": "unknown", "message": "Status file unreadable"}


# ============================================================
# Pipeline Orchestrator (process.py)
# ============================================================

def _count_json_files(directory: Path) -> int:
    """Count .json files in a directory."""
    if not directory.is_dir():
        return 0
    return sum(1 for f in directory.iterdir() if f.suffix == '.json')


def _is_process_running() -> bool:
    """Check if a process.py run is currently active."""
    if not PROCESS_RUN_STATUS.exists():
        return False
    try:
        with open(PROCESS_RUN_STATUS) as f:
            status = json.load(f)
        if not status.get("running"):
            return False
        pid = status.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                # Process died — update status
                status["running"] = False
                status["phase"] = "finished"
                with open(PROCESS_RUN_STATUS, "w") as f:
                    json.dump(status, f)
                return False
        return False
    except Exception:
        return False


@router.get("/orchestrator/status")
def orchestrator_status(admin=Depends(require_admin)):
    """Get RT pipeline state: file counts per stage, pending work, recent log entries."""
    pipeline_dir = RT_ENGINE_DIR / "pipeline"
    assembled_dir = pipeline_dir / "assembled"
    classified_dir = pipeline_dir / "classified"
    addresses_dir = pipeline_dir / "addresses"
    parcel_links_dir = pipeline_dir / "parcel_links"
    clean_data_dir = PROJECT_ROOT / "clean-data" / "rt"
    lockfile = parcel_links_dir / ".resolve_v2.lock"

    assembled = _count_json_files(assembled_dir)
    classified = _count_json_files(classified_dir)
    addresses = _count_json_files(addresses_dir)
    parcel_links = _count_json_files(parcel_links_dir)
    clean_data = _count_json_files(clean_data_dir)

    # Check resolve lock
    resolve_locked = False
    resolve_pid = None
    if lockfile.is_file():
        try:
            with open(lockfile) as f:
                lock_info = json.load(f)
            pid = lock_info.get("pid")
            if pid:
                try:
                    os.kill(pid, 0)
                    resolve_locked = True
                    resolve_pid = pid
                except OSError:
                    pass
        except Exception:
            pass

    # Check reprocess marker
    reprocess = None
    if PROCESS_MARKER.is_file():
        try:
            with open(PROCESS_MARKER) as f:
                content = f.read().strip()
            if content and content != '{}':
                marker = json.loads(content)
                if marker.get("from_stage"):
                    reprocess = marker
        except Exception:
            pass

    # Read recent processing log (last 20 entries)
    log_entries = []
    if PROCESS_LOG.is_file():
        try:
            lines = PROCESS_LOG.read_text().strip().split('\n')
            for line in lines[-20:]:
                if line.strip():
                    try:
                        log_entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    # Check if a run is currently active
    running = _is_process_running()
    run_status = None
    if PROCESS_RUN_STATUS.is_file():
        try:
            with open(PROCESS_RUN_STATUS) as f:
                run_status = json.load(f)
        except Exception:
            pass

    return {
        "stages": {
            "assembled": assembled,
            "classified": classified,
            "normalized": addresses,
            "resolved": parcel_links,
            "clean_data": clean_data,
        },
        "pending": {
            "classify": max(0, assembled - classified),
            "normalize": max(0, classified - addresses),
            "resolve": max(0, addresses - parcel_links),
        },
        "resolve_locked": resolve_locked,
        "resolve_pid": resolve_pid,
        "reprocess": reprocess,
        "running": running,
        "run_status": run_status,
        "log": log_entries,
    }


@router.post("/orchestrator/run")
def orchestrator_run(
    mode: str = "new",
    skip_resolve: bool = False,
    admin=Depends(require_admin),
):
    """Start the pipeline orchestrator as a background process.

    Modes:
      - new: Process only new/missing records (daily use)
      - dry-run: Show what would be processed without doing it
      - from-classify: Reprocess everything from classify onward
      - from-normalize: Reprocess everything from normalize onward
    """
    if _is_process_running():
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    if not PROCESS_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="process.py not found")

    # Build command
    cmd = ["python3", "-u", str(PROCESS_SCRIPT)]

    if mode == "new":
        cmd.append("--new")
    elif mode == "dry-run":
        cmd.extend(["--new", "--dry-run"])
    elif mode == "from-classify":
        cmd.extend(["--from", "classify"])
    elif mode == "from-normalize":
        cmd.extend(["--from", "normalize"])
    elif mode == "full":
        cmd.append("--full")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    if skip_resolve and mode != "dry-run":
        cmd.extend(["--skip", "resolve"])

    # Write initial status
    run_info = {
        "running": True,
        "mode": mode,
        "skip_resolve": skip_resolve,
        "started_at": time.time(),
        "pid": None,
        "command": " ".join(cmd),
    }

    # Ensure data dir exists
    PROCESS_RUN_STATUS.parent.mkdir(parents=True, exist_ok=True)

    # Spawn as detached subprocess
    log_fh = open(PROCESS_RUN_LOG, "w")
    proc = subprocess.Popen(
        cmd,
        cwd=str(RT_ENGINE_DIR),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    run_info["pid"] = proc.pid
    with open(PROCESS_RUN_STATUS, "w") as f:
        json.dump(run_info, f)

    return {
        "success": True,
        "mode": mode,
        "pid": proc.pid,
        "message": f"Pipeline started in {mode} mode",
    }


@router.get("/orchestrator/log")
def orchestrator_log(lines: int = 50, admin=Depends(require_admin)):
    """Get the last N lines of the current/recent pipeline run output."""
    if not PROCESS_RUN_LOG.is_file():
        return {"lines": [], "message": "No run log found"}

    try:
        all_lines = PROCESS_RUN_LOG.read_text().strip().split('\n')
        return {"lines": all_lines[-lines:]}
    except Exception as e:
        return {"lines": [], "message": str(e)}
