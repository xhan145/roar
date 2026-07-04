import milestones


def test_thresholds_ascending_and_named():
    ts = [t for t, _ in milestones.MILESTONES]
    assert ts == sorted(ts)
    assert ts[0] == 1000 and ts[-1] == 1_000_000
    assert milestones.name_for(50000) == "Local Legend"
    assert milestones.name_for(1234) is None


def test_progress_start():
    p = milestones.progress(0)
    assert p["unlocked"] == []
    assert p["next"] == {"threshold": 1000, "name": "First Roar"}
    assert p["words_remaining"] == 1000
    assert p["percent"] == 0
    assert p["total_words"] == 0


def test_progress_mid_band():
    p = milestones.progress(3000)   # past 1000, toward 5000
    assert [u["threshold"] for u in p["unlocked"]] == [1000]
    assert p["next"]["threshold"] == 5000
    assert p["words_remaining"] == 2000
    # from 1000 -> 5000, at 3000 => (3000-1000)/(5000-1000) = 50%
    assert p["percent"] == 50


def test_progress_exact_threshold_counts_as_unlocked():
    p = milestones.progress(5000)
    assert 5000 in [u["threshold"] for u in p["unlocked"]]
    assert p["next"]["threshold"] == 10000


def test_progress_maxed():
    p = milestones.progress(2_000_000)
    assert len(p["unlocked"]) == len(milestones.MILESTONES)
    assert p["next"] is None
    assert p["words_remaining"] == 0
    assert p["percent"] == 100


def test_progress_carries_unlock_timestamps():
    p = milestones.progress(6000, unlocks={1000: 111.0, 5000: 222.0})
    got = {u["threshold"]: u["unlocked_ts"] for u in p["unlocked"]}
    assert got == {1000: 111.0, 5000: 222.0}


def test_newly_crossed():
    assert milestones.newly_crossed(0, 999) == []
    assert milestones.newly_crossed(0, 1000) == [1000]
    assert milestones.newly_crossed(900, 6000) == [1000, 5000]
    assert milestones.newly_crossed(5000, 5001) == []       # 5000 already had
    assert milestones.newly_crossed(999_999, 3_000_000) == [1_000_000]


def test_progress_tolerates_bad_input():
    assert milestones.progress(-5)["total_words"] == 0
    assert milestones.progress("nope")["next"]["threshold"] == 1000
