from datetime import datetime,timezone,timedelta
from pathlib import Path
from fantrax.live.provider_maturity import due,provider_plan,promote_if_valid

def test_preliminary_provider_is_recheckable_and_stable_is_skipped():
    old=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    assert due("PRELIMINARY",old,"whoscored")
    assert due("PRELIMINARY",old,"understat")
    assert not due("STABLE",old,"whoscored")
    assert not due("STABLE",old,"understat")

def test_failed_candidate_preserves_previous_and_no_change_is_detected():
    current=candidate=Path("fantrax/live/provider_maturity.py")
    assert promote_if_valid(current,candidate,valid=False)=="RETAINED_PREVIOUS"
    assert promote_if_valid(current,candidate,valid=True)=="NO_CHANGE"

def test_provider_plan_reports_missing_and_due():
    old=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat();got=provider_plan("whoscored",[{"maturity":"PRELIMINARY","retrieved_at":old}],10)
    assert got["missing"]==9 and got["due_for_recheck"]==1
