from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from app.models import (
    ArticleORM,
    DailyReportORM,
    PipelineRunORM,
    RunStageLogORM,
    SourceConfigORM,
    SourceRunLogORM,
    utc_now,
)
from app.services.rules import MAJOR_EVENT_MIN_IMPORTANCE, article_is_major, source_rank
from app.services.time_windows import (
    briefing_window,
    current_briefing_edition_date,
    format_shanghai,
    shanghai_day_bounds,
    shanghai_today,
)
from app.services.translation import article_display_summary, article_display_title, is_foreign_original


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

CATEGORY_LABELS = {
    "policy_regulation": "📋 政策法规（影响油箱技术路线）",
    "strategic_cooperation": "🤝 战略合作（OEM/供应商关系）",
    "technology_breakthrough": "⚙️ 技术突破（燃油/混动系统）",
    "sales_data": "📊 销量数据（PHEV/EREV/燃油车）",
    "supply_chain": "🔗 供应链（原材料/零部件/成本）",
    "executive_change": "👔 高管变动",
    "macro_policy": "📜 宏观政策",
    "geopolitics": "🌍 地缘政治",
    "commodities_fx": "💰 大宗商品/汇率（HDPE/钢材/原油）",
    "incident": "⚠️ 突发事件",
}

CONTENT_ACCESS_LABELS = {
    "full_text": "全文",
    "index_only": "Index-only",
}

WINDOW_MODE_LABELS = {
    "edition": "早报期次",
    "calendar": "自然日",
}

MACRO_CATEGORIES = {"macro_policy", "geopolitics", "commodities_fx", "incident"}
DOMESTIC_SOURCE_KEYS = {"cnautonews", "gasgoo", "xinhua_auto"}
MAX_REPORT_ITEMS = 12


