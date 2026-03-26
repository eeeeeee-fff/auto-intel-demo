from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ArticleORM, DailyReportORM, PipelineRunORM, SourceConfigORM
from app.schemas import (
    AnalyzeRequest,
    ArticleDetailRead,
    ArticleRead,
    ArticleTranslationRead,
    CollectRequest,
    DailyReportRead,
    DashboardTodayRead,
    GenerateReportRequest,
    PipelineRunDetailRead,
    PipelineRunRead,
    SourceConfigRead,
    SourceConfigUpdate,
    SourceRunLogRead,
    SourceStatusRead,
)
from app.services.dashboard import get_dashboard_today, render_dashboard_context, render_ops_context
from app.services.ingestion import analyze_articles, bootstrap_sources, run_collection_pipeline
from app.services.reporting import (
    CATEGORY_LABELS,
    CONTENT_ACCESS_LABELS,
    get_latest_report_article_ids,
    load_runs,
    load_source_run_logs,
    load_source_runs,
    load_stage_logs,
    parse_analysis_payload,
    parse_tags_json,
    query_articles,
    render_daily_report,
    render_intel_context,
    templates,
)
from app.services.rules import article_is_major
from app.services.time_windows import current_briefing_edition_date, shanghai_today
from app.services.translation import (
    article_display_content,
    article_display_summary,
    article_display_title,
    ensure_article_translation,
    is_foreign_original,
    parse_translation_payload,
)


router = APIRouter()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid date format, expected YYYY-MM-DD") from exc


def _article_read_payload(article: ArticleORM) -> dict:
    return {
        "id": article.id,
        "source_key": article.source_key,
        "source_name": article.source_name,
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at,
        "is_candidate": article.is_candidate,
        "is_major_event": article_is_major(article),
        "event_category": article.event_category,
        "event_importance": article.event_importance,
        "core_summary": article.core_summary,
        "filter_reason": article.filter_reason,
        "content_access": article.content_access,
        "llm_status": article.llm_status,
        "translation_status": article.translation_status,
        "display_title": article_display_title(article),
        "display_summary": article_display_summary(article),
        "original_language": article.language,
        "is_foreign_original": is_foreign_original(article),
        "included_in_today_digest": article.included_in_today_digest,
    }


def _article_detail_payload(db: Session, article: ArticleORM) -> dict:
    latest_report = db.scalars(select(DailyReportORM).order_by(DailyReportORM.generated_at.desc()).limit(1)).first()
    latest_report_article_ids = get_latest_report_article_ids(db, latest_report)
    translation_payload = parse_translation_payload(article.translation_payload)
    payload = _article_read_payload(article)
    payload.update(
        {
            "summary_hint": article.summary_hint,
            "content_text": article.content_text,
            "author": article.author,
            "tags": parse_tags_json(article.tags_json),
            "rule_category": article.rule_category,
            "dedupe_key": article.dedupe_key,
            "analysis_payload": parse_analysis_payload(article.analysis_payload),
            "translated_title_zh": article.translated_title_zh,
            "translated_summary_zh": article.translated_summary_zh,
            "translated_content_zh": article.translated_content_zh,
            "translated_at": article.translated_at,
            "preserved_terms": translation_payload.get("preserved_terms", []),
            "original_title": article.title,
            "original_summary": article.summary_hint or article.core_summary,
            "original_content": article.content_text,
            "display_content": article_display_content(article),
            "included_in_latest_report": article.id in latest_report_article_ids,
        }
    )
    return payload


@router.get("/health")
def health() -> dict:
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}


@router.get("/v1/sources", response_model=list[SourceConfigRead])
def list_sources(db: Session = Depends(get_db)) -> list[SourceConfigORM]:
    bootstrap_sources(db)
    return list(db.scalars(select(SourceConfigORM).order_by(SourceConfigORM.key)))


