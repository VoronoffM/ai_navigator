"""Read-only T-Invest MCP client for the four context tools."""
import itertools
import json

import httpx

MCP_URL = "https://invest-public-api.tbank.ru/mcp"
TOOLS = frozenset({
    "invest_get_news", "invest_get_candles", "invest_get_share_dividends", "invest_get_instrument_reports",
})


class InvestMCP:
    def __init__(self, client: httpx.AsyncClient, token: str, url: str = MCP_URL):
        self.client = client
        self.url = url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        }
        self.token = token
        self.ids = itertools.count(1)

    async def rpc(self, headers: dict, method: str, params: dict | None = None):
        request_id = None if method.startswith("notifications/") else next(self.ids)
        body = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            body["id"] = request_id
        if params is not None:
            body["params"] = params
        async with self.client.stream("POST", self.url, headers=headers, json=body) as response:
            response.raise_for_status()
            response_headers = response.headers
            if request_id is None:
                return None, response_headers
            if response.headers.get("content-type", "").startswith("text/event-stream"):
                lines = []
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        lines.append(line[5:].lstrip(" "))
                    if not line and lines:
                        message = json.loads("\n".join(lines))
                        lines.clear()
                        if message.get("id") == request_id:
                            break
                else:
                    raise ValueError("MCP response missing")
            else:
                message = json.loads(await response.aread())
            if message.get("id") != request_id or "error" in message:
                raise ValueError("MCP RPC failed")
            return message["result"], response_headers

    async def call(self, name: str, arguments: dict) -> dict:
        if name not in TOOLS or not self.token:
            raise ValueError("MCP tool or token unavailable")
        info, response_headers = await self.rpc(self.headers, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "ai-navigator", "version": "0.1.0"},
        })
        headers = {**self.headers, "MCP-Protocol-Version": info["protocolVersion"]}
        if session_id := response_headers.get("Mcp-Session-Id"):
            headers["Mcp-Session-Id"] = session_id
        try:
            await self.rpc(headers, "notifications/initialized")
            result, _ = await self.rpc(headers, "tools/call", {"name": name, "arguments": arguments})
        finally:
            if session_id:
                try:
                    await self.client.delete(self.url, headers=headers, timeout=1)
                except httpx.RequestError:
                    pass
        if result.get("isError"):
            raise ValueError("MCP tool returned an error")
        data = result.get("structuredContent")
        if data is None:
            entries = [item["text"] for item in result.get("content", []) if item.get("type") == "text"]
            if len(entries) != 1:
                raise ValueError("Unexpected MCP content")
            data = json.loads(entries[0])
        if not isinstance(data, dict):
            raise ValueError("Unexpected MCP result")
        return data
