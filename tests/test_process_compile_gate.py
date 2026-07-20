"""Tests for the incremental compile+rebuild gate in engines/rt/process.py.

The daily `--new` run must NOT trigger the full ~18-minute DB rebuild when
there is no genuinely new data, but MUST rebuild when new records arrive, when
forced, or when a prior (skipped/failed/locked) run left the DB flagged stale.
See docs/incremental-recompile-plan.md.
"""

import importlib.util
import json
import os

_PROC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'engines', 'rt', 'process.py',
)
_spec = importlib.util.spec_from_file_location('rt_process', _PROC_PATH)
rt_process = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt_process)


# --- _needs_compile decision --------------------------------------------------

def test_new_with_new_work_compiles():
    should, nw = rt_process._needs_compile(
        {'classify': 3, 'resolve': 2}, 'new', force_compile=False, dirty=False)
    assert should is True and nw == 5


def test_new_no_work_clean_skips():
    should, nw = rt_process._needs_compile(
        {'dedup': 0, 'classify': 0, 'normalize': 0, 'resolve': 0},
        'new', force_compile=False, dirty=False)
    assert should is False and nw == 0


def test_new_no_work_but_dirty_compiles():
    # Prior run left the DB stale (e.g. resolve was locked) — must still compile.
    should, nw = rt_process._needs_compile({}, 'new', force_compile=False, dirty=True)
    assert should is True and nw == 0


def test_force_compile_overrides_clean():
    should, _ = rt_process._needs_compile({}, 'new', force_compile=True, dirty=False)
    assert should is True


def test_full_mode_always_compiles():
    should, _ = rt_process._needs_compile({}, 'all', force_compile=False, dirty=False)
    assert should is True


def test_extract_count_is_not_new_work():
    # 'extract' counts already-known re-assembled pages and must NOT trigger a
    # rebuild on a day where nothing genuinely new came through.
    should, nw = rt_process._needs_compile(
        {'extract': 172, 'dedup': 0, 'classify': 0, 'normalize': 0, 'resolve': 0},
        'new', force_compile=False, dirty=False)
    assert nw == 0 and should is False


# --- dirty marker persistence -------------------------------------------------

def test_marker_roundtrip(tmp_path, monkeypatch):
    marker = tmp_path / 'pipeline-dirty.json'
    monkeypatch.setattr(rt_process, 'DIRTY_MARKER', str(marker))

    # Missing marker is treated as dirty so we never skip a needed compile.
    assert rt_process._read_dirty() is True

    rt_process._clear_dirty()
    assert rt_process._read_dirty() is False

    rt_process._set_dirty('2 new record-stage output(s)')
    assert rt_process._read_dirty() is True
    assert json.loads(marker.read_text())['reason'] == '2 new record-stage output(s)'

    rt_process._clear_dirty()
    assert rt_process._read_dirty() is False


def test_corrupt_marker_treated_as_dirty(tmp_path, monkeypatch):
    marker = tmp_path / 'pipeline-dirty.json'
    marker.write_text('{ not valid json')
    monkeypatch.setattr(rt_process, 'DIRTY_MARKER', str(marker))
    assert rt_process._read_dirty() is True
