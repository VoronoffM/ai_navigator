import asyncio, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from mcp_news_probe import Session, OUT, TOKEN, safe

MOSCOW=timezone(timedelta(hours=3))
TARGET=datetime(2025,5,22,tzinfo=MOSCOW).date()

def decode(result):
    if 'error' in result:
        raise ValueError('RPC error: '+json.dumps(safe(result['error']),ensure_ascii=False))
    value=result['result']
    if value.get('isError'):
        texts=[item.get('text','')[:500] for item in value.get('content',[]) if item.get('type')=='text']
        raise ValueError('Tool error: '+str(safe(texts)))
    if 'structuredContent' in value:
        return value['structuredContent']
    texts=[item['text'] for item in value.get('content',[]) if item.get('type')=='text']
    if len(texts)!=1:
        raise ValueError('Unexpected content blocks')
    return json.loads(texts[0])

def stamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(MOSCOW)
    except (AttributeError,ValueError):
        return None

async def scan(environment,instrument,max_pages,limit):
    session=Session(environment)
    report={'environment':environment,'instrument':instrument or 'ALL','checkedAt':datetime.now(timezone.utc).isoformat(),'limit':limit,'pages':[], 'targetDateMoscow':str(TARGET),'targetHits':[],'samples':[],'gazpItems':[],'textDateMatches':[],'archiveExhausted':False,'itemsSeen':0,'duplicateIds':0,'invalidTimestamps':0}
    cursor=None
    seen=set(); cursors=set(); all_dates=[]
    try:
        report['serverInfo']=await session.start()
        for page in range(1,max_pages+1):
            args={'limit':limit}
            if instrument:
                args['instrumentId']=instrument
            if cursor:
                args['cursor']=cursor
            data=decode(await session.rpc('tools/call',{'name':'invest_get_news','arguments':args}))
            rows=data.get('items',[])
            if page == 1:
                report['samples'] = [{key: row.get(key) for key in ('id','ts','title','source','instrumentId')} for row in rows[:3]]
            dates=[]
            for row in rows:
                rid=row.get('id')
                refs=row.get('instrumentId',[])
                is_gazp=any((entry.get('instrument') or {}).get('ticker')=='GAZP' for entry in refs if isinstance(entry,dict))
                blob=' '.join(str(row.get(key) or '') for key in ('title','summary','content'))
                is_gazp=is_gazp or ('газпром' in blob.lower())
                small={key:row.get(key) for key in ('id','ts','title','source')}
                if is_gazp:
                    report['gazpItems'].append(safe(small))
                compact=blob.lower()
                if any(marker in compact for marker in ('2025-05-22','22.05.2025','22 мая 2025','1027187')):
                    report['textDateMatches'].append(safe({**small,'mentionsGazprom':is_gazp}))
                if rid in seen:
                    report['duplicateIds']+=1
                seen.add(rid)
                ts=stamp(row.get('ts'))
                if ts:
                    dates.append(ts); all_dates.append(ts)
                    if ts.date()==TARGET:
                        hit={key:row.get(key) for key in ('id','ts','title','source','instrumentId')}
                        # Store a short synopsis, never full article text.
                        hit['summary']=str(row.get('summary') or '')[:450]
                        report['targetHits'].append(safe(hit))
                else:
                    report['invalidTimestamps']+=1
            report['itemsSeen']+=len(rows)
            info={'page':page,'count':len(rows),'newestMoscow':max(dates).isoformat() if dates else None,'oldestMoscow':min(dates).isoformat() if dates else None,'hasNext':data.get('hasNext'),'hasCursor':bool(data.get('nextCursor'))}
            report['pages'].append(info)
            print(json.dumps(safe({'environment':environment,'instrument':instrument or 'ALL',**info,'targetHits':len(report['targetHits']),'gazpItems':len(report['gazpItems']),'textDateMatches':len(report['textDateMatches'])}),ensure_ascii=False),flush=True)
            cursor=data.get('nextCursor')
            if data.get('hasNext') is False:
                report['archiveExhausted']=True; report['stopReason']='hasNext=false'; break
            if not cursor:
                report['stopReason']='missing_cursor'; break
            if cursor in cursors:
                report['stopReason']='repeated_cursor'; break
            cursors.add(cursor)
        else:
            report['stopReason']='page_budget_reached'
    except Exception as exc:
        report['error']=safe({'type':type(exc).__name__,'message':str(exc)[:700]})
        print(json.dumps(report['error'],ensure_ascii=False),flush=True)
    finally:
        if all_dates:
            report['newestMoscow']=max(all_dates).isoformat(); report['oldestMoscow']=min(all_dates).isoformat()
        report=safe(report)
        path=OUT/f'mcp-news-scan-{environment}-{instrument or "all"}.json'
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        await session.close()
        print(json.dumps({key:value for key,value in report.items() if key not in ('pages','targetHits','gazpItems','textDateMatches')},ensure_ascii=False),flush=True)
        if report['targetHits']:
            print(json.dumps({'targetHits':report['targetHits']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    if not TOKEN:
        raise SystemExit('No TBANK_TOKEN')
    asyncio.run(scan(sys.argv[1], '' if sys.argv[2]=='ALL' else sys.argv[2], int(sys.argv[3]) if len(sys.argv)>3 else 1,int(sys.argv[4]) if len(sys.argv)>4 else 1000))
