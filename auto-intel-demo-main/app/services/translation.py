from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArticleORM, utc_now
from app.services.llm import DeepSeekClient


def _parse_tags_json(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def is_foreign_original(article: ArticleORM) -> bool:
    return article.language != "zh"


def article_display_title(article: ArticleORM) -> str:
    return (article.translated_title_zh or article.title or "").strip()


def article_display_summary(article: ArticleORM) -> str:
    return (
        article.translated_summary_zh
        or article.core_summary
        or article.summary_hint
        or ""
    ).strip()


def article_display_content(article: ArticleORM) -> str:
    return (article.translated_content_zh or article.content_text or "").strip()


def _reset_translation(article: ArticleORM) -> None:
    if article.language == "zh":
        article.translation_status = "not_needed"
    else:
        article.translation_status = "not_requested"
    article.translated_title_zh = None
    article.translated_summary_zh = None
    article.translated_content_zh = None
    article.translation_payload = None
    article.translated_at = None


def reset_translation_if_needed(article: ArticleORM, *, content_changed: bool) -> None:
    if not content_changed:
        if article.language == "zh" and not article.translation_status:
            article.translation_status = "not_needed"
        elif article.language != "zh" and not article.translation_status:
            article.translation_status = "not_requested"
        return
    _reset_translation(article)


def ensure_article_translation(session: Session, article: ArticleORM, *, force: bool = False) -> ArticleORM:
    if article.language == "zh":
        article.translation_status = "not_needed"
        session.commit()
        session.refresh(article)
        return article

    if not force and article.translation_status == "done" and article.translated_content_zh:
        return article

    client = DeepSeekClient()
    if not client.enabled:
        article.translation_status = "error:disabled"
        session.commit()
        raise RuntimeError("DeepSeek client is not configured")

    article.translation_status = "pending"
    session.commit()

    try:
        decision = client.translate_article(
            title=article.title,
            source_key=article.source_key,
            source_name=article.source_name,
            content_text=article.content_text or "",
            summary_hint=article.summary_hint or "",
            tags=_parse_tags_json(article.tags_json),
            content_access=article.content_access,
        )
        article.translated_title_zh = decision.translated_title_zh
        article.translated_summary_zh = decision.translated_summary_zh
        article.translated_content_zh = decision.translated_content_zh
        article.translation_payload = decision.raw_payload
        article.translated_at = utc_now()
        article.translation_status = "done"
    except Exception as exc:
        article.translation_status = f"error:{exc.__class__.__name__}"
        session.commit()
        raise

    session.commit()
    session.refresh(article)
    return article


def translate_articles(
    session: Session,
    article_ids: list[str] | None = None,
    *,
    force: bool = False,
    limit: int | None = None,
    source_key: str | None = None,
) -> tuple[int, dict[str, int]]:
    statement = select(ArticleORM).where(ArticleORM.language != "zh")
    if article_ids:
        statement = statement.where(ArticleORM.id.in_(article_ids))
    if source_key:
        statement = statement.where(ArticleORM.source_key == source_key)
    if not force:
        statement = statement.where(ArticleORM.translation_status != "done")
    statement = statement.order_by(ArticleORM.updated_at.desc())
    if limit is not None:
        statement = statement.limit(limit)

    articles = list(session.scalars(statement))
    if not articles:
        return 0, {}

    client = DeepSeekClient()
    if not client.enabled:
        for article in articles:
            article.translation_status = "error:disabled"
        session.commit()
        return 0, {}

    translated_count = 0
    per_source: dict[str, int] = defaultdict(int)
    for article in articles:
        try:
            ensure_article_translation(session, article, force=force)
        except RuntimeError:
            break
        except Exception:
            continue
        translated_count += 1
        per_source[article.source_key] += 1
    return translated_count, dict(per_source)


def parse_translation_payload(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
    if isinstance(parsed, dict):
        return parsed
    return {"raw": parsed}
