from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import CollectedArticle
from app.collectors.sources import DEFAULT_SOURCE_CONFIGS, build_collector
from app.config import get_settings
from app.models import (
    ArticleORM,
    DailyReportORM,
    PipelineRunORM,
    RunStageLogORM,
    SourceConfigORM,
    SourceRunLogORM,
    utc_now,
)
from app.services.llm import DeepSeekClient
from app.services.rules import apply_rule_filter, importance_is_major
from app.services.translation import reset_translation_if_needed, translate_articles


def bootstrap_sources(session: Session) -> None:
    changed = False
    for source in DEFAULT_SOURCE_CONFIGS:
        existing = session.get(SourceConfigORM, source["key"])
        if existing is None:
            session.add(SourceConfigORM(**source))
            changed = True
            continue

        if existing.name != source["name"]:
            existing.name = source["name"]
            changed = True
        if existing.base_url != source["base_url"]:
            existing.base_url = source["base_url"]
            changed = True
        if existing.collector_kind != source["collector_kind"]:
            existing.collector_kind = source["collector_kind"]
            changed = True

    if changed:
        session.commit()


def list_enabled_sources(session: Session, source_keys: list[str] | None = None) -> list[SourceConfigORM]:
    statement = select(SourceConfigORM).where(SourceConfigORM.enabled.is_(True))
    if source_keys:
        statement = statement.where(SourceConfigORM.key.in_(source_keys))
    return list(session.scalars(statement.order_by(SourceConfigORM.key)))


def upsert_article(session: Session, item: CollectedArticle) -> tuple[ArticleORM, bool]:
    statement = select(ArticleORM).where(ArticleORM.source_key == item.source_key, ArticleORM.url == item.url)
    article = session.scalars(statement).first()
    content_changed = True
    if article is None:
        article = ArticleORM(source_key=item.source_key, source_name=item.source_name, url=item.url, title=item.title)
        session.add(article)
        session.flush()
    else:
        content_changed = any(
            [
                article.title != item.title,
                article.published_at != item.published_at,
                article.content_text != item.content_text,
                article.summary_hint != item.summary_hint,
                article.author != item.author,
                article.tags_json != json.dumps(item.tags, ensure_ascii=False),
                article.content_access != item.content_access,
            ]
        )
    article.source_name = item.source_name
    article.title = item.title
    article.published_at = item.published_at
    article.fetched_at = utc_now()
    article.language = item.language
    article.raw_html = item.raw_html
    article.content_text = item.content_text
    article.summary_hint = item.summary_hint
    article.author = item.author
    article.tags_json = json.dumps(item.tags, ensure_ascii=False)
    article.content_access = item.content_access
    reset_translation_if_needed(article, content_changed=content_changed)
    return article, content_changed


def apply_rule_decision(article: ArticleORM, *, reset_llm: bool = True) -> None:
    settings = get_settings()
    decision = apply_rule_filter(
        title=article.title,
        content_text=article.content_text or "",
        summary_hint=article.summary_hint or "",
        published_at=article.published_at,
        lookback_hours=settings.lookback_hours,
        source_key=article.source_key,
    )
    article.rule_category = decision.category
    article.is_candidate = decision.is_candidate
    article.filter_reason = decision.filter_reason

    if article.is_candidate and not reset_llm and article.llm_status == "done" and article.analysis_payload:
        article.is_major_event = importance_is_major(article.event_importance)
        if not article.core_summary:
            article.core_summary = decision.summary
        if not article.dedupe_key:
            article.dedupe_key = decision.dedupe_key
        return

    article.event_category = decision.category
    article.event_importance = decision.importance
    article.is_major_event = importance_is_major(article.event_importance)
    article.core_summary = decision.summary
    article.dedupe_key = decision.dedupe_key
    article.analysis_payload = None
    article.llm_status = "pending" if article.is_candidate else "fallback"


def analyze_articles(session: Session, article_ids: list[str] | None = None) -> int:
    statement = select(ArticleORM).where(ArticleORM.is_candidate.is_(True))
    if article_ids:
        statement = statement.where(ArticleORM.id.in_(article_ids))
    else:
        statement = statement.where(ArticleORM.llm_status != "done")

    articles = list(session.scalars(statement))
    client = DeepSeekClient()
    analyzed = 0
    for article in articles:
        if not client.enabled:
            if article.llm_status == "pending":
                article.llm_status = "fallback"
            analyzed += 1
            continue

        try:
            decision = client.analyze_article(
                title=article.title,
                source_key=article.source_key,
                source_name=article.source_name,
                url=article.url,
                published_at=article.published_at.isoformat() if article.published_at else None,
                content_text=article.content_text or "",
                summary_hint=article.summary_hint or "",
                content_access=article.content_access,
            )
            article.event_category = decision.category or article.rule_category
            article.event_importance = decision.importance
            article.is_major_event = importance_is_major(article.event_importance)
            article.core_summary = decision.core_summary or article.core_summary
            article.dedupe_key = decision.dedupe_key or article.dedupe_key
            article.analysis_payload = decision.raw_payload
            article.llm_status = "done"
        except Exception as exc:
            article.llm_status = f"error:{exc.__class__.__name__}"
        analyzed += 1

    session.commit()
    return analyzed


def _create_stage_log(session: Session, run_id: str, stage_name: str) -> RunStageLogORM:
    stage = RunStageLogORM(run_id=run_id, stage_name=stage_name, status="running")
    session.add(stage)
    session.commit()
    return stage


def _finish_stage_log(
    session: Session,
    stage: RunStageLogORM,
    *,
    status: str,
    processed_count: int = 0,
    error_message: str | None = None,
) -> None:
    stage.status = status
    stage.processed_count = processed_count
    stage.error_message = error_message
    stage.finished_at = utc_now()
    session.commit()


