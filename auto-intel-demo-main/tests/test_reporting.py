from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import ArticleORM
from app.services.reporting import (
    _dedupe_articles_for_report,
    _rebalance_report_articles,
    build_source_stats,
    load_major_articles,
    query_articles,
)


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def make_article(
    article_id: str,
    source_key: str,
    source_name: str,
    importance: int,
    *,
    content_access: str = "full_text",
    dedupe_key: str | None = None,
) -> ArticleORM:
    return ArticleORM(
        id=article_id,
        source_key=source_key,
        source_name=source_name,
        url=f"https://example.com/{article_id}",
        title=f"title-{article_id}",
        language="en",
        published_at=datetime(2026, 3, 18, 8, 0, tzinfo=timezone.utc),
        content_text="x" * 400,
        summary_hint="summary",
        is_candidate=True,
        is_major_event=True,
        event_importance=importance,
        content_access=content_access,
        dedupe_key=dedupe_key,
    )


def test_build_source_stats_counts_articles_candidates_and_majors() -> None:
    articles = [
        make_article("a1", "gasgoo", "盖世汽车", 5),
        make_article("a2", "gasgoo", "盖世汽车", 2),
        make_article("a3", "just_auto", "Just Auto", 4),
    ]
    articles[1].is_major_event = True

    stats = build_source_stats(articles)
    gasgoo = next(item for item in stats if item["source_key"] == "gasgoo")
    just_auto = next(item for item in stats if item["source_key"] == "just_auto")

    assert gasgoo["article_count"] == 2
    assert gasgoo["candidate_count"] == 2
    assert gasgoo["major_count"] == 1
    assert just_auto["major_count"] == 1


def test_report_prefers_full_text_over_index_only_in_same_bucket() -> None:
    index_only = make_article(
        "a1",
        "marklines",
        "MarkLines",
        5,
        content_access="index_only",
        dedupe_key="same-event",
    )
    full_text = make_article(
        "a2",
        "just_auto",
        "Just Auto",
        4,
        content_access="full_text",
        dedupe_key="same-event",
    )

    deduped = _dedupe_articles_for_report([index_only, full_text])
    assert len(deduped) == 1
    assert deduped[0].source_key == "just_auto"


def test_rebalance_report_articles_reserves_foreign_sources() -> None:
    articles = [
        make_article("a1", "gasgoo", "盖世汽车", 5),
        make_article("a2", "cnautonews", "中国汽车报", 5),
        make_article("a3", "just_auto", "Just Auto", 4),
        make_article("a4", "iea", "IEA", 4),
    ]

    balanced = _rebalance_report_articles(articles, max_items=4)
    first_sources = {item.source_key for item in balanced[:2]}

    assert "just_auto" in first_sources or "iea" in first_sources


def test_major_queries_follow_importance_threshold_even_if_flag_is_stale() -> None:
    session = make_session()
    major_by_importance = make_article("a1", "just_auto", "Just Auto", 3)
    major_by_importance.is_major_event = False
    non_major = make_article("a2", "gasgoo", "盖世汽车", 2)
    non_major.is_major_event = True
    session.add_all([major_by_importance, non_major])
    session.commit()

    queried = query_articles(
        session,
        window_start_at=datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc),
        window_end_at=datetime(2026, 3, 19, 0, 0, tzinfo=timezone.utc),
        major_only=True,
        limit=10,
    )
    loaded = load_major_articles(
        session,
        window_start_at=datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc),
        window_end_at=datetime(2026, 3, 19, 0, 0, tzinfo=timezone.utc),
    )

    assert [item.id for item in queried] == ["a1"]
    assert [item.id for item in loaded] == ["a1"]
