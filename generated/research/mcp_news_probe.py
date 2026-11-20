import asyncio, json, os, sys
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'generated' / 'research'
load_dotenv(ROOT / '.env')
TOKEN = os.getenv('TBANK_TOKEN', '').strip()
URLS = {'sandbox': 'https://sandbox-invest-public-api.tbank.ru/mcp', 'production': 'https://invest-public-api.tbank.ru/mcp'}

def safe(value):
    text = json.dumps(value, ensure_ascii=False)
    if TOKEN:
        text = text.replace(TOKEN, '[redacted]')
    return json.loads(text)

class Session:
    def __init__(self, environment):
        self.url = URLS[environment]
        self.headers = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/json, text/event-stream'}
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(35, connect=15), follow_redirects=False)
        self.i = 0
    async def rpc(self, method, params=None):
        self.i += 1
        rid = self.i
        body = {'jsonrpc':'2.0','method':method}
        if not method.startswith('notifications/'):
            body['id'] = rid
        if params is not None:
            body['params'] = params
        async with self.client.stream('POST', self.url, headers=self.headers, json=body) as response:
            response.raise_for_status()
            if sid := response.headers.get('Mcp-Session-Id'):
                self.headers['Mcp-Session-Id'] = sid
            if 'id' not in body:
                await response.aread()
                return None
            if response.headers.get('content-type','').startswith('text/event-stream'):
                lines=[]
                async for line in response.aiter_lines():
                    if line.startswith('data:'):
                        lines.append(line[5:].lstrip())
                    elif not line and lines:
                        msg=json.loads('\n'.join(lines)); lines=[]
                        if msg.get('id')==rid:
                            return msg
                if lines:
                    msg=json.loads('\n'.join(lines))
                    if msg.get('id')==rid:
                        return msg
                raise ValueError('No matching MCP response')
            return json.loads(await response.aread())
    async def start(self):
        message = await self.rpc('initialize', {'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'ai-navigator-news-audit','version':'1.0'}})
        if 'error' in message:
            raise ValueError('Initialize RPC failed')
        self.headers['MCP-Protocol-Version'] = message['result']['protocolVersion']
        await self.rpc('notifications/initialized')
        return message['result'].get('serverInfo',{})
    async def close(self):
        if 'Mcp-Session-Id' in self.headers:
            try:
                await self.client.delete(self.url,headers=self.headers,timeout=4)
            except httpx.HTTPError:
                pass
        await self.client.aclose()

async def discover(environment):
    session=Session(environment)
    try:
        info=await session.start()
        result=await session.rpc('tools/list',{})
        tools=result.get('result',{}).get('tools',[])
        selected=[tool for tool in tools if 'news' in (tool['name']+' '+tool.get('description','')).lower() or 'новост' in tool.get('description','').lower()]
        report=safe({'environment':environment,'serverInfo':info,'toolCount':len(tools),'newsTools':selected,'error':result.get('error')})
        (OUT/f'mcp-news-discovery-{environment}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False),flush=True)
    except Exception as exc:
        report=safe({'environment':environment,'errorType':type(exc).__name__,'status':exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None,'message':str(exc)[:300]})
        (OUT/f'mcp-news-discovery-{environment}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False),flush=True)
    finally:
        await session.close()

if __name__=='__main__':
    if not TOKEN:
        print('TBANK_TOKEN отсутствует; запрос не отправлен.')
        raise SystemExit(2)
    asyncio.run(discover(sys.argv[1] if len(sys.argv)>1 else 'sandbox'))
