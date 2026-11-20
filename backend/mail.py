"""Session-scoped SMTP delivery; credentials never leave the server in responses."""
import asyncio
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from backend.telegram import DeliveryStatus


class MailSettings(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(default=465, ge=1, le=65535)
    security: Literal["ssl", "starttls"] = "ssl"
    username: str = Field(min_length=1, max_length=254, pattern=r"^[^\r\n]+$")
    password: SecretStr = Field(min_length=1, max_length=1024)
    sender: str = Field(max_length=254, pattern=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
    recipient: str = Field(max_length=254, pattern=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


@dataclass
class MailConnection:
    settings: MailSettings
    deliveries: dict[tuple[UUID, str], DeliveryStatus] = field(default_factory=dict)


class MailError(Exception):
    pass


def _send(settings: MailSettings, subject: str, text: str) -> None:
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = settings.recipient
    message["Subject"] = subject.replace("\r", " ").replace("\n", " ")
    message.set_content(text)
    context = ssl.create_default_context()
    try:
        smtp = (smtplib.SMTP_SSL(settings.host, settings.port, timeout=8, context=context)
                if settings.security == "ssl" else smtplib.SMTP(settings.host, settings.port, timeout=8))
        with smtp:
            if settings.security == "starttls":
                smtp.starttls(context=context)
            smtp.login(settings.username, settings.password.get_secret_value())
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise MailError("Сервер отклонил логин или пароль. Проверьте пароль приложения и доступ по SMTP.") from None
    except smtplib.SMTPRecipientsRefused:
        raise MailError("Сервер отклонил адрес получателя. Проверьте почту для отчётов.") from None
    except (OSError, smtplib.SMTPException, ValueError, UnicodeError):
        raise MailError("Не удалось отправить письмо. Проверьте SMTP-сервер, порт, защиту и адрес отправителя.") from None


async def send_mail(settings: MailSettings, subject: str, text: str) -> None:
    await asyncio.to_thread(_send, settings, subject, text)
