from __future__ import annotations

import argparse

from app.db import SessionLocal, init_db
from app.services.ingestion import bootstrap_sources, run_collection_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect one or more configured sources.")
    parser.add_argument("source_keys", nargs="+", help="Configured source keys, e.g. gasgoo marklines")
    parser.add_argument("--limit-per-source", type=int, default=None)
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        bootstrap_sources(session)
        run = run_collection_pipeline(
            session,
            source_keys=args.source_keys,
            analyze=True,
            translate=True,
            build_digest=False,
            render_report=False,
            limit_per_source=args.limit_per_source,
            trigger_mode="script:collect_source",
        )
        print(
            {
                "run_id": run.id,
                "source_keys": args.source_keys,
                "status": run.status,
                "collected_count": run.collected_count,
                "candidate_count": run.candidate_count,
                "analyzed_count": run.analyzed_count,
            }
        )


if __name__ == "__main__":
    main()