@router.get("/v1/sources/status", response_model=list[SourceStatusRead])
def list_source_status(db: Session = Depends(get_db)) -> list[dict]:
    from app.services.dashboard import build_source_status

    bootstrap_sources(db)
    return build_source_status(db)


@router.get("/v1/sources/{source_key}/runs", response_model=list[SourceRunLogRead])
def list_source_runs(source_key: str, db: Session = Depends(get_db)) -> list:
    return load_source_runs(db, source_key, limit=20)


@router.patch("/v1/sources/{source_key}", response_model=SourceConfigRead)
def update_source(source_key: str, payload: SourceConfigUpdate, db: Session = Depends(get_db)) -> SourceConfigORM:
    source = db.get(SourceConfigORM, source_key)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    if payload.enabled is not None:
        source.enabled = payload.enabled
    if payload.schedule_minutes is not None:
        source.schedule_minutes = payload.schedule_minutes
    db.commit()
    db.refresh(source)
    return source


@router.get("/v1/dashboard/today", response_model=DashboardTodayRead)
def dashboard_today(target_date: str | None = None, db: Session = Depends(get_db)) -> dict:
    return get_dashboard_today(db, _parse_date(target_date))


@router.post("/v1/pipeline/collect", response_model=PipelineRunRead)
def collect(payload: CollectRequest, db: Session = Depends(get_db)) -> PipelineRunORM:
    run = run_collection_pipeline(
        db,
        source_keys=payload.source_keys,
        analyze=payload.analyze,
        translate=payload.translate,
        build_digest=payload.build_digest,
        render_report=payload.render_report,
        limit_per_source=payload.limit_per_source,
        trigger_mode=payload.trigger_mode,
    )
    return run


@router.post("/v1/pipeline/analyze")
def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db)) -> dict:
    analyzed_count = analyze_articles(db, article_ids=payload.article_ids)
    return {"analyzed_count": analyzed_count}


