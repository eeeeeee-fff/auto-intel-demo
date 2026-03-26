from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


SOURCE_PRIORITY = {
    "reuters": 100,
    "bloomberg": 95,
    "marklines": 90,
    "autonews": 85,
    "gasgoo": 82,
    "cnautonews": 78,
    "xinhua_auto": 76,
    "just_auto": 74,
    "oica": 72,
    "iea": 70,
    "autoweek": 68,
    "eia": 64,
}

MIN_EVENT_IMPORTANCE = 1
MAX_EVENT_IMPORTANCE = 5
MAJOR_EVENT_MIN_IMPORTANCE = 3

GENERAL_NOISE_KEYWORDS = [
    "试驾",
    "亮相",
    "首发",
    "车展",
    "上市",
    "图库",
    "gallery",
    "road test",
    "first drive",
    "comparison test",
    "spy shot",
    "rendering",
    "facelift",
]

SOURCE_NOISE_KEYWORDS = {
    "autoweek": [
        "first drive",
        "instrumented test",
        "comparison test",
        "collector's item",
        "buyer's guide",
        "best cars",
    ],
    "just_auto": [
        "podcast",
        "webinar",
    ],
}

CATEGORY_KEYWORDS = {
    "policy_regulation": [
        "政策",
        "法规",
        "补贴",
        "排放",
        "双积分",
        "tariff",
        "regulation",
        "rule",
        "mandate",
        "zero-emission",
        "zev",
        "phase-out",
        "subsidy",
    ],
    "strategic_cooperation": [
        "合作",
        "合资",
        "并购",
        "入股",
        "投资",
        "partnership",
        "joint venture",
        "cooperation",
        "strategic alliance",
        "acquire",
        "stake",
    ],
    "technology_breakthrough": [
        "电池",
        "热管理",
        "核心技术",
        "平台",
        "混动",
        "增程",
        "固态",
        "battery",
        "thermal",
        "phev",
        "erev",
        "solid-state",
        "robotaxi",
        "adas",
        "autonomous",
        "chip",
        "lfp",
    ],
    "sales_data": [
        "销量",
        "交付",
        "产量",
        "production",
        "sales",
        "deliveries",
        "market share",
        "registration",
    ],
    "supply_chain": [
        "供应链",
        "原材料",
        "物流",
        "港口",
        "短缺",
        "shortage",
        "supplier",
        "procurement",
        "anode",
        "graphite",
        "recycling",
        "manufacturing hub",
        "plant",
        "battery recycling",
    ],
    "executive_change": [
        "高层",
        "管理层",
        "董事长",
        "总裁",
        "ceo",
        "cfo",
        "chairman",
        "executive",
        "leadership",
    ],
    "macro_policy": [
        "利率",
        "财政",
        "经济政策",
        "decarbonization",
        "stimulus",
        "industrial policy",
        "oil stock release",
        "energy transition",
    ],
    "geopolitics": [
        "关税",
        "贸易战",
        "制裁",
        "地缘",
        "middle east",
        "iran",
        "hormuz",
        "sanction",
        "trade barrier",
    ],
    "commodities_fx": [
        "原油",
        "汇率",
        "美元",
        "commodity",
        "oil price",
        "gas price",
        "steel",
        "chemical",
    ],
    "incident": [
        "中断",
        "停产",
        "shutdown",
        "disruption",
        "recall",
        "accident",
        "fatal",
        "fire",
        "earthquake",
        "cyberattack",
    ],
}

OICA_FORCE_CATEGORY_HINTS = {
    "major news items summarized": "macro_policy",
    "production statistics": "sales_data",
    "sales statistics": "sales_data",
    "technical committee": "policy_regulation",
}


@dataclass
class RuleDecision:
    is_candidate: bool
    is_major_event: bool
    category: str | None
    importance: int | None
    filter_reason: str | None
    summary: str
    dedupe_key: str


def clamp_importance(value: int | None, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    return max(MIN_EVENT_IMPORTANCE, min(int(value), MAX_EVENT_IMPORTANCE))


def importance_is_major(importance: int | None) -> bool:
    return importance is not None and importance >= MAJOR_EVENT_MIN_IMPORTANCE


def article_is_major(article: object) -> bool:
    importance = getattr(article, "event_importance", None)
    if importance is not None:
        return importance_is_major(clamp_importance(importance))
    return bool(getattr(article, "is_major_event", False))


def normalize_title(title: str) -> str:
    normalized = title.lower()
    normalized = re.sub(r"https?://\S+", "", normalized)
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def build_summary(text: str, fallback: str = "", max_length: int = 180) -> str:
    content = re.sub(r"\s+", " ", text or fallback).strip()
    if not content:
        return ""
    for splitter in ("。", "！", "？", ";", ".", "!", "?"):
        if splitter in content:
            first = content.split(splitter)[0].strip()
            if len(first) >= 24:
                return first[:max_length]
    return content[:max_length]


def within_lookback(published_at: datetime | None, hours: int) -> bool:
    if published_at is None:
        return True
    now = datetime.now(timezone.utc)
    return published_at >= now - timedelta(hours=hours)


def _source_noise_keywords(source_key: str | None) -> list[str]:
    if not source_key:
        return []
    return SOURCE_NOISE_KEYWORDS.get(source_key, [])


def _category_scores(haystack: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in haystack)
        if score:
            scores[category] = score
    return scores


def _oica_fallback_category(title: str, haystack: str) -> str | None:
    title_lower = title.lower()
    for keyword, category in OICA_FORCE_CATEGORY_HINTS.items():
        if keyword in title_lower or keyword in haystack:
            return category
    return None


def apply_rule_filter(
    title: str,
    content_text: str,
    summary_hint: str,
    published_at: datetime | None,
    lookback_hours: int,
    source_key: str | None = None,
) -> RuleDecision:
    haystack = f"{title}\n{summary_hint}\n{content_text}".lower()
    dedupe_key = normalize_title(title)
    summary = build_summary(content_text, summary_hint)

    if not within_lookback(published_at, lookback_hours):
        return RuleDecision(False, False, None, None, "out_of_lookback", summary, dedupe_key)

    if any(keyword.lower() in haystack for keyword in GENERAL_NOISE_KEYWORDS):
        return RuleDecision(False, False, None, None, "noise_article", summary, dedupe_key)

    if any(keyword.lower() in haystack for keyword in _source_noise_keywords(source_key)):
        return RuleDecision(False, False, None, None, "source_specific_noise", summary, dedupe_key)

    scores = _category_scores(haystack)
    if not scores and source_key == "oica":
        category = _oica_fallback_category(title, haystack)
        if category:
            return RuleDecision(True, True, category, 4, None, summary, dedupe_key)

    if not scores:
        return RuleDecision(False, False, None, None, "no_major_signal", summary, dedupe_key)

    category = max(scores, key=scores.get)
    score = scores[category]
    importance = clamp_importance(3 + min(score, 2))
    return RuleDecision(
        True,
        importance_is_major(importance),
        category,
        importance,
        None,
        summary,
        dedupe_key,
    )


def source_rank(source_key: str) -> int:
    return SOURCE_PRIORITY.get(source_key, 10)
