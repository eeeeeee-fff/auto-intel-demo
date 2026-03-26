from __future__ import annotations

import re
from typing import Type

from bs4 import BeautifulSoup

from .base import BaseCollector, CollectedArticle, clean_text, parse_datetime, unique_urls


def _clean_url(url: str) -> str:
    return url.split("#", 1)[0].split("?", 1)[0].strip()


class ChinaAutoNewsCollector(BaseCollector):
    source_key = "cnautonews"
    source_name = "中国汽车报"
    base_url = "http://www.cnautonews.com/"
    sitemap_url = "http://www.cnautonews.com/sitemap.xml"
    section_keywords = ("yaowen", "chengyongcar", "shangyongcar", "lingbujian", "xinnengyuan", "qiche", "chanye")

    def collect(self, limit: int) -> list[CollectedArticle]:
        # 尝试从 sitemap 获取 URL
        urls: list[str] = []
        try:
            sitemap = self.request(self.sitemap_url)
            sitemap_soup = BeautifulSoup(sitemap.text, "xml")
            for loc in sitemap_soup.find_all("loc"):
                href = _clean_url(loc.get_text(strip=True))
                if any(keyword in href for keyword in self.section_keywords) and re.search(r"/\d{4}/\d{2}/\d{2}/.*\.html$", href):
                    urls.append(href)
        except Exception as e:
            print(f"[{self.source_name}] Sitemap 请求失败：{e}")
        
        # 如果 sitemap 没有获取到 URL，回退到首页抓取
        if not urls:
            try:
                response = self.request(self.base_url)
                soup = BeautifulSoup(response.text, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    href = _clean_url(self.absolute_url(anchor["href"]))
                    if re.search(r"/\d{4}/\d{2}/\d{2}/.*\.html$", href):
                        urls.append(href)
            except Exception as e:
                print(f"[{self.source_name}] 首页抓取失败：{e}")
        
        # 如果仍然没有 URL，放宽条件从 sitemap 获取所有 html 链接
        if not urls:
            try:
                sitemap = self.request(self.sitemap_url)
                sitemap_soup = BeautifulSoup(sitemap.text, "xml")
                for loc in sitemap_soup.find_all("loc"):
                    href = _clean_url(loc.get_text(strip=True))
                    if re.search(r"\.html$", href) and self.is_same_domain(href):
                        urls.append(href)
            except Exception as e:
                print(f"[{self.source_name}] 放宽条件获取 sitemap 失败：{e}")
        
        return [self.build_article_from_html(url, language="zh") for url in unique_urls(urls)[:limit]]


class GasgooCollector(BaseCollector):
    source_key = "gasgoo"
    source_name = "盖世汽车"
    base_url = "https://auto.gasgoo.com/"
    feed_url = "https://auto.gasgoo.com/Rss/ClassRss.aspx?ClassId=-1"

    def collect(self, limit: int) -> list[CollectedArticle]:
        response = self.request(self.feed_url)
        items = self.parse_rss(response.text)
        articles = []
        for item in items[:limit]:
            article = self.build_article_from_html(
                item["link"],
                language="zh",
                fallback_title=item["title"],
                fallback_published_at=parse_datetime(item["pubDate"]),
                fallback_summary=item["description"],
            )
            articles.append(article)
        return articles


class XinhuaAutoCollector(BaseCollector):
    source_key = "xinhua_auto"
    source_name = "新华网汽车"
    base_url = "http://www.news.cn/auto/"

    def collect(self, limit: int) -> list[CollectedArticle]:
        response = self.request(self.base_url)
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for anchor in soup.find_all("a", href=True):
            href = _clean_url(self.absolute_url(anchor["href"]))
            if re.search(r"/auto/\d{8}/.+/c\.html$", href):
                urls.append(href)
        return [self.build_article_from_html(url, language="zh") for url in unique_urls(urls)[:limit]]


class IEANewsCollector(BaseCollector):
    source_key = "iea"
    source_name = "IEA"
    base_url = "https://www.iea.org/news"

    def collect(self, limit: int) -> list[CollectedArticle]:
        response = self.request(self.base_url)
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for anchor in soup.find_all("a", href=True):
            href = _clean_url(self.absolute_url(anchor["href"]))
            if href.startswith("https://www.iea.org/news/") and "#content" not in href:
                urls.append(href)
        return [self.build_article_from_html(url, language="en") for url in unique_urls(urls)[:limit]]


class EIARssCollector(BaseCollector):
    source_key = "eia"
    source_name = "EIA"
    base_url = "https://www.eia.gov/todayinenergy/"
    feed_url = "https://www.eia.gov/rss/todayinenergy.xml"

    def collect(self, limit: int) -> list[CollectedArticle]:
        response = self.request(self.feed_url)
        items = self.parse_rss(response.text)
        articles = []
        for item in items[:limit]:
            article = self.build_article_from_html(
                item["link"],
                language="en",
                fallback_title=item["title"],
                fallback_published_at=parse_datetime(item["pubDate"]),
                fallback_summary=item["description"],
            )
            articles.append(article)
        return articles


class JustAutoCollector(BaseCollector):
    source_key = "just_auto"
    source_name = "Just Auto"
    base_url = "https://www.just-auto.com/"
    news_url = "https://www.just-auto.com/news/"

    def collect(self, limit: int) -> list[CollectedArticle]:
        response = self.request(self.news_url)
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for anchor in soup.find_all("a", href=True):
            href = _clean_url(self.absolute_url(anchor["href"]))
            if re.match(r"^https://www\.just-auto\.com/news/[^/]+/?$", href) and href != self.news_url:
                urls.append(href)
        return [self.build_article_from_html(url, language="en") for url in unique_urls(urls)[:limit]]


class AutoweekCollector(BaseCollector):
    source_key = "autoweek"
    source_name = "Autoweek"
    base_url = "https://www.autoweek.com/news/"
    feed_url = "https://www.autoweek.com/rss/news.xml"

    def collect(self, limit: int) -> list[CollectedArticle]:
        response = self.request(self.feed_url)
        items = self.parse_rss(response.text)
        articles = []
        for item in items[:limit]:
            article = self.build_article_from_html(
                item["link"],
                language="en",
                fallback_title=item["title"],
                fallback_published_at=parse_datetime(item["pubDate"]),
                fallback_summary=item["description"],
            )
            articles.append(article)
        return articles


class OICANewsCollector(BaseCollector):
    source_key = "oica"
    source_name = "OICA"
    base_url = "https://oica.net/"
    landing_pages = ("https://oica.net/news/", "https://oica.net/latest-news/")
    excluded_paths = {
        "",
        "about",
        "all-members",
        "news",
        "top-5-news",
        "members-news",
        "latest-news",
        "statistics",
        "production-statistics",
        "sales-statistics",
        "industry-topics",
        "motor-shows",
        "unece",
        "contact",
    }

    def collect(self, limit: int) -> list[CollectedArticle]:
        urls: list[str] = []
        for page_url in self.landing_pages:
            response = self.request(page_url)
            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = _clean_url(self.absolute_url(anchor["href"]))
                if not self.is_same_domain(href):
                    continue
                if self._looks_like_article(href):
                    urls.append(href)
        return [self.build_article_from_html(url, language="en") for url in unique_urls(urls)[:limit]]

    def _looks_like_article(self, url: str) -> bool:
        path = re.sub(r"^https?://(?:www\.)?oica\.net/?", "", url).strip("/")
        if not path or path in self.excluded_paths:
            return False
        if "/" in path:
            return False
        if "oicas-5-major-news-items-summarized" in path:
            return True
        return path.count("-") >= 4


class MarkLinesCollector(BaseCollector):
    source_key = "marklines"
    source_name = "MarkLines"
    base_url = "https://www.marklines.com/"
    news_url = "https://www.marklines.com/en/news/latest"

    def collect(self, limit: int) -> list[CollectedArticle]:
        response = self.request(self.news_url)
        soup = BeautifulSoup(response.text, "html.parser")
        articles: list[CollectedArticle] = []

        for card in soup.select("article.simplified-news-card"):
            title_anchor = card.select_one("h3.news-title a")
            teaser_node = card.select_one("p.news-body")
            time_node = card.select_one("time[datetime]")
            if title_anchor is None or time_node is None:
                continue

            href = _clean_url(self.absolute_url(title_anchor.get("href", "")))
            title = clean_text(title_anchor.get_text(" ", strip=True))
            teaser = clean_text(teaser_node.get_text(" ", strip=True)) if teaser_node else ""
            published_at = parse_datetime(time_node.get("datetime"))
            tags = [clean_text(tag.get_text(" ", strip=True)) for tag in card.select("ul.tag-group a")]
            tags = [tag for tag in tags if tag]

            if not href or not title:
                continue

            articles.append(
                CollectedArticle(
                    source_key=self.source_key,
                    source_name=self.source_name,
                    url=href,
                    title=title,
                    published_at=published_at,
                    language="en",
                    content_text=teaser,
                    summary_hint=teaser,
                    tags=tags,
                    content_access="index_only",
                )
            )

        deduped: list[CollectedArticle] = []
        seen_urls: set[str] = set()
        for article in articles:
            if article.url in seen_urls:
                continue
            seen_urls.add(article.url)
            deduped.append(article)
        return deduped[:limit]


COLLECTOR_REGISTRY: dict[str, Type[BaseCollector]] = {
    ChinaAutoNewsCollector.source_key: ChinaAutoNewsCollector,
    GasgooCollector.source_key: GasgooCollector,
    XinhuaAutoCollector.source_key: XinhuaAutoCollector,
    IEANewsCollector.source_key: IEANewsCollector,
    EIARssCollector.source_key: EIARssCollector,
    JustAutoCollector.source_key: JustAutoCollector,
    AutoweekCollector.source_key: AutoweekCollector,
    OICANewsCollector.source_key: OICANewsCollector,
    MarkLinesCollector.source_key: MarkLinesCollector,
}


DEFAULT_SOURCE_CONFIGS = [
    {
        "key": ChinaAutoNewsCollector.source_key,
        "name": ChinaAutoNewsCollector.source_name,
        "base_url": ChinaAutoNewsCollector.base_url,
        "collector_kind": "html",
        "schedule_minutes": 60,
    },
    {
        "key": GasgooCollector.source_key,
        "name": GasgooCollector.source_name,
        "base_url": GasgooCollector.base_url,
        "collector_kind": "rss+html",
        "schedule_minutes": 60,
    },
    {
        "key": XinhuaAutoCollector.source_key,
        "name": XinhuaAutoCollector.source_name,
        "base_url": XinhuaAutoCollector.base_url,
        "collector_kind": "html",
        "schedule_minutes": 60,
    },
    {
        "key": IEANewsCollector.source_key,
        "name": IEANewsCollector.source_name,
        "base_url": IEANewsCollector.base_url,
        "collector_kind": "html",
        "schedule_minutes": 180,
    },
    {
        "key": EIARssCollector.source_key,
        "name": EIARssCollector.source_name,
        "base_url": EIARssCollector.base_url,
        "collector_kind": "rss+html",
        "schedule_minutes": 180,
    },
    {
        "key": JustAutoCollector.source_key,
        "name": JustAutoCollector.source_name,
        "base_url": JustAutoCollector.base_url,
        "collector_kind": "html",
        "schedule_minutes": 60,
    },
    {
        "key": AutoweekCollector.source_key,
        "name": AutoweekCollector.source_name,
        "base_url": AutoweekCollector.base_url,
        "collector_kind": "rss+html",
        "schedule_minutes": 60,
    },
    {
        "key": OICANewsCollector.source_key,
        "name": OICANewsCollector.source_name,
        "base_url": OICANewsCollector.base_url,
        "collector_kind": "html",
        "schedule_minutes": 720,
    },
    {
        "key": MarkLinesCollector.source_key,
        "name": MarkLinesCollector.source_name,
        "base_url": MarkLinesCollector.base_url,
        "collector_kind": "index-only",
        "schedule_minutes": 60,
    },
]


def build_collector(source_key: str) -> BaseCollector:
    collector_cls = COLLECTOR_REGISTRY[source_key]
    return collector_cls()
