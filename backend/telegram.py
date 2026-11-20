import re
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, UUID4

from backend.replay import Signal


DeliveryStatus = Literal["pending", "sent", "failed", "unconnected"]


class TelegramSettings(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    token: SecretStr
    chat_id: str = Field(max_length=80, pattern=r"^(-?[0-9]+|@[A-Za-z0-9_]+)$")


class ScenarioDelivery(BaseModel):
    run_id: UUID4
    scenario_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=80)

    @property
    def key(self) -> tuple[UUID, str]:
        return self.run_id, self.scenario_id


@dataclass
class TelegramConnection:
    settings: TelegramSettings
    deliveries: dict[tuple[UUID, str], DeliveryStatus] = field(default_factory=dict)


class TelegramError(Exception):
    pass


def valid_token(settings: TelegramSettings) -> bool:
    token = settings.token.get_secret_value()
    return len(token) <= 128 and re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token) is not None


async def send_message(settings: TelegramSettings, text: str) -> None:
    token = settings.token.get_secret_value()
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": settings.chat_id, "text": text, "link_preview_options": {"is_disabled": True}},
            )
        result = response.json()
    except (httpx.RequestError, ValueError):
        raise TelegramError("Не удалось получить ответ от Telegram. Проверьте соединение и повторите попытку.") from None
    if response.status_code == 401:
        raise TelegramError("Telegram отклонил токен бота. Проверьте токен в BotFather.")
    if response.status_code == 403:
        raise TelegramError("Бот не может писать в этот чат. Проверьте, что бот не заблокирован и у него есть доступ.")
    if not response.is_success or not isinstance(result, dict) or result.get("ok") is not True:
        if isinstance(result, dict) and result.get("description") == "Bad Request: chat not found":
            raise TelegramError("Telegram не нашёл чат. Проверьте ID чата и отправьте /start этому боту.")
        raise TelegramError("Telegram не принял сообщение. Проверьте токен, чат и права бота.")


def report_text(event: Signal, scenario: ScenarioDelivery, result: dict, *, truncate: bool = True) -> str:
    movement = f"{event.changePercent:+.2f}".replace(".", ",")
    mode = "симуляция · вымышленные данные" if event.synthetic else "исторический эпизод"
    lines = [
        f"AI Штурман · {scenario.name}",
        f"{event.ticker} {movement}% · {event.detectedAt:%d.%m.%Y %H:%M} МСК ({mode})",
    ]
    synthesis = result["synthesis"]
    if synthesis:
        if synthesis["summary"]:
            lines.extend(["", synthesis["summary"]])
        for group, title in (("facts", "По материалам"), ("hypotheses", "Возможные причины"), ("questions", "Что проверить")):
            if synthesis[group]:
                lines.extend(["", title])
                lines.extend(f"• {item if isinstance(item, str) else item['text']}" for item in synthesis[group])
        citations = {item["url"]: item["source"] or item["title"]
                     for group in ("facts", "hypotheses") for statement in synthesis[group]
                     for item in statement["citations"] if item["url"]}
        if citations:
            lines.extend(["", "Источники", *(f"{label} · {url}" for url, label in citations.items())])
    else:
        lines.extend(["", "Сводка по источникам"])
        checks = result["checks"]
        comparison = checks["market"]["facts"].get("comparison")
        if comparison:
            change = f"{comparison['changePercent']:+.2f}".replace(".", ",")
            label = "Учебный индекс" if event.synthetic else "IMOEX"
            lines.append(f"• {label} {change}% за тот же час")
        for check in (checks["news"], checks["dividends"], checks["reports"], result.get("cbr")):
            if check and check["status"] != "disabled":
                titles = [item["title"] for item in check["materials"]]
                if check["reason"] or titles:
                    lines.append("• " + (check["reason"] or titles[0]))
        if lines[-1] == "Сводка по источникам":
            lines.append("Доступных данных недостаточно, чтобы объяснить движение цены.")
        if result["reason"]:
            lines.extend(["", f"ИИ-разбор: {result['reason']}"])
    text = "\n".join(lines)
    # Leave room under the Telegram message limit even for astral characters.
    encoded = text.encode("utf-16-le")
    return text if not truncate or len(encoded) <= 8000 else encoded[:7998].decode("utf-16-le", errors="ignore").rstrip() + "…"
