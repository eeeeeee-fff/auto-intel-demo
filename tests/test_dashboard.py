from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import ArticleORM
from app.services.dashboard import build_today_digest, parse_digest_payload
from app.services.reporting import query_articles


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def make_article(
    article_id: str,
    *,
    published_at: datetime,
    language: str = "zh",
    translation_status: str = "not_needed",
    translated_title_zh: str | None = None,
    is_major_event: bool = True,
    event_importance: int = 5,
) -> ArticleORM:
    return ArticleORM(
        id=article_id,
        source_key="gasgoo" if language == "zh" else "just_auto",
        source_name="盖世汽车" if language == "zh" else "Just Auto",
        url=f"https://example.com/{article_id}",
        title=f"title-{article_id}",
        published_at=published_at,
        fetched_at=published_at,
        language=language,
        content_text="content",
        summary_hint="summary",
        is_candidate=True,
        is_major_event=is_major_event,
        event_category="strategic_cooperation",
        event_importance=event_importance,
        content_access="full_text",
        translation_status=translation_status,
        translated_title_zh=translated_title_zh,
        translated_summary_zh="中文摘要" if translated_title_zh else None,
        translated_content_zh="中文正文" if translated_title_zh else None,
    )


def test_query_articles_filters_by_edition_window_and_language_scope() -> None:
    session = make_session()
    edition_date = date(2026, 3, 20)
    session.add_all(
        [
            make_article("a1", published_at=datetime(2026, 3, 18, 20, 30, tzinfo=timezone.utc), language="zh"),
            make_article(
                "a2",
                published_at=datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc),
                language="en",
                translation_status="done",
                translated_title_zh="中文标题",
            ),
            make_article("a3", published_at=datetime(2026, 3, 19, 21, 30, tzinfo=timezone.utc), language="zh"),
        ]
    )
    session.commit()

    articles = query_articles(
        session,
        target_date=edition_date,
        window_mode="edition",
        language_scope="foreign",
        limit=20,
    )

    assert [item.id for item in articles] == ["a2"]


def test_build_today_digest_excludes_untranslated_foreign_articles_and_adds_followup() -> None:
    session = make_session()
    edition_date = date(2026, 3, 20)
    session.add_all(
        [
            make_article("zh1", published_at=datetime(2026, 3, 19, 20, 30, tzinfo=timezone.utc), language="zh"),
            make_article(
                "en1",
                published_at=datetime(2026, 3, 19, 20, 0, tzinfo=timezone.utc),
                language="en",
                translation_status="done",
                translated_title_zh="外文中文标题",
            ),
            make_article(
                "en2",
                published_at=datetime(2026, 3, 19, 19, 30, tzinfo=timezone.utc),
                language="en",
                translation_status="not_requested",
            ),
            make_article(
                "old1",
                published_at=datetime(2026, 3, 18, 20, 0, tzinfo=timezone.utc),
                language="zh",
                event_importance=4,
            ),
        ]
    )
    session.commit()

    digest = build_today_digest(session, target_date=edition_date)
    payload = parse_digest_payload(digest.summary_payload)
    top_event_ids = [item["id"] for item in payload["top_events"]]
    followup_ids = [item["id"] for item in payload["followup_events"]]

    assert payload["edition_date"] == "2026-03-20"
    assert payload["briefing_window"]["start_label"].startswith("2026-03-19 05:00")
    assert "zh1" in top_event_ids
    assert "en1" in top_event_ids
    assert "en2" not in top_event_ids
    assert "old1" in followup_ids

    translated_article = session.get(ArticleORM, "en1")
    untranslated_article = session.get(ArticleORM, "en2")
    assert translated_article.included_in_today_digest is True
    assert untranslated_article.included_in_today_digest is False
    strategic = payload["strategic_judgement"]
    assert strategic["title"]
    assert strategic["summary"]
    assert strategic["business_relevance"] in {"高", "中", "低"}
    assert strategic["impact_direction"] in {"潜在利好", "潜在承压", "分化", "中性观察"}
    assert len(strategic["validation_focus"]) >= 1
    assert len(strategic["watchpoints"]) >= 1
