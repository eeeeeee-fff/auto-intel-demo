from __future__ import annotations

import argparse

from app.db import SessionLocal, init_db
from app.services.dashboard import build_today_digest
from app.services.translation import translate_articles


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill translations for existing foreign-language articles.")
    parser.add_argument("--source-key", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        translated_count, per_source = translate_articles(
            session,
            source_key=args.source_key,
            limit=args.limit,
            force=args.force,
        )
        build_today_digest(session)
        print(
            {
                "translated_count": translated_count,
                "per_source": per_source,
                "source_key": args.source_key,
                "force": args.force,
            }
        )


if __name__ == "__main__":
    main()
