from __future__ import annotations

from app.db import SessionLocal, init_db
from app.services.dashboard import load_today_digest, parse_digest_payload
from app.services.ingestion import bootstrap_sources, run_collection_pipeline


def main() -> None:
    init_db()
    with SessionLocal() as session:
        bootstrap_sources(session)
        run = run_collection_pipeline(
            session,
            analyze=True,
            translate=True,
            build_digest=True,
            render_report=True,
            trigger_mode="script:demo_collect",
        )
        digest = load_today_digest(session)
        payload = parse_digest_payload(digest.summary_payload) if digest else {}
        print(
            {
                "run_id": run.id,
                "status": run.status,
                "collected_count": run.collected_count,
                "candidate_count": run.candidate_count,
                "analyzed_count": run.analyzed_count,
                "digest_id": digest.id if digest else None,
                "edition_date": payload.get("edition_date"),
                "window": payload.get("briefing_window", {}).get("label"),
                "top_event_count": len(payload.get("top_events", [])),
            }
        )


if __name__ == "__main__":
    main()
