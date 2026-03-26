from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

from app.config import get_settings
from app.services.rules import clamp_importance


ALLOWED_CATEGORIES = {
    "policy_regulation",
    "strategic_cooperation",
    "technology_breakthrough",
    "sales_data",
    "supply_chain",
    "executive_change",
    "macro_policy",
    "geopolitics",
    "commodities_fx",
    "incident",
}

CATEGORY_ALIASES = {
    "政策法规": "policy_regulation",
    "法规政策": "policy_regulation",
    "战略合作": "strategic_cooperation",
    "并购合作": "strategic_cooperation",
    "技术突破": "technology_breakthrough",
    "销量产量": "sales_data",
    "销量数据": "sales_data",
    "供应链": "supply_chain",
    "高管变动": "executive_change",
    "宏观政策": "macro_policy",
    "地缘政治": "geopolitics",
    "大宗商品/汇率": "commodities_fx",
    "突发事件": "incident",
    "法律诉讼": "incident",
}

SOURCE_HINTS = {
    "oica": "Industry association digest and statistics source. Summary pages may aggregate multiple external news items.",
    "iea": "Energy and policy source. Macro and energy implications matter more than consumer product details.",
    "eia": "Energy and commodity data source. Price, inventory, fuel, and supply disruptions are material.",
    "autoweek": "General auto news source with some consumer coverage. Ignore test-drive, gallery, and lifestyle angles.",
    "just_auto": "Industry and supplier news source. Focus on strategy, manufacturing, investment, and supply chain changes.",
    "marklines": "Automotive industry portal. This source is index-only in this demo, so the teaser may be the only available content.",
}


@dataclass
class LLMDecision:
    category: str
    importance: int
    core_summary: str
    dedupe_key: str
    raw_payload: str


@dataclass
class TranslationDecision:
    translated_title_zh: str
    translated_summary_zh: str
    translated_content_zh: str
    preserved_terms: list[str]
    raw_payload: str


PRESERVE_TERMS = [
    "PHEV",
    "EREV",
    "BEV",
    "HEV",
    "EV",
    "OEM",
    "Tier 1",
    "Tier 2",
    "ADAS",
    "L2",
    "L3",
    "L4",
    "LFP",
    "NCM",
    "SiC",
    "IGBT",
    "BMS",
    "OTA",
    "CTC",
    "ICE",
    "eAxle",
]


class DeepSeekClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: OpenAI | None = None
        if self.settings.deepseek_api_key:
            self._client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=1,
            )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def analyze_article(
        self,
        *,
        title: str,
        source_key: str,
        source_name: str,
        url: str,
        published_at: str | None,
        content_text: str,
        summary_hint: str,
        content_access: str,
    ) -> LLMDecision:
        if not self._client:
            raise RuntimeError("DeepSeek client is not configured")

        system_prompt = (
            "You classify automotive intelligence articles.\n"
            "Return exactly one JSON object and no markdown.\n"
            "Required fields: category(string), importance(integer 1-5), core_summary(string), dedupe_key(string).\n"
            "core_summary must always be written in simplified Chinese (简体中文), regardless of the article's original language.\n"
            "Allowed category enum only: policy_regulation, strategic_cooperation, technology_breakthrough, "
            "sales_data, supply_chain, executive_change, macro_policy, geopolitics, commodities_fx, incident.\n"
            "Importance rubric: 5=industry-shaping, 4=very important, 3=material major event, 2=worth tracking but not major, 1=minor.\n"
            "The major-event threshold is fixed: importance >= 3 means major; importance <= 2 means non-major.\n"
            "Use only the provided input. Do not invent facts, companies, policies, dates, metrics, or causes.\n"
            "If content_access is index_only, treat the article as an index teaser and do not infer details that are not explicit.\n"
            "Treat policy, M&A, strategic cooperation, core technology, sales/production data, supply-chain shifts, "
            "macro energy policy, executive changes, and major disruptions as material. Be conservative if unclear."
        )
        user_prompt = {
            "source_key": source_key,
            "source_name": source_name,
            "source_profile": SOURCE_HINTS.get(source_key, "General automotive industry source."),
            "content_access": content_access,
            "title": title,
            "url": url,
            "published_at": published_at,
            "summary_hint": summary_hint,
            "content_text": content_text[:6000],
        }
        response = self._client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw_payload = response.choices[0].message.content or "{}"
        payload = json.loads(raw_payload)
        category = self._normalize_category(str(payload.get("category", "")))
        importance = clamp_importance(int(payload.get("importance", 3)), default=3) or 3
        return LLMDecision(
            category=category,
            importance=importance,
            core_summary=str(payload.get("core_summary", "")),
            dedupe_key=str(payload.get("dedupe_key", "")),
            raw_payload=raw_payload,
        )

    def _normalize_category(self, category: str) -> str:
        normalized = CATEGORY_ALIASES.get(category.strip(), category.strip())
        if normalized in ALLOWED_CATEGORIES:
            return normalized
        return "incident"

    def translate_article(
        self,
        *,
        title: str,
        source_key: str,
        source_name: str,
        content_text: str,
        summary_hint: str,
        tags: list[str],
        content_access: str,
    ) -> TranslationDecision:
        if not self._client:
            raise RuntimeError("DeepSeek client is not configured")

        system_prompt = (
            "You translate automotive industry articles into simplified Chinese.\n"
            "Return exactly one JSON object and no markdown.\n"
            "Required fields: translated_title_zh(string), translated_summary_zh(string), "
            "translated_content_zh(string), preserved_terms(array of strings).\n"
            "Rules:\n"
            "- Keep professional abbreviations and chemistry terms unchanged when they appear in the source.\n"
            "- Keep model names, platform names, company brands, and product names unchanged if there is no widely used Chinese translation.\n"
            "- Do not invent facts or add background.\n"
            "- If content_access is index_only, translate only the explicit teaser content and do not imply access to the full article.\n"
            "- Use natural business Chinese for customers.\n"
        )
        user_prompt = {
            "source_key": source_key,
            "source_name": source_name,
            "content_access": content_access,
            "preserve_terms": PRESERVE_TERMS,
            "title": title,
            "summary_hint": summary_hint,
            "tags": tags,
            "content_text": content_text[:7000],
        }
        response = self._client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw_payload = response.choices[0].message.content or "{}"
        payload = json.loads(raw_payload)
        preserved_terms = payload.get("preserved_terms") or []
        if not isinstance(preserved_terms, list):
            preserved_terms = []
        return TranslationDecision(
            translated_title_zh=str(payload.get("translated_title_zh", "")),
            translated_summary_zh=str(payload.get("translated_summary_zh", "")),
            translated_content_zh=str(payload.get("translated_content_zh", "")),
            preserved_terms=[str(item) for item in preserved_terms if str(item).strip()],
            raw_payload=raw_payload,
        )
