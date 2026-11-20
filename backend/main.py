import os
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.staticfiles import StaticFiles
from pydantic import StringConstraints

from backend.analysis import AnalysisService, Profile
from backend.cbr import check_cbr_calendar
from backend.llm import OllamaProvider, PublicCloudTransport
from backend.market import SANDBOX_URL, MarketError, SandboxMarket, Ticker
from backend.replay import Signal, gazprom_replay
from backend.episodes import CATALOG, catalog, episode_signal, replay_episode
from backend.signal_checks import CHECKS, replay_check
from backend.mail import MailConnection, MailError, MailSettings, send_mail
from backend.telegram import (
    DeliveryStatus, ScenarioDelivery, TelegramConnection, TelegramError, TelegramSettings,
    report_text, send_message, valid_token,
)


ROOT = Path(__file__).resolve().parents[1]
MAIL_COOKIE = "ai_navigator_mail"
TELEGRAM_COOKIE = "ai_navigator_telegram"


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(ROOT / ".env")
    app.state.telegram = {}
    app.state.mail = {}
    async with (
        httpx.AsyncClient(base_url=SANDBOX_URL, timeout=8) as client,
        httpx.AsyncClient(transport=PublicCloudTransport(), trust_env=False) as cloud_client,
    ):
        app.state.market = SandboxMarket(client, os.getenv("TBANK_TOKEN", "").strip())
        app.state.analysis = AnalysisService(
            OllamaProvider(client), {name: partial(replay_check, name) for name in CHECKS}, cloud_client=cloud_client,
            cbr_check=partial(check_cbr_calendar, client),
        )
        try:
            yield
        finally:
            await app.state.analysis.shutdown()


