import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import MAX_SOURCE_TEXT_LEN

LOGGER = logging.getLogger(__name__)


def _extract_meta_content(soup: BeautifulSoup, key: str) -> str | None:
    for attr in ("property", "name"):
        meta = soup.find("meta", attrs={attr: key})
        if meta and meta.get("content"):
            return str(meta.get("content")).strip()
    return None


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _trim_text(text: str, limit: int = MAX_SOURCE_TEXT_LEN) -> str:
    if len(text) <= limit:
        return text

    clipped = text[:limit]
    last_break = max(
        clipped.rfind(". "),
        clipped.rfind("! "),
        clipped.rfind("? "),
        clipped.rfind("\n"),
    )
    if last_break > int(limit * 0.6):
        clipped = clipped[: last_break + 1]

    return clipped.strip()


def _extract_main_text(soup: BeautifulSoup) -> str:
    root = soup.find("article") or soup.find("main") or soup.body or soup

    chunks: list[str] = []
    for node in root.find_all(["p", "li", "h2", "h3"]):
        text = _normalize_whitespace(node.get_text(" ", strip=True))
        if len(text) >= 40:
            chunks.append(text)

    if chunks:
        combined = "\n\n".join(chunks)
    else:
        combined = _normalize_whitespace(root.get_text(" ", strip=True))

    return _trim_text(combined, MAX_SOURCE_TEXT_LEN)


def _extract_supported_img_candidate(img: Any, page_url: str) -> str | None:
    src = (
        img.get("src")
        or img.get("data-src")
        or img.get("data-original")
        or img.get("data-lazy-src")
    )
    if not src:
        return None

    candidate = urljoin(page_url, str(src).strip())
    path = urlparse(candidate).path.lower()
    if path.endswith((".jpg", ".jpeg", ".png")):
        return candidate

    return None


def _find_image_by_predicate(soup: BeautifulSoup, page_url: str, predicate: Any) -> str | None:
    for img in soup.find_all("img"):
        if not predicate(img):
            continue

        candidate = _extract_supported_img_candidate(img, page_url)
        if candidate:
            return candidate

    return None


def _extract_image_url(soup: BeautifulSoup, page_url: str) -> str | None:
    hero_exact = _find_image_by_predicate(
        soup,
        page_url,
        lambda img: (img.get("elementtiming") or "").strip().lower() == "blog-page-hero-image",
    )
    if hero_exact:
        return hero_exact

    hero_like = _find_image_by_predicate(
        soup,
        page_url,
        lambda img: "hero" in (img.get("elementtiming") or "").lower(),
    )
    if hero_like:
        return hero_like

    high_priority = _find_image_by_predicate(
        soup,
        page_url,
        lambda img: (img.get("fetchpriority") or "").lower() == "high"
        and (img.get("loading") or "").lower() == "eager",
    )
    if high_priority:
        return high_priority

    og_image = _extract_meta_content(soup, "og:image")
    if og_image:
        return urljoin(page_url, og_image)

    for img in soup.find_all("img"):
        candidate = _extract_supported_img_candidate(img, page_url)
        if candidate:
            return candidate

    return None


def _strip_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", text)
    return _normalize_whitespace(text)


def _extract_image_from_reader_text(text: str) -> str | None:
    candidates: list[str] = []

    markdown_image_urls = re.findall(r"!\[[^\]]*\]\((https?://[^)]+)\)", text)
    for candidate in markdown_image_urls:
        path = urlparse(candidate).path.lower()
        if path.endswith((".jpg", ".jpeg", ".png")):
            candidates.append(candidate)

    plain_urls = re.findall(r"https?://\S+", text)
    for candidate in plain_urls:
        clean_candidate = candidate.rstrip(")]},.;:!?")
        path = urlparse(clean_candidate).path.lower()
        if path.endswith((".jpg", ".jpeg", ".png")):
            candidates.append(clean_candidate)

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    if not unique_candidates:
        return None

    def score(url: str) -> int:
        lowered = url.lower()
        total = 0

        if any(token in lowered for token in ("hero", "cover", "header", "screenshot")):
            total += 30
        if "fetchpriority=high" in lowered or "resizewidth=700" in lowered:
            total += 5

        if any(token in lowered for token in ("avatar", "profile", "icon", "logo")):
            total -= 40

        return total

    best = max(unique_candidates, key=score)
    return best


def _parse_page_via_reader(url: str) -> dict[str, Any]:
    clean_url = re.sub(r"^https?://", "", url.strip())
    reader_url = f"https://r.jina.ai/http://{clean_url}"

    response = requests.get(
        reader_url,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        },
    )
    response.raise_for_status()

    lines = [line.strip() for line in response.text.splitlines() if line.strip()]

    title = "Без заголовка"
    for line in lines:
        if line.lower().startswith("title:"):
            candidate = line.split(":", 1)[1].strip()
            if candidate:
                title = candidate
                break

    if title == "Без заголовка":
        for line in lines:
            if line.startswith("#"):
                candidate = line.lstrip("#").strip()
                if candidate:
                    title = candidate
                    break

    body_lines: list[str] = []
    skip_prefixes = (
        "url source:",
        "title:",
        "published time:",
        "markdown content:",
    )
    for line in lines:
        if line.lower().startswith(skip_prefixes):
            continue
        body_lines.append(line)

    raw_body_text = "\n".join(body_lines)
    image_url = _extract_image_from_reader_text(raw_body_text)

    text = _strip_markdown(raw_body_text)
    text = _trim_text(text, MAX_SOURCE_TEXT_LEN)
    if not text:
        raise ValueError("На странице не найден текст для поста")

    return {
        "url": url,
        "title": title,
        "text": text,
        "image_url": image_url,
    }


def parse_page(url: str) -> dict[str, Any]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    response = requests.get(url, timeout=20, headers=headers)
    if response.status_code in (401, 403, 429):
        LOGGER.info(
            "Сайт вернул %s для %s, включаю резервный парсер",
            response.status_code,
            url,
        )
        return _parse_page_via_reader(url)

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    title = (
        _extract_meta_content(soup, "og:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else "")
        or (
            soup.find("h1").get_text(" ", strip=True)
            if soup.find("h1") is not None
            else ""
        )
        or "Без заголовка"
    )
    text = _extract_main_text(soup)
    if not text:
        raise ValueError("На странице не найден текст для поста")

    image_url = _extract_image_url(soup, url)

    return {
        "url": url,
        "title": title,
        "text": text,
        "image_url": image_url,
    }
