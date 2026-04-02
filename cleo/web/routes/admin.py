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

router = APIRouter()

# Project root (cleo-turbo/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REBUILD_SCRIPT = PROJECT_ROOT / "rebuild.py"
STATUS_FILE = PROJECT_ROOT / "data" / "rebuild-status.json"
PIPELINE_RUNNER = PROJECT_ROOT / "engines" / "rt" / "pipeline_runner.py"
PIPELINE_STATUS_FILE = PROJECT_ROOT / "data" / "pipeline-status.json"
PIPELINE_LOG_FILE = PROJECT_ROOT / "data" / "pipeline-runner.log"


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