app = FastAPI(title="AI Штурман", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    if request.url.path == "/api/studio/mail/test":
        return JSONResponse(status_code=422, content={"detail": "Проверьте SMTP-сервер, порт, логин, пароль и адреса почты."})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(MarketError)
async def handle_market_error(_request: Request, exc: MarketError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/api/quotes")
async def get_quotes(request: Request):
    return await request.app.state.market.quotes()


@app.get("/api/candles/{ticker}")
async def get_candles(request: Request, ticker: Ticker, interval: Literal["1h", "1d"] = "1h"):
    return await request.app.state.market.candles(ticker, interval)


@app.get("/api/replay/gazprom")
def get_gazprom_replay():
    return gazprom_replay()


@app.get("/api/replay/episodes")
def get_replay_catalog():
    return catalog()


@app.get("/api/replay/episodes/{episode_id}")
def get_replay_episode(episode_id: str):
    if episode_id not in CATALOG:
        raise HTTPException(status_code=404, detail="Исторический эпизод не найден.")
    return replay_episode(episode_id)


@app.get("/api/analysis/config")
async def analysis_config(request: Request):
    return request.app.state.analysis.config()


class AnalysisRequest(Profile):
    telegram: ScenarioDelivery | None = None
    mail: ScenarioDelivery | None = None


@app.post("/api/analysis/{event_id}")
async def start_analysis(request: Request, event_id: str, profile: AnalysisRequest, background: BackgroundTasks,
                         authorization: Annotated[str, Header()] = ""):
    signal = episode_signal(event_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="Историческое событие не найдено.")
    try:
        scheme, _, key = authorization.partition(" ")
        job = request.app.state.analysis.start(signal, profile, key.strip() if scheme.lower() == "bearer" else "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if (scenario := profile.telegram) and (profile.workflow is None or "report" in profile.workflow.actions):
        connection_id = request.cookies.get(TELEGRAM_COOKIE)
        connection = request.app.state.telegram.get(connection_id)
        if connection and scenario.key not in connection.deliveries:
            connection.deliveries[scenario.key] = "pending"
            background.add_task(deliver_analysis, request.app.state.analysis, request.app.state.telegram,
                                connection_id, connection, scenario, signal, job["id"])
        job = {**job, "telegram": delivery_status(connection, scenario.key)}
    if (scenario := profile.mail) and (profile.workflow is None or "report" in profile.workflow.actions):
        connection_id = request.cookies.get(MAIL_COOKIE)
        connection = request.app.state.mail.get(connection_id)
        if connection and scenario.key not in connection.deliveries:
            connection.deliveries[scenario.key] = "pending"
            background.add_task(deliver_mail_analysis, request.app.state.analysis, request.app.state.mail,
                                connection_id, connection, scenario, signal, job["id"])
        job = {**job, "mail": delivery_status(connection, scenario.key)}
    return JSONResponse(job, status_code=200 if job["status"] == "done" else 202)


@app.get("/api/analysis/jobs/{job_id}")
async def analysis_job(request: Request, job_id: str, run_id: UUID | None = None,
                       scenario_id: Annotated[str, StringConstraints(max_length=128)] | None = None,
                       channel: Literal["telegram", "mail"] = "telegram"):
    job = request.app.state.analysis.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Разбор не найден.")
    if run_id and scenario_id:
        connections = request.app.state.mail if channel == "mail" else request.app.state.telegram
        cookie = MAIL_COOKIE if channel == "mail" else TELEGRAM_COOKIE
        connection = connections.get(request.cookies.get(cookie))
        job = {**job, channel: delivery_status(connection, (run_id, scenario_id))}
    return JSONResponse(job, headers={"Cache-Control": "no-store"})


def delivery_status(connection: TelegramConnection | MailConnection | None, key: tuple[UUID, str]) -> DeliveryStatus:
    return connection.deliveries.get(key, "unconnected") if connection else "unconnected"


async def deliver_analysis(analysis: AnalysisService, connections: dict, connection_id: str,
                           connection: TelegramConnection, scenario: ScenarioDelivery, signal: Signal, job_id: str):
    try:
        result = await analysis.wait(job_id)
        if connections.get(connection_id) is not connection:
            return
        await send_message(connection.settings, report_text(signal, scenario, result))
    except TelegramError:
        connection.deliveries[scenario.key] = "failed"
    else:
        connection.deliveries[scenario.key] = "sent"


@app.get("/api/studio/telegram")
async def telegram_connection(request: Request):
    connection = request.app.state.telegram.get(request.cookies.get(TELEGRAM_COOKIE))
    return JSONResponse({"chat_id": connection.settings.chat_id if connection else None},
                        headers={"Cache-Control": "no-store"})


@app.delete("/api/studio/telegram", status_code=204)
async def disconnect_telegram(request: Request, response: Response):
    request.app.state.telegram.pop(request.cookies.get(TELEGRAM_COOKIE), None)
    response.delete_cookie(TELEGRAM_COOKIE)


@app.post("/api/studio/telegram/test")
async def test_telegram(request: Request, response: Response, settings: TelegramSettings):
    if not valid_token(settings):
        raise HTTPException(status_code=422, detail="Проверьте формат токена бота.")
    try:
        await send_message(settings, "AI Штурман · тест подключения Agent Studio")
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    connections = request.app.state.telegram
    connections.pop(request.cookies.get(TELEGRAM_COOKIE), None)
    connection_id = uuid4().hex
    connections[connection_id] = TelegramConnection(settings)
    response.set_cookie(TELEGRAM_COOKIE, connection_id, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https")
    return {"ok": True}


async def deliver_mail_analysis(analysis: AnalysisService, connections: dict, connection_id: str,
                                connection: MailConnection, scenario: ScenarioDelivery, signal: Signal, job_id: str):
    try:
        result = await analysis.wait(job_id)
        if connections.get(connection_id) is not connection:
            return
        await send_mail(connection.settings, f"Отчёт · {scenario.name}",
                        report_text(signal, scenario, result, truncate=False))
    except MailError:
        connection.deliveries[scenario.key] = "failed"
    else:
        connection.deliveries[scenario.key] = "sent"


@app.get("/api/studio/mail")
async def mail_connection(request: Request):
    connection = request.app.state.mail.get(request.cookies.get(MAIL_COOKIE))
    settings = connection.settings.model_dump(exclude={"password"}) if connection else None
    return JSONResponse({"settings": settings}, headers={"Cache-Control": "no-store"})


@app.delete("/api/studio/mail", status_code=204)
async def disconnect_mail(request: Request, response: Response):
    request.app.state.mail.pop(request.cookies.get(MAIL_COOKIE), None)
    response.delete_cookie(MAIL_COOKIE)


@app.post("/api/studio/mail/test")
async def test_mail(request: Request, response: Response, settings: MailSettings):
    try:
        await send_mail(settings, "AI Штурман · проверка почты", "Почта подключена. На этот адрес будут приходить отчёты выбранных сценариев.")
    except MailError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    connections = request.app.state.mail
    connections.pop(request.cookies.get(MAIL_COOKIE), None)
    connection_id = uuid4().hex
    connections[connection_id] = MailConnection(settings)
    response.set_cookie(MAIL_COOKIE, connection_id, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https")
    return {"ok": True}


dist = ROOT / "frontend" / "dist"
if (dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=dist, html=True), name="terminal")
