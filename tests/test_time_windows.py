from datetime import datetime, timezone

from app.services.time_windows import briefing_window, current_briefing_edition_date


def test_current_briefing_edition_date_rolls_back_before_cutoff() -> None:
    before_cutoff = datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc)
    assert current_briefing_edition_date(before_cutoff).isoformat() == "2026-03-19"


def test_briefing_window_uses_previous_cutoff_to_current_cutoff() -> None:
    window = briefing_window(target_date=current_briefing_edition_date(datetime(2026, 3, 19, 22, 0, tzinfo=timezone.utc)))

    assert window.edition_date.isoformat() == "2026-03-20"
    assert window.start_local.strftime("%Y-%m-%d %H:%M") == "2026-03-19 05:00"
    assert window.end_local.strftime("%Y-%m-%d %H:%M") == "2026-03-20 05:00"
