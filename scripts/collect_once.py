from __future__ import annotations

import argparse

from app.db import SessionLocal, init_db
from app.services.dashboard import load_today_digest, parse_digest_payload
from app.services.ingestion import bootstrap_sources, run_collection_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one full collection pipeline.")
    parser.add_argument("--limit-per-source", type=int, default=None)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        bootstrap_sources(session)
        run = run_collection_pipeline(
            session,
            analyze=True,
            translate=True,
            build_digest=True,
            render_report=not args.no_report,
            limit_per_source=args.limit_per_source,
            trigger_mode="script:collect_once",
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