def parse_tags_json(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def parse_analysis_payload(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
    if isinstance(parsed, dict):
        return parsed
    return {"raw": parsed}


def _calendar_date(value: date | None) -> date:
    return value or shanghai_today()


def _edition_date(value: date | None) -> date:
    return value or current_briefing_edition_date()


def build_time_window_context(target_date: date | None = None, *, window_mode: str = "edition") -> dict[str, Any]:
    if window_mode == "calendar":
        active_date = _calendar_date(target_date)
        start_at, end_at = shanghai_day_bounds(active_date)
        return {
            "window_mode": "calendar",
            "window_mode_label": WINDOW_MODE_LABELS["calendar"],
            "active_date": active_date,
            "edition_date": None,
            "window_start_at": start_at,
            "window_end_at": end_at,
            "window_start_label": format_shanghai(start_at),
            "window_end_label": format_shanghai(end_at),
            "window_label": f"{active_date.isoformat()} 00:00 - 23:59",
            "cutoff_label": "00:00",
        }

    window = briefing_window(target_date)
    return {
        "window_mode": "edition",
        "window_mode_label": WINDOW_MODE_LABELS["edition"],
        "active_date": window.edition_date,
        "edition_date": window.edition_date,
        "window_start_at": window.start_at,
        "window_end_at": window.end_at,
        "window_start_label": format_shanghai(window.start_at),
        "window_end_label": format_shanghai(window.end_at),
        "window_label": window.label,
        "cutoff_label": window.cutoff_label,
    }


def _preview_sort_key(item: ArticleORM) -> tuple[int, int, int, datetime]:
    published_at = item.published_at or datetime.min.replace(tzinfo=timezone.utc)
    return (
        1 if item.content_access == "full_text" else 0,
        item.event_importance or 0,
        source_rank(item.source_key),
        published_at,
    )


def _report_eligible(article: ArticleORM) -> bool:
    if article.source_key == "marklines" and article.content_access == "index_only":
        return (article.event_importance or 0) >= 4
    return True


def _major_event_condition():
    return or_(
        ArticleORM.event_importance >= MAJOR_EVENT_MIN_IMPORTANCE,
        and_(ArticleORM.event_importance.is_(None), ArticleORM.is_major_event.is_(True)),
    )


def _dedupe_articles_for_report(articles: list[ArticleORM]) -> list[ArticleORM]:
    grouped: dict[str, list[ArticleORM]] = defaultdict(list)
    for article in articles:
        grouped[article.dedupe_key or article.title].append(article)

    selected: list[ArticleORM] = []
    for bucket in grouped.values():
        bucket = [article for article in bucket if _report_eligible(article)]
        if not bucket:
            continue
        bucket.sort(key=_preview_sort_key, reverse=True)
        selected.append(bucket[0])
    selected.sort(key=_preview_sort_key, reverse=True)
    return selected


def _rebalance_report_articles(articles: list[ArticleORM], max_items: int = MAX_REPORT_ITEMS) -> list[ArticleORM]:
    if not articles:
        return []

    reserved: list[ArticleORM] = []
    seen_ids: set[str] = set()
    foreign_picks: dict[str, ArticleORM] = {}
    for article in articles:
        if article.source_key in DOMESTIC_SOURCE_KEYS:
            continue
        if (article.event_importance or 0) < 4:
            continue
        foreign_picks.setdefault(article.source_key, article)

    for article in sorted(foreign_picks.values(), key=_preview_sort_key, reverse=True)[:3]:
        reserved.append(article)
        seen_ids.add(article.id)

    ordered = reserved + [article for article in articles if article.id not in seen_ids]
    return ordered[:max_items]


def _apply_published_window(
    statement: Select[tuple[ArticleORM]],
    *,
    start_at: datetime,
    end_at: datetime,
    inclusive_start: bool,
) -> Select[tuple[ArticleORM]]:
    statement = statement.where(ArticleORM.published_at.is_not(None))
    if inclusive_start:
        statement = statement.where(ArticleORM.published_at >= start_at)
    else:
        statement = statement.where(ArticleORM.published_at > start_at)
    return statement.where(ArticleORM.published_at <= end_at)


def query_articles(
    session: Session,
    *,
    target_date: date | None = None,
    window_mode: str = "edition",
    window_start_at: datetime | None = None,
    window_end_at: datetime | None = None,
    source_key: str | None = None,
    candidate_only: bool = False,
    major_only: bool = False,
    category: str | None = None,
    content_access: str | None = None,
    language_scope: str = "all",
    limit: int = 120,
    offset: int = 0,
) -> list[ArticleORM]:
    statement = select(ArticleORM)

    if window_start_at is not None and window_end_at is not None:
        statement = _apply_published_window(
            statement,
            start_at=window_start_at,
            end_at=window_end_at,
            inclusive_start=False,
        )
    elif window_mode == "calendar":
        start_at, end_at = shanghai_day_bounds(_calendar_date(target_date))
        statement = _apply_published_window(
            statement,
            start_at=start_at,
            end_at=end_at,
            inclusive_start=True,
        )
    else:
        window = briefing_window(_edition_date(target_date))
        statement = _apply_published_window(
            statement,
            start_at=window.start_at,
            end_at=window.end_at,
            inclusive_start=False,
        )

    if source_key:
        statement = statement.where(ArticleORM.source_key == source_key)
    if candidate_only:
        statement = statement.where(ArticleORM.is_candidate.is_(True))
    if major_only:
        statement = statement.where(_major_event_condition())
    if category:
        statement = statement.where(ArticleORM.event_category == category)
    if content_access:
        statement = statement.where(ArticleORM.content_access == content_access)
    if language_scope == "domestic":
        statement = statement.where(ArticleORM.language == "zh")
    elif language_scope == "foreign":
        statement = statement.where(ArticleORM.language != "zh")

    statement = (
        statement.order_by(ArticleORM.published_at.desc().nullslast(), ArticleORM.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement))


def load_major_articles(
    session: Session,
    *,
    target_date: date | None = None,
    window_mode: str = "edition",
    window_start_at: datetime | None = None,
    window_end_at: datetime | None = None,
) -> list[ArticleORM]:
    statement = select(ArticleORM).where(_major_event_condition())
    if window_start_at is not None and window_end_at is not None:
        statement = _apply_published_window(
            statement,
            start_at=window_start_at,
            end_at=window_end_at,
            inclusive_start=False,
        )
    elif window_mode == "calendar":
        start_at, end_at = shanghai_day_bounds(_calendar_date(target_date))
        statement = _apply_published_window(
            statement,
            start_at=start_at,
            end_at=end_at,
            inclusive_start=True,
        )
    else:
        window = briefing_window(_edition_date(target_date))
        statement = _apply_published_window(
            statement,
            start_at=window.start_at,
            end_at=window.end_at,
            inclusive_start=False,
        )
    statement = statement.order_by(ArticleORM.published_at.desc())
    deduped = _dedupe_articles_for_report(list(session.scalars(statement)))
    return _rebalance_report_articles(deduped)


def load_today_major_articles(session: Session, target_date: date | None = None) -> list[ArticleORM]:
    return load_major_articles(session, target_date=target_date, window_mode="calendar")


def build_source_stats(articles: list[ArticleORM]) -> list[dict[str, object]]:
    buckets: dict[str, dict[str, object]] = {}
    for article in articles:
        stats = buckets.setdefault(
            article.source_key,
            {
                "source_key": article.source_key,
                "source_name": article.source_name,
                "article_count": 0,
                "candidate_count": 0,
                "major_count": 0,
                "latest_published_at": article.published_at,
            },
        )
        stats["article_count"] = int(stats["article_count"]) + 1
        if article.is_candidate:
            stats["candidate_count"] = int(stats["candidate_count"]) + 1
        if article_is_major(article):
            stats["major_count"] = int(stats["major_count"]) + 1
        latest_published_at = stats["latest_published_at"]
        if latest_published_at is None or (article.published_at and article.published_at > latest_published_at):
            stats["latest_published_at"] = article.published_at

    return sorted(
        buckets.values(),
        key=lambda item: (
            int(item["major_count"]),
            int(item["candidate_count"]),
            int(item["article_count"]),
            item["source_name"],
        ),
        reverse=True,
    )


def get_latest_run(session: Session) -> PipelineRunORM | None:
    return session.scalars(select(PipelineRunORM).order_by(PipelineRunORM.started_at.desc()).limit(1)).first()


def load_runs(
    session: Session,
    *,
    target_date: date | None = None,
    window_mode: str = "edition",
    limit: int = 30,
) -> list[PipelineRunORM]:
    statement = select(PipelineRunORM)
    if target_date is not None:
        if window_mode == "calendar":
            start_at, end_at = shanghai_day_bounds(_calendar_date(target_date))
            statement = statement.where(PipelineRunORM.started_at >= start_at).where(PipelineRunORM.started_at <= end_at)
        else:
            window = briefing_window(_edition_date(target_date))
            statement = statement.where(PipelineRunORM.started_at > window.start_at).where(PipelineRunORM.started_at <= window.end_at)
    statement = statement.order_by(PipelineRunORM.started_at.desc()).limit(limit)
    return list(session.scalars(statement))


def load_source_run_logs(session: Session, run_id: str) -> list[SourceRunLogORM]:
    statement = select(SourceRunLogORM).where(SourceRunLogORM.run_id == run_id).order_by(SourceRunLogORM.started_at.asc())
    return list(session.scalars(statement))


def load_stage_logs(session: Session, run_id: str) -> list[RunStageLogORM]:
    statement = select(RunStageLogORM).where(RunStageLogORM.run_id == run_id).order_by(RunStageLogORM.started_at.asc())
    return list(session.scalars(statement))


def load_source_runs(session: Session, source_key: str, *, limit: int = 10) -> list[SourceRunLogORM]:
    statement = (
        select(SourceRunLogORM)
        .where(SourceRunLogORM.source_key == source_key)
        .order_by(SourceRunLogORM.started_at.desc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def build_global_summary(articles: list[ArticleORM]) -> dict[str, str | list[str]]:
    if not articles:
        return {
            "macro_scan": "本期早报窗口内暂无达到重大事件阈值的公开资讯，建议检查采集窗口、候选阈值和来源运行情况。",
            "strategic_view": "当前未形成可稳定提炼的行业主线，建议优先核对来源站点的发布时间和翻译完成率。",
            "actions": ["先确认各来源本期是否真实产出，再决定是否下调候选阈值或补充持续跟踪项。"],
        }

    auto_events = [item for item in articles if item.event_category not in MACRO_CATEGORIES]
    macro_events = [item for item in articles if item.event_category in MACRO_CATEGORIES]
    top = sorted(articles, key=_preview_sort_key, reverse=True)[0]
    source_count = len({item.source_key for item in articles})

    macro_scan = (
        f"本期共纳入 {len(articles)} 条重大事件，覆盖 {source_count} 个来源。"
        f" 其中汽车产业事件 {len(auto_events)} 条，宏观与政策扰动 {len(macro_events)} 条。"
    )
    strategic_view = f"当前最强信号来自 {top.source_name}：{article_display_title(top)}"
    actions = [
        "优先复核重要度 4-5 的政策、供应链和技术事件，确认是否需要升级为跟踪主题。",
        "对境外来源保持中文优先展示，但在详情保留原文，方便销售演示和客户复核。",
        "采集中心重点看来源覆盖和阶段日志，避免首页结论被单一来源主导。",
    ]
    return {"macro_scan": macro_scan, "strategic_view": strategic_view, "actions": actions}


def build_business_analysis(articles: list[ArticleORM]) -> dict[str, Any]:
    """构建业务四维分析（汽车油箱系统产业视角）"""
    # 基于新闻内容自动判断业务影响
    
    # 1. 主营业务影响分析
    business_impact = "基于今日新闻，油箱需求预期保持稳定。需持续关注 PHEV/EREV 趋势对高压油箱的拉动作用。"
    phev_erev_trend = "今日无明确 PHEV/EREV 增速信号，建议持续跟踪混动销量数据和 OEM 技术路线规划。"
    cost_risks = "今日无重大原材料价格波动报道，HDPE、塑料粒子和钢材价格维持震荡。"
    customer_opportunities = []
    
    # 简单关键词匹配来识别机会
    for article in articles:
        text = (article.title or "") + " " + (article.summary_hint or "")
        text_lower = text.lower()
        
        # 产能扩张信号
        if any(kw in text_lower for kw in ["新工厂", "产能扩张", "海外投资", "greenfield", "capacity expansion"]):
            customer_opportunities.append(f"OEM 产能扩张可能带动油箱需求：{article_display_title(article)[:40]}...")
        
        # 合作机会信号
        if any(kw in text_lower for kw in ["合作", "定点", "供应协议", "partnership", "supply agreement"]):
            customer_opportunities.append(f"潜在客户合作机会：{article_display_title(article)[:40]}...")
        
        # PHEV/EREV 趋势信号
        if any(kw in text_lower for kw in ["phev", "增程", "erev", "插电混动", "plug-in hybrid"]):
            if "增长" in text or "加速" in text or "increase" in text_lower or "accelerate" in text_lower:
                phev_erev_trend = "PHEV/EREV 市场呈现加速发展趋势，高压油箱需求有望持续受益。"
            elif "放缓" in text or "下降" in text or "slow" in text_lower or "decline" in text_lower:
                phev_erev_trend = "PHEV/EREV 增速可能放缓，需关注对高压油箱业务的潜在影响。"
        
        # 成本风险信号
        if any(kw in text_lower for kw in ["hdpe", "聚乙烯", "塑料粒子", "steel", "原油", "crude oil"]):
            if "涨价" in text or "上涨" in text or "rise" in text_lower or "increase" in text_lower:
                cost_risks = f"原材料价格上涨压力：{article_display_title(article)[:35]}..."
        
        # 政策法规影响
        if article.event_category == "policy_regulation":
            if "排放" in text or "emission" in text_lower:
                business_impact = "排放法规升级可能加速燃油系统技术迭代，高压油箱和混动系统迎来发展机遇。"
    
    return {
        "business_impact": business_impact,
        "phev_erev_trend": phev_erev_trend,
        "cost_risks": cost_risks,
        "customer_opportunities": customer_opportunities[:5],  # 最多 5 条
    }


def render_daily_report(session: Session, report_date: date | None = None) -> DailyReportORM:
    active_date = _edition_date(report_date)
    window_context = build_time_window_context(active_date, window_mode="edition")
    articles = load_major_articles(session, target_date=active_date, window_mode="edition")
    auto_events = [item for item in articles if item.event_category not in MACRO_CATEGORIES]
    macro_events = [item for item in articles if item.event_category in MACRO_CATEGORIES]
    summary = build_global_summary(articles)
    business_analysis = build_business_analysis(articles)

    html = templates.get_template("reports/daily.html").render(
        report_date=active_date.isoformat(),
        generated_at=utc_now().isoformat(),
        briefing_window=window_context,
        global_summary=summary,
        business_analysis=business_analysis,
        auto_events=auto_events,
        macro_events=macro_events,
        category_labels=CATEGORY_LABELS,
        content_access_labels=CONTENT_ACCESS_LABELS,
        article_display_title=article_display_title,
        article_display_summary=article_display_summary,
    )
    existing = session.scalars(select(DailyReportORM).where(DailyReportORM.report_date == active_date)).first()
    if existing is None:
        existing = DailyReportORM(report_date=active_date, html=html)
        session.add(existing)
    existing.html = html
    existing.generated_at = utc_now()
    existing.major_event_count = len(articles)
    existing.source_count = len({item.source_key for item in articles})
    session.commit()
    session.refresh(existing)
    return existing


def get_latest_report_article_ids(session: Session, latest_report: DailyReportORM | None) -> set[str]:
    if latest_report is None:
        return set()
    return {
        article.id
        for article in load_major_articles(session, target_date=latest_report.report_date, window_mode="edition")
    }


def render_intel_context(
    session: Session,
    *,
    target_date: date | None,
    window_mode: str = "edition",
    source_key: str | None = None,
    candidate_only: bool = False,
    major_only: bool = False,
    category: str | None = None,
    content_access: str | None = None,
    language_scope: str = "all",
    limit: int = 120,
    offset: int = 0,
) -> dict[str, Any]:
    if window_mode == "calendar":
        active_date = _calendar_date(target_date)
    else:
        active_date = _edition_date(target_date)
    window_context = build_time_window_context(active_date, window_mode=window_mode)

    recent_articles = query_articles(session, target_date=active_date, window_mode=window_mode, limit=240)
    filtered_articles = query_articles(
        session,
        target_date=active_date,
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
    source_options = list(session.scalars(select(SourceConfigORM).order_by(SourceConfigORM.key)))
    return {
        "articles": filtered_articles,
        "source_stats": build_source_stats(recent_articles),
        "source_options": source_options,
        "category_labels": CATEGORY_LABELS,
        "content_access_labels": CONTENT_ACCESS_LABELS,
        "window_mode_labels": WINDOW_MODE_LABELS,
        "active_date": active_date,
        "window_info": window_context,
        "filters": {
            "date": active_date.isoformat(),
            "window_mode": window_mode,
            "source_key": source_key or "",
            "candidate_only": candidate_only,
            "major_only": major_only,
            "category": category or "",
            "content_access": content_access or "",
            "language_scope": language_scope,
            "limit": limit,
            "offset": offset,
        },
        "totals": {
            "article_count": len(filtered_articles),
            "candidate_count": len([item for item in filtered_articles if item.is_candidate]),
            "major_count": len([item for item in filtered_articles if article_is_major(item)]),
            "foreign_count": len([item for item in filtered_articles if is_foreign_original(item)]),
        },
    }
