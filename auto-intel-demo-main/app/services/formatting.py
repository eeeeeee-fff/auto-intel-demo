from __future__ import annotations

import re

from bs4 import BeautifulSoup


_NOISE_TAGS = ["nav", "footer", "aside", "header"]

_NOISE_CSS = [
    "[class*='cookie']",
    "[class*='banner']",
    "[class*='related-article']",
    "[class*='related_article']",
    "[class*='ad-container']",
    "[class*='ad_container']",
    "[class*='social-share']",
    "[class*='social_share']",
    "[class*='share-bar']",
    "[class*='newsletter']",
    "[class*='sidebar']",
    "[class*='popup']",
    "[id*='cookie']",
    "[id*='ad-container']",
    "[id*='ad_container']",
    "[id*='newsletter']",
    "[id*='sidebar']",
]

_NOISE_LINE_PATTERNS = re.compile(
    r"(?i)"
    r"^(cookie|we use cookies|accept all|reject all|manage preferences)"
    r"|^(share|tweet|email|print|copy link|follow us)\s*$"
    r"|^related articles?\s*$"
    r"|^(advertisement|sponsored)\s*$"
    r"|^©\s"
    r"|^copyright\s"
    r"|^all rights reserved"
)


def strip_noise_elements(soup: BeautifulSoup) -> None:
    for tag_name in _NOISE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()
    for selector in _NOISE_CSS:
        for el in soup.select(selector):
            el.decompose()


def clean_lines(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if len(stripped) < 4:
            continue
        if _NOISE_LINE_PATTERNS.search(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def format_content(text: str) -> str:
    text = clean_lines(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
