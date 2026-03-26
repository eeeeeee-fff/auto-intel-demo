from __future__ import annotations

from app.db import SessionLocal, init_db
from app.services.dashboard import build_today_digest, parse_digest_payload
from app.services.reporting import render_daily_report


def main() -> None:
    init_db()
    with SessionLocal() as session:
        digest = build_today_digest(session)
        report = render_daily_report(session)
        payload = parse_digest_payload(digest.summary_payload)
        print(
            {
                "digest_id": digest.id,
                "edition_date": payload.get("edition_date"),
                "window": payload.get("briefing_window", {}).get("label"),
                "major_event_count": payload.get("briefing_totals", {}).get("major_count", 0),
                "top_event_count": len(payload.get("top_events", [])),
                "report_id": report.id,
            }
        )


if __name__ == "__main__":
    main()