@router.get("/v1/articles", response_model=list[ArticleRead])
def list_articles(
    date: str | None = None,
    window_mode: str = Query(default="edition", pattern="^(edition|calendar)$"),
    source_key: str | None = None,
    candidate_only: bool = False,
    major_only: bool = False,
    category: str | None = None,
    content_access: str | None = None,
    language_scope: str = Query(default="all", pattern="^(all|domestic|foreign)$"),
    limit: int = Query(default=120, ge=1, le=300),
    offset: int = Query(default=0, ge=0, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    if date:
        target_date = _parse_date(date)
    else:
        target_date = current_briefing_edition_date() if window_mode == "edition" else shanghai_today()
    articles = query_articles(
        db,
        target_date=target_date,
        window_mode=window_mode,
        source_key=source_key,
        candidate_only=candidate_only,
        major_only=major_only,
        category=category,
        content_access=content_access,
        language_scope=language_scope,
        limit=limit,
        offset=offset,
    )
    return [_article_read_payload(item) for item in articles]


@router.get("/v1/articles/{article_id}", response_model=ArticleDetailRead)
def get_article(article_id: str, db: Session = Depends(get_db)) -> dict:
    article = db.get(ArticleORM, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")
    return _article_detail_payload(db, article)


@router.post("/v1/articles/{article_id}/translate", response_model=ArticleTranslationRead)
def translate_article(article_id: str, force: bool = False, db: Session = Depends(get_db)) -> dict:
    article = db.get(ArticleORM, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")
    if article.language == "zh":
        raise HTTPException(status_code=400, detail="article is already Chinese")
    try:
        article = ensure_article_translation(db, article, force=force)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"translation failed: {exc.__class__.__name__}") from exc

    translation_payload = parse_translation_payload(article.translation_payload)
    return {
        "article_id": article.id,
        "translation_status": article.translation_status,
        "translated_title_zh": article.translated_title_zh,
        "translated_summary_zh": article.translated_summary_zh,
        "translated_content_zh": article.translated_content_zh,
        "translated_at": article.translated_at,
        "preserved_terms": translation_payload.get("preserved_terms", []),
    }


@router.get("/v1/runs", response_model=list[PipelineRunRead])
def list_runs(db: Session = Depends(get_db)) -> list[PipelineRunORM]:
    return load_runs(db, limit=30)


@router.get("/v1/runs/today", response_model=list[PipelineRunRead])
def list_today_runs(db: Session = Depends(get_db)) -> list[PipelineRunORM]:
    return load_runs(db, target_date=current_briefing_edition_date(), window_mode="edition", limit=30)


@router.get("/v1/runs/current-edition", response_model=list[PipelineRunRead])
def list_current_edition_runs(db: Session = Depends(get_db)) -> list[PipelineRunORM]:
    return load_runs(db, target_date=current_briefing_edition_date(), window_mode="edition", limit=30)


@router.get("/v1/runs/{run_id}", response_model=PipelineRunDetailRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(PipelineRunORM, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "id": run.id,
        "trigger_mode": run.trigger_mode,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "source_count": run.source_count,
        "collected_count": run.collected_count,
        "candidate_count": run.candidate_count,
        "analyzed_count": run.analyzed_count,
        "report_id": run.report_id,
        "error_message": run.error_message,
        "source_logs": load_source_run_logs(db, run.id),
        "stage_logs": load_stage_logs(db, run.id),
    }


@router.post("/v1/reports/daily", response_model=DailyReportRead)
def create_daily_report(payload: GenerateReportRequest, db: Session = Depends(get_db)) -> DailyReportORM:
    return render_daily_report(db, payload.report_date)


@router.get("/v1/reports/latest", response_model=DailyReportRead | None)
def latest_report(db: Session = Depends(get_db)) -> DailyReportORM | None:
    return db.scalars(select(DailyReportORM).order_by(DailyReportORM.generated_at.desc()).limit(1)).first()


@router.get("/", response_class=HTMLResponse)
def home_page(request: Request, date: str | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    context = render_dashboard_context(db, target_date=_parse_date(date))
    context["request"] = request
    return templates.TemplateResponse(request, "dashboard/index.html", context)


@router.get("/intel", response_class=HTMLResponse)
def intel_page(
    request: Request,
    date: str | None = None,
    window_mode: str = Query(default="edition", pattern="^(edition|calendar)$"),
    source_key: str | None = None,
    candidate_only: bool = False,
    major_only: bool = False,
    category: str | None = None,
    content_access: str | None = None,
    language_scope: str = Query(default="all", pattern="^(all|domestic|foreign)$"),
    limit: int = Query(default=120, ge=1, le=300),
    offset: int = Query(default=0, ge=0, le=500),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if date:
        target_date = _parse_date(date)
    else:
        target_date = current_briefing_edition_date() if window_mode == "edition" else shanghai_today()
    context = render_intel_context(
        db,
        target_date=target_date,
        window_mode=window_mode,
        source_key=source_key,
        candidate_only=candidate_only,
        major_only=major_only,
        category=category,
        content_access=content_access,
        language_scope=language_scope,
        limit=limit,
        offset=offset,
    )
    context.update(
        {
            "request": request,
            "category_labels": CATEGORY_LABELS,
            "content_access_labels": CONTENT_ACCESS_LABELS,
        }
    )
    return templates.TemplateResponse(request, "intel/index.html", context)


@router.get("/ops", response_class=HTMLResponse)
def ops_page(request: Request, date: str | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    context = render_ops_context(db, target_date=_parse_date(date) or current_briefing_edition_date())
    context["request"] = request
    return templates.TemplateResponse(request, "ops/index.html", context)


@router.get("/preview", response_class=HTMLResponse)
def preview_redirect() -> RedirectResponse:
    return RedirectResponse(url="/intel", status_code=307)


@router.get("/preview/report/{report_id}", response_class=HTMLResponse)
def preview_report(report_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    report = db.get(DailyReportORM, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return HTMLResponse(report.html)
