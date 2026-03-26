"""Reprocess stale articles: retry failed translations and re-analyze English summaries.

Usage:
    python -m scripts.reprocess_articles              # execute both groups
    python -m scripts.reprocess_articles --dry-run     # preview counts only
    python -m scripts.reprocess_articles --skip-translate  # only re-analyze
    python -m scripts.reprocess_articles --skip-analyze    # only retry translations
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import text

# Ensure project root is importable when run as `python -m scripts.reprocess_articles`
sys.path.insert(0, ".")

from app.db import engine  # noqa: E402


def _has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s))


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess stale articles")
    parser.add_argument("--dry-run", action="store_true", help="Preview counts without modifying data")
    parser.add_argument("--skip-translate", action="store_true", help="Skip retrying failed translations")
    parser.add_argument("--skip-analyze", action="store_true", help="Skip re-analyzing English summaries")
    args = parser.parse_args()

    with engine.begin() as conn:
        # Group A: failed translations -> reset to not_requested
        failed_rows = conn.execute(
            text("SELECT COUNT(*) FROM articles WHERE translation_status LIKE 'error:%'")
        ).scalar()

        # Group B: done analyses with English-only core_summary
        done_rows = conn.execute(
            text("SELECT id, core_summary FROM articles WHERE llm_status = 'done' AND core_summary IS NOT NULL")
        ).fetchall()
        english_ids = [row[0] for row in done_rows if row[1] and not _has_cjk(row[1])]

        print(f"Group A (failed translations): {failed_rows} articles")
        print(f"Group B (English core_summary): {len(english_ids)} articles")

        if args.dry_run:
            print("--dry-run: no changes made")
            return

        if not args.skip_translate and failed_rows:
            conn.execute(
                text("UPDATE articles SET translation_status = 'not_requested' WHERE translation_status LIKE 'error:%'")
            )
            print(f"  -> Reset {failed_rows} translation(s) to not_requested")

        if not args.skip_analyze and english_ids:
            placeholders = ",".join(f"'{aid}'" for aid in english_ids)
            conn.execute(
                text(f"UPDATE articles SET llm_status = 'pending' WHERE id IN ({placeholders})")
            )
            print(f"  -> Reset {len(english_ids)} article(s) to pending for re-analysis")

    print("Done.")


if __name__ == "__main__":
    main()