def run_collection_pipeline(
    session: Session,
    *,
    source_keys: list[str] | None = None,
    analyze: bool = True,
    translate: bool = True,
    build_digest: bool = False,
    render_report: bool = False,
    limit_per_source: int | None = None,
    trigger_mode: str = "manual",
) -> PipelineRunORM:
    bootstrap_sources(session)
    settings = get_settings()
    run = PipelineRunORM(trigger_mode=trigger_mode, status="running")
    session.add(run)
    session.commit()

    limit = limit_per_source or settings.collect_limit_per_source
    sources = list_enabled_sources(session, source_keys)
    run.source_count = len(sources)
    session.commit()

    collected_count = 0
    candidate_count = 0
    candidate_article_ids: list[str] = []
    translation_article_ids: list[str] = []
    analyze_targets_by_source: dict[str, list[str]] = defaultdict(list)
    translation_targets_by_source: dict[str, list[str]] = defaultdict(list)
    source_logs: dict[str, SourceRunLogORM] = {}

    collect_stage = _create_stage_log(session, run.id, "collect")

    try:
        for source in sources:
            source_started_at = utc_now()
            source_log = SourceRunLogORM(
                run_id=run.id,
                source_key=source.key,
                source_name=source.name,
                status="running",
                started_at=source_started_at,
            )
            session.add(source_log)
            session.commit()
            source_logs[source.key] = source_log

            source_candidate_count = 0
            source_collected_count = 0
            try:
                collector = build_collector(source.key)
                articles = collector.collect(limit=limit)
                source_collected_count = len(articles)
                for item in articles:
                    article, content_changed = upsert_article(session, item)
                    apply_rule_decision(article, reset_llm=content_changed)
                    collected_count += 1
                    if article.language != "zh" and (content_changed or article.translation_status != "done"):
                        if article.id is None:
                            session.flush()
                        translation_article_ids.append(article.id)
                        translation_targets_by_source[source.key].append(article.id)
                    if article.is_candidate:
                        if article.id is None:
                            session.flush()
                        candidate_count += 1
                        source_candidate_count += 1
                        if content_changed or article.llm_status != "done":
                            candidate_article_ids.append(article.id)
                            analyze_targets_by_source[source.key].append(article.id)

                source.last_status = "success"
                source.last_error = None
                source_log.status = "success"
            except Exception as exc:
                source.last_status = "failed"
                source.last_error = str(exc)
                source_log.status = "failed"
                source_log.error_message = str(exc)

            source.last_run_at = utc_now()
            source_log.collected_count = source_collected_count
            source_log.candidate_count = source_candidate_count
            source_log.analyzed_count = len(analyze_targets_by_source[source.key]) if analyze else 0
            source_log.translated_count = 0
            source_log.finished_at = utc_now()
            source_log.duration_ms = int((source_log.finished_at - source_started_at).total_seconds() * 1000)
            session.commit()

        _finish_stage_log(session, collect_stage, status="success", processed_count=collected_count)

        analyzed_count = 0
        candidate_article_ids = list(dict.fromkeys(candidate_article_ids))
        translation_article_ids = list(dict.fromkeys(translation_article_ids))

        if analyze:
            analyze_stage = _create_stage_log(session, run.id, "analyze")
            try:
                analyzed_count = analyze_articles(session, article_ids=candidate_article_ids) if candidate_article_ids else 0
            except Exception as exc:
                _finish_stage_log(
                    session,
                    analyze_stage,
                    status="failed",
                    processed_count=0,
                    error_message=str(exc),
                )
                raise
            _finish_stage_log(session, analyze_stage, status="success", processed_count=analyzed_count)
        run.analyzed_count = analyzed_count

        translated_count = 0
        if translate:
            translate_stage = _create_stage_log(session, run.id, "translate")
            try:
                translated_count, translated_by_source = translate_articles(session, article_ids=translation_article_ids)
                for source_key, count in translated_by_source.items():
                    source_log = source_logs.get(source_key)
                    if source_log is not None:
                        source_log.translated_count = count
                session.commit()
            except Exception as exc:
                _finish_stage_log(
                    session,
                    translate_stage,
                    status="failed",
                    processed_count=0,
                    error_message=str(exc),
                )
                raise
            _finish_stage_log(session, translate_stage, status="success", processed_count=translated_count)

        if build_digest:
            digest_stage = _create_stage_log(session, run.id, "build_digest")
            try:
                from app.services.dashboard import build_today_digest

                build_today_digest(session, run_id=run.id)
            except Exception as exc:
                _finish_stage_log(
                    session,
                    digest_stage,
                    status="failed",
                    processed_count=0,
                    error_message=str(exc),
                )
                raise
            _finish_stage_log(session, digest_stage, status="success", processed_count=1)

        if render_report:
            report_stage = _create_stage_log(session, run.id, "render_report")
            try:
                from app.services.reporting import render_daily_report

                report = render_daily_report(session)
                run.report_id = report.id
            except Exception as exc:
                _finish_stage_log(
                    session,
                    report_stage,
                    status="failed",
                    processed_count=0,
                    error_message=str(exc),
                )
                raise
            _finish_stage_log(session, report_stage, status="success", processed_count=1)

        run.status = "success"
        run.collected_count = collected_count
        run.candidate_count = candidate_count
        run.finished_at = utc_now()
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = utc_now()
        session.commit()
        raise

    session.commit()
    return run


def latest_report_for_date(session: Session, report_date) -> DailyReportORM | None:
    statement = select(DailyReportORM).where(DailyReportORM.report_date == report_date)
    return session.scalars(statement).first()
