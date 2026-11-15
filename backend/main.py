import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.market import SANDBOX_URL, MarketError, SandboxMarket, Ticker


ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(ROOT / ".env")
    async with httpx.AsyncClient(base_url=SANDBOX_URL, timeout=8) as client:
        app.state.market = SandboxMarket(client, os.getenv("TBANK_TOKEN", "").strip())
        yield


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


dist = ROOT / "frontend" / "dist"
if (dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=dist, html=True), name="terminal")
