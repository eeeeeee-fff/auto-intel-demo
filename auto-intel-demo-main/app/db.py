from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _ensure_sqlite_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "articles" not in table_names:
        return

    article_columns = {column["name"] for column in inspector.get_columns("articles")}
    statements: list[str] = []
    if "content_access" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN content_access VARCHAR(32) DEFAULT 'full_text'")
    if "translation_status" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN translation_status VARCHAR(32) DEFAULT 'not_requested'")
    if "translated_title_zh" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN translated_title_zh TEXT")
    if "translated_summary_zh" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN translated_summary_zh TEXT")
    if "translated_content_zh" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN translated_content_zh TEXT")
    if "translation_payload" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN translation_payload TEXT")
    if "translated_at" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN translated_at DATETIME")
    if "included_in_today_digest" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN included_in_today_digest BOOLEAN DEFAULT 0")
    if "digest_rank" not in article_columns:
        statements.append("ALTER TABLE articles ADD COLUMN digest_rank INTEGER")

    source_log_statements: list[str] = []
    if "source_run_logs" in table_names:
        source_log_columns = {column["name"] for column in inspector.get_columns("source_run_logs")}
        if "translated_count" not in source_log_columns:
            source_log_statements.append("ALTER TABLE source_run_logs ADD COLUMN translated_count INTEGER DEFAULT 0")

    digest_statements: list[str] = []
    if "today_digests" in table_names:
        digest_columns = {column["name"] for column in inspector.get_columns("today_digests")}
        if "window_start_at" not in digest_columns:
            digest_statements.append("ALTER TABLE today_digests ADD COLUMN window_start_at DATETIME")
        if "window_end_at" not in digest_columns:
            digest_statements.append("ALTER TABLE today_digests ADD COLUMN window_end_at DATETIME")

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        for statement in source_log_statements:
            connection.execute(text(statement))
        for statement in digest_statements:
            connection.execute(text(statement))
        connection.execute(text("UPDATE articles SET content_access = 'full_text' WHERE content_access IS NULL"))
        connection.execute(
            text(
                """
                UPDATE articles
                SET translation_status = CASE
                    WHEN language = 'zh' THEN 'not_needed'
                    ELSE 'not_requested'
                END
                WHERE translation_status IS NULL
                """
            )
        )
        connection.execute(
            text("UPDATE articles SET included_in_today_digest = 0 WHERE included_in_today_digest IS NULL")
        )
        connection.execute(
            text(
                """
                UPDATE articles
                SET is_major_event = CASE
                    WHEN event_importance IS NULL THEN is_major_event
                    WHEN event_importance >= 3 THEN 1
                    ELSE 0
                END
                """
            )
        )
        if "source_run_logs" in table_names:
            connection.execute(
                text("UPDATE source_run_logs SET translated_count = 0 WHERE translated_count IS NULL")
            )


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_schema()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
