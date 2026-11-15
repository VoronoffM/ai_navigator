import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.analysis import AnalysisService, Profile
from backend.llm import OllamaProvider
from backend.market import SANDBOX_URL, MarketError, SandboxMarket, Ticker
from backend.replay import gazprom_replay, gazprom_signal
from backend.signal_checks import CHECKS, ReplayChecks


ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(ROOT / ".env")
    async with httpx.AsyncClient(base_url=SANDBOX_URL, timeout=8) as client:
        app.state.market = SandboxMarket(client, os.getenv("TBANK_TOKEN", "").strip())
        event = gazprom_replay()["event"]
        checks = ReplayChecks(event["news"] if event else None)
        app.state.analysis = AnalysisService(OllamaProvider(client), {name: getattr(checks, name) for name in CHECKS})
        try:
            yield
        finally:
            await app.state.analysis.shutdown()


app = FastAPI(title="AI Navigator", lifespan=lifespan)


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


@app.get("/api/analysis/config")
async def analysis_config(request: Request):
    return request.app.state.analysis.config()


@app.post("/api/analysis/{event_id}")
async def start_analysis(request: Request, event_id: str, profile: Profile):
    signal = gazprom_signal()
    if signal is None or signal.event_id != event_id:
        raise HTTPException(status_code=404, detail="Историческое событие не найдено.")
    try:
        job = request.app.state.analysis.start(signal, profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(job, status_code=200 if job["status"] == "done" else 202)


@app.get("/api/analysis/jobs/{job_id}")
async def analysis_job(request: Request, job_id: str):
    job = request.app.state.analysis.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Разбор не найден.")
    return JSONResponse(job, headers={"Cache-Control": "no-store"})


dist = ROOT / "frontend" / "dist"
if (dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=dist, html=True), name="terminal")
