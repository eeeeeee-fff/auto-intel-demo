from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from app.config import get_settings
from app.services.formatting import format_content, strip_noise_elements


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return ensure_utc(parsedate_to_datetime(value))
    except Exception:
        pass
    normalized = value.replace("Z", "+00:00").replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return ensure_utc(datetime.strptime(normalized, fmt))
        except ValueError:
            continue
    chinese = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{1,2}))?", value)
    if chinese:
        year, month, day, hour, minute = chinese.groups()
        dt = datetime(
            int(year),
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
            tzinfo=timezone.utc,
        )
        return ensure_utc(dt)
    iso = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z)?", normalized)
    if iso:
        try:
            return ensure_utc(datetime.fromisoformat(iso.group(0).replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def parse_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.get_text(strip=True)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    return item
    return {}


def extract_published_at(soup: BeautifulSoup, html: str) -> datetime | None:
    selectors = [
        ("meta", {"property": "article:published_time"}, "content"),
        ("meta", {"name": "pubdate"}, "content"),
        ("meta", {"name": "publishdate"}, "content"),
        ("meta", {"name": "PublishDate"}, "content"),
        ("meta", {"name": "date"}, "content"),
        ("time", {"datetime": True}, "datetime"),
    ]
    for tag_name, attrs, attr_name in selectors:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get(attr_name):
            parsed = parse_datetime(tag.get(attr_name))
            if parsed:
                return parsed
    payload = parse_json_ld(soup)
    for key in ("datePublished", "dateModified"):
        parsed = parse_datetime(payload.get(key))
        if parsed:
            return parsed
    patterns = [
        r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}",
        r"\d{4}-\d{2}-\d{2}",
        r"\d{4}年\d{1,2}月\d{1,2}日(?:\s+\d{1,2}:\d{1,2})?",
    ]
    snippet = html[:4000]
    for pattern in patterns:
        match = re.search(pattern, snippet)
        if match:
            parsed = parse_datetime(match.group(0))
            if parsed:
                return parsed
    return None


def extract_main_text(soup: BeautifulSoup) -> str:
    selectors = [
        "article",
        "main",
        "[class*='article']",
        "[class*='content']",
        "[class*='detail']",
        "[class*='正文']",
        "[id*='article']",
        "[id*='content']",
    ]
    candidates: list[str] = []
    for selector in selectors:
        for node in soup.select(selector):
            paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in node.find_all("p")]
            text = "\n".join(line for line in paragraphs if line)
            if len(text) > 180:
                candidates.append(text)
    if candidates:
        return max(candidates, key=len)
    paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    return "\n".join(line for line in paragraphs if line)


def unique_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


@dataclass
class CollectedArticle:
    source_key: str
    source_name: str
    url: str
    title: str
    published_at: datetime | None
    language: str
    content_text: str = ""
    summary_hint: str = ""
    author: str | None = None
    raw_html: str | None = None
    tags: list[str] = field(default_factory=list)
    content_access: str = "full_text"


class BaseCollector:
    source_key = ""
    source_name = ""
    base_url = ""
    collector_kind = "html"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )

    def request(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.settings.request_timeout_seconds)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "text" in content_type or "html" in content_type or "xml" in content_type:
            apparent = response.apparent_encoding
            if apparent:
                response.encoding = apparent
        return response

    def collect(self, limit: int) -> list[CollectedArticle]:
        raise NotImplementedError

    def absolute_url(self, href: str) -> str:
        return urljoin(self.base_url, href)

    def build_article_from_html(
        self,
        url: str,
        language: str,
        fallback_title: str = "",
        fallback_published_at: datetime | None = None,
        fallback_summary: str = "",
    ) -> CollectedArticle:
        response = self.request(url)
        soup = BeautifulSoup(response.text, "html.parser")
        title = clean_text(soup.title.get_text()) if soup.title else fallback_title or url
        published_at = extract_published_at(soup, response.text) or fallback_published_at
        author = None
        author_meta = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", attrs={"property": "author"})
        if author_meta:
            author = clean_text(author_meta.get("content"))
        strip_noise_elements(soup)
        content_text = format_content(extract_main_text(soup))
        summary_hint = fallback_summary or clean_text(content_text[:220])
        return CollectedArticle(
            source_key=self.source_key,
            source_name=self.source_name,
            url=url,
            title=title,
            published_at=published_at,
            language=language,
            content_text=content_text,
            summary_hint=summary_hint,
            author=author,
            raw_html=response.text,
        )

    def parse_rss(self, xml_text: str) -> list[dict[str, str]]:
        root = ET.fromstring(xml_text)
        items: list[dict[str, str]] = []
        for item in root.findall("./channel/item"):
            items.append(
                {
                    "title": clean_text(item.findtext("title")),
                    "link": clean_text(item.findtext("link")).split("#")[0],
                    "description": strip_html(item.findtext("description")),
                    "pubDate": clean_text(item.findtext("pubDate")),
                }
            )
        return items

    def is_same_domain(self, url: str) -> bool:
        target = urlparse(url).netloc.replace("www.", "")
        current = urlparse(self.base_url).netloc.replace("www.", "")
        return target.endswith(current)
