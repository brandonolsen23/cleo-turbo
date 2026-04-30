import pytest
from cleo.discovery_v2.tenures import detect_tenures


def _evt(date, sid, stem):
    return {'sale_date': date, 'source_id': sid, 'side': 'seller', 'stem': stem}


def test_single_stem_makes_one_tenure_min_to_max():
    timeline = [
        _evt('2018-01-01', 'A', 'kingsett'),
        _evt('2019-06-01', 'B', 'kingsett'),
        _evt('2021-03-01', 'C', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 1
    t = tenures[0]
    assert t['dominant_stem'] == 'kingsett'
    assert t['start_date'] == '2018-01-01'
    assert t['end_date'] == '2021-03-01'
    assert t['n_party_sides'] == 3
    assert t['dominance_share'] == pytest.approx(1.0)


def test_long_silence_does_not_split():
    """A 5-year quiet stretch with no contradicting evidence is still one tenure."""
    timeline = [
        _evt('2010-01-01', 'A', 'kingsett'),
        _evt('2010-06-01', 'B', 'kingsett'),
        # Silence 2011-2017 — no events at all
        _evt('2018-01-01', 'C', 'kingsett'),
        _evt('2024-01-01', 'D', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 1
    assert tenures[0]['start_date'] == '2010-01-01'
    assert tenures[0]['end_date'] == '2024-01-01'
    assert tenures[0]['n_party_sides'] == 4


def test_two_stems_at_one_anchor_emit_two_tenures():
    timeline = [
        _evt('2010-01-01', 'A', 'dh'),
        _evt('2012-01-01', 'B', 'dh'),
        _evt('2014-01-01', 'C', 'dh'),
        _evt('2018-01-01', 'D', 'midland'),
        _evt('2020-01-01', 'E', 'midland'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 2
    by_stem = {t['dominant_stem']: t for t in tenures}
    assert by_stem['dh']['start_date'] == '2010-01-01'
    assert by_stem['dh']['end_date'] == '2014-01-01'
    assert by_stem['dh']['n_party_sides'] == 3
    assert by_stem['midland']['start_date'] == '2018-01-01'
    assert by_stem['midland']['end_date'] == '2020-01-01'
    assert by_stem['midland']['n_party_sides'] == 2
    # Dominance: dh = 3/5 = 0.6, midland = 2/5 = 0.4
    assert by_stem['dh']['dominance_share'] == pytest.approx(0.6)
    assert by_stem['midland']['dominance_share'] == pytest.approx(0.4)


def test_interleaved_stems_still_emit_one_tenure_per_stem():
    """Even if events alternate, each stem gets its own MIN/MAX tenure."""
    timeline = [
        _evt('2018-01-01', 'A', 'dh'),
        _evt('2019-01-01', 'B', 'midland'),
        _evt('2020-01-01', 'C', 'dh'),
        _evt('2021-01-01', 'D', 'midland'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 2
    by_stem = {t['dominant_stem']: t for t in tenures}
    assert by_stem['dh']['start_date'] == '2018-01-01'
    assert by_stem['dh']['end_date'] == '2020-01-01'
    assert by_stem['midland']['start_date'] == '2019-01-01'
    assert by_stem['midland']['end_date'] == '2021-01-01'


def test_unmapped_events_dilute_dominance_but_dont_create_tenures():
    """An event with stem=None contributes to volume (denominator) but doesn't
    seed its own tenure."""
    timeline = [
        _evt('2018-01-01', 'A', 'kingsett'),
        _evt('2018-06-01', 'B', None),
        _evt('2019-01-01', 'C', 'kingsett'),
        _evt('2019-06-01', 'D', None),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 1
    t = tenures[0]
    assert t['dominant_stem'] == 'kingsett'
    assert t['n_party_sides'] == 2
    assert t['dominance_share'] == pytest.approx(0.5)


def test_empty_timeline_returns_empty():
    assert detect_tenures([]) == []


def test_all_unmapped_yields_no_tenures():
    timeline = [_evt('2018-01-01', 'A', None), _evt('2019-01-01', 'B', None)]
    assert detect_tenures(timeline) == []


def test_now_argument_is_ignored():
    """The old signature took `now` for "ongoing" detection. Now it's ignored."""
    timeline = [_evt('2018-01-01', 'A', 'kingsett')]
    tenures = detect_tenures(timeline, now='2026-04-30')
    assert len(tenures) == 1
    assert tenures[0]['end_date'] == '2018-01-01'  # NOT None — just the last observed date
