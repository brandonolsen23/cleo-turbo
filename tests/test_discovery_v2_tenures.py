import pytest
from cleo.discovery_v2.tenures import detect_tenures


def _evt(date, sid, stem):
    return {'sale_date': date, 'source_id': sid, 'side': 'seller', 'stem': stem}


def test_detect_tenures_single_dominant_stem_is_one_tenure():
    timeline = [
        _evt('2018-01-01', 'RT1', 'kingsett'),
        _evt('2019-06-01', 'RT2', 'kingsett'),
        _evt('2021-03-01', 'RT3', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 1
    t = tenures[0]
    assert t['dominant_stem'] == 'kingsett'
    assert t['start_date'] == '2018-01-01'
    assert t['end_date'] == '2021-03-01'
    assert t['n_party_sides'] == 3
    assert t['dominance_share'] == pytest.approx(1.0)


def test_detect_tenures_long_gap_splits_run():
    """A gap > MAX_TENURE_GAP_DAYS (730) splits."""
    timeline = [
        _evt('2010-01-01', 'A', 'kingsett'),
        _evt('2011-01-01', 'B', 'kingsett'),
        # 2-year+1-day gap — should split
        _evt('2013-01-02', 'C', 'kingsett'),
        _evt('2014-01-01', 'D', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 2
    assert tenures[0]['start_date'] == '2010-01-01'
    assert tenures[0]['end_date'] == '2011-01-01'
    assert tenures[1]['start_date'] == '2013-01-02'
    assert tenures[1]['end_date'] == '2014-01-01'


def test_detect_tenures_stem_change_with_grace_buffer():
    """3 off-stem events in a row don't split (grace=3); 4 do."""
    timeline = [
        _evt('2018-01-01', 'A', 'dh'),
        _evt('2018-06-01', 'B', 'dh'),
        _evt('2019-01-01', 'C', 'dh'),
        _evt('2019-06-01', 'D', 'dh'),
        _evt('2020-01-01', 'E', 'dh'),
        # Three off-stem events — within grace, don't split yet
        _evt('2020-03-01', 'F', 'midland'),
        _evt('2020-04-01', 'G', 'midland'),
        _evt('2020-05-01', 'H', 'midland'),
        # Fourth off-stem event — exceeds grace, split here
        _evt('2020-06-01', 'I', 'midland'),
        _evt('2020-07-01', 'J', 'midland'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 2
    assert tenures[0]['dominant_stem'] == 'dh'
    assert tenures[1]['dominant_stem'] == 'midland'
    # First tenure should end at the LAST on-stem event before the split,
    # not the start of the off-stem run.
    assert tenures[0]['end_date'] == '2020-01-01'
    assert tenures[1]['start_date'] == '2020-03-01'


def test_detect_tenures_unmapped_events_count_in_volume_but_not_dominance():
    """Unmapped (stem=None) events are part of the tenure's window but
    dilute its dominance share."""
    timeline = [
        _evt('2018-01-01', 'A', 'kingsett'),
        _evt('2018-06-01', 'B', 'kingsett'),
        _evt('2019-01-01', 'C', None),  # unmapped
        _evt('2019-06-01', 'D', 'kingsett'),
    ]
    tenures = detect_tenures(timeline)
    assert len(tenures) == 1
    t = tenures[0]
    assert t['dominant_stem'] == 'kingsett'
    assert t['n_party_sides'] == 4
    assert t['dominance_share'] == pytest.approx(0.75)


def test_detect_tenures_empty_timeline_returns_empty():
    assert detect_tenures([]) == []


def test_detect_tenures_all_unmapped_yields_no_tenures():
    """If we never see a mapped stem, there's no tenure to anchor on."""
    timeline = [_evt('2018-01-01', 'A', None), _evt('2019-01-01', 'B', None)]
    tenures = detect_tenures(timeline)
    assert tenures == []


def test_detect_tenures_open_tenure_when_recent():
    """A tenure with the latest event within RECENT_TENURE_DAYS of `now`
    emits end_date=None (ongoing)."""
    timeline = [
        _evt('2024-01-01', 'A', 'kingsett'),
        _evt('2025-01-01', 'B', 'kingsett'),
        _evt('2026-04-01', 'C', 'kingsett'),
    ]
    tenures = detect_tenures(timeline, now='2026-04-30')
    assert len(tenures) == 1
    assert tenures[0]['end_date'] is None  # ongoing


def test_detect_tenures_closed_tenure_when_dormant():
    """A tenure whose last event is older than RECENT_TENURE_DAYS gets a
    fixed end_date (the last event's date)."""
    timeline = [
        _evt('2018-01-01', 'A', 'kingsett'),
        _evt('2019-01-01', 'B', 'kingsett'),
    ]
    tenures = detect_tenures(timeline, now='2026-04-30')
    assert len(tenures) == 1
    assert tenures[0]['end_date'] == '2019-01-01'
