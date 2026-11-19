"""Read a public page without giving page contents permission to invoke tools."""
import hashlib
from datetime import datetime
from html.parser import HTMLParser

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

from backend.llm import PublicCloudTransport
from backend.replay import Signal
from backend.signal_checks import CheckResult, Material


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groupId: str | None = Field(default=None, max_length=100)
    kind: Literal["url", "cbr"] = "url"
    url: str = Field(min_length=1, max_length=2048)
    instructions: str = Field(min_length=1, max_length=1000)

    @field_validator("url")
    @classmethod
    def public_https(cls, value: str) -> str:
        url = httpx.URL(value.strip())
        if (url.scheme != "https" or not url.host or url.userinfo or url.fragment
                or url.port not in (None, 443) or url.host == "localhost" or url.host.endswith(".localhost")):
            raise ValueError("Укажите публичную HTTPS-ссылку без логина и пароля.")
        return str(url)

    @field_validator("instructions")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Укажите задачу агенту.")
        return value.strip()


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.in_title = False
        self.title: list[str] = []
        self.parts: list[str] = []
        self.published: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta" and (attrs.get("property") or attrs.get("name")) in (
            "article:published_time", "datePublished", "date", "pubdate"):
            self.published = self.published or attrs.get("content")
        if tag == "time" and attrs.get("datetime"):
            self.published = self.published or attrs["datetime"]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


async def read_source(client: httpx.AsyncClient, source: ResearchSource, event: Signal) -> CheckResult:
    try:
        # Redirect targets are deliberately not followed: each new URL needs validation.
        async with client.stream("GET", source.url, follow_redirects=False, timeout=8,
                                 headers={"Accept": "text/html, application/xhtml+xml"}) as response:
            response.raise_for_status()
            if response.is_redirect or not any(kind in response.headers.get("content-type", "")
                                               for kind in ("text/html", "application/xhtml+xml")):
                return CheckResult("unavailable", "Нужна прямая ссылка на HTML-страницу.")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 1_000_000:
                    return CheckResult("unavailable", "Страница превышает допустимый размер.")
            page = PageParser()
            page.feed(body.decode(response.encoding or "utf-8", errors="replace"))
        text = " ".join(page.parts)[:18000]
        if not text:
            return CheckResult("unavailable", "Не удалось прочитать текст страницы.")
        try:
            published = datetime.fromisoformat((page.published or "").replace("Z", "+00:00"))
            if published.utcoffset() is None:
                raise ValueError
        except ValueError:
            return CheckResult("unavailable", "Нет точной даты публикации: материал исключён из исторического разбора.")
        if published > event.detectedAt or published < event.intervalStart:
            return CheckResult("empty", "Дата публикации вне окна сигнала.")
        title = " ".join(page.title)[:300] or httpx.URL(source.url).host
        material = Material(id="page-" + hashlib.sha256(source.url.encode()).hexdigest()[:16],
                            source=httpx.URL(source.url).host, publishedAt=published, title=title,
                            text=text, url=source.url, kind="unverified")
        return CheckResult("ok", materials=[material])
    except (httpx.HTTPError, OSError, ValueError):
        return CheckResult("unavailable", "Не удалось прочитать источник. Проверьте ссылку и доступность страницы.")


async def check_source(source: ResearchSource, event: Signal) -> CheckResult:
    async with httpx.AsyncClient(transport=PublicCloudTransport(allow_synthetic_openai=False), trust_env=False) as client:
        return await read_source(client, source, event)
