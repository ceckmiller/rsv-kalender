#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; DOCS=ROOT/'docs'; STATE=ROOT/'state'
TZ=ZoneInfo('Europe/Berlin')
UA='Mozilla/5.0 (compatible; RSV-Kalender/1.0; +https://github.com/)'

DATE_RE=re.compile(r'(\d{2})\.(\d{2})\.(\d{4}).*?(\d{2}):(\d{2})')

def load_json(path):
    with open(path,encoding='utf-8') as f:return json.load(f)

def save_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with open(tmp,'w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
    tmp.replace(path)

def fetch(url):
    r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'de-DE,de;q=0.9'},timeout=30)
    r.raise_for_status()
    if len(r.text)<1000: raise RuntimeError(f'Antwort zu kurz ({len(r.text)} Zeichen)')
    return r.text

def parse_dfb(html, team):
    soup=BeautifulSoup(html,'html.parser')
    text=soup.get_text(' ',strip=True)
    # Robust fallback based on repeating date + team/result/team sequence.
    pat=re.compile(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+Uhr\s+(.+?)\s+(\d+\s*:\s*\d+|-\s*:\s*-)\s+(.+?)(?=(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s+\d{2}\.\d{2}\.\d{4}|$)')
    out=[]
    for m in pat.finditer(text):
        d,t,home,res,away=m.groups()
        # Strip navigation words if present.
        home=re.sub(r'^(?:Schema|Vergleich|Liveticker)\s+','',home).strip()
        away=re.split(r'\s+(?:Schema|Vergleich|Liveticker)\b',away)[0].strip()
        if team not in (home,away): continue
        dt=datetime.strptime(d+' '+t,'%d.%m.%Y %H:%M')
        key=hashlib.sha1(f'{dt.date()}|{home}|{away}'.encode()).hexdigest()[:12]
        out.append({'id':'rl-'+key,'date':dt.strftime('%Y-%m-%d'),'time':t,'home':home,'away':away,'competition':'Regionalliga Nordost 2026/27','result':None if '-' in res else re.sub(r'\s','',res),'location':'','source_url':''})
    return dedupe(out)

def parse_fussball(html, team, source_url):
    soup=BeautifulSoup(html,'html.parser')
    text='\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip())
    lines=text.splitlines(); out=[]
    # Find date headers, then inspect the following compact block for match number and teams.
    for i,line in enumerate(lines):
        m=re.match(r'(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s*(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})\s*Uhr\s*\|\s*(.+)',line)
        if not m: continue
        date,time,comp=m.group(2),m.group(3),m.group(4)
        block=' | '.join(lines[i+1:i+12])
        no=re.search(r'\b([678]\d{8})\b',block)
        # Team names occur around a colon. Use known team and nearby tokens.
        pos=block.find(team)
        if pos<0: continue
        before=block[:pos]; after=block[pos+len(team):]
        # Links rendered as plain text; select the nearest plausible names.
        names=[x.strip() for x in re.split(r'\s*\|\s*',block) if x.strip()]
        names=[x for x in names if x not in {':','Zum Spiel','ME','PO','FS'} and not re.fullmatch(r'\d{2}\.\d{2}\.\d{2}',x) and not re.fullmatch(r'\d{2}:\d{2}',x) and not re.fullmatch(r'\d{9}',x)]
        idx=next((j for j,x in enumerate(names) if x==team),None)
        if idx is None: continue
        home=names[idx-1] if idx>0 and ':' in names[idx-1] else None
        # Better: find colon marker in original names list.
        try:
            c=names.index(':')
            home=names[c-1]; away=names[c+1]
        except Exception:
            # Derive whether team appears before/after first colon in block.
            colon=block.find(':', max(0,pos-80))
            candidates=[x for x in names if len(x)>3 and team!=x and not x.startswith(('So,','Sa,','Fr,','Mi,','Di,','Mo,','Do,'))]
            other=candidates[-1] if candidates else 'Unbekannter Gegner'
            if colon>=0 and pos<colon: home,away=team,other
            else: home,away=other,team
        dt=datetime.strptime(date+' '+time,'%d.%m.%Y %H:%M')
        mid=no.group(1) if no else hashlib.sha1(f'{dt.date()}|{home}|{away}'.encode()).hexdigest()[:10]
        out.append({'id':'u21-'+mid,'date':dt.strftime('%Y-%m-%d'),'time':time,'home':home,'away':away,'competition':comp+' 2026/27','result':None,'location':'','source_url':source_url,'match_number':mid})
    return dedupe(out)

def dedupe(games):
    seen={};
    for g in games: seen[g['id']]=g
    return sorted(seen.values(),key=lambda x:(x['date'],x.get('time','00:00')))

def merge(base, remote):
    result={g['id']:deepcopy(g) for g in base}
    # Secondary identity lets remote IDs change without duplicating games.
    by_identity={(g['date'],g['home'],g['away']):g['id'] for g in base}
    for g in remote:
        target=g['id'] if g['id'] in result else by_identity.get((g['date'],g['home'],g['away']),g['id'])
        old=result.get(target,{})
        result[target]={**old,**{k:v for k,v in g.items() if v not in ('',None)},'id':target}
    return sorted(result.values(),key=lambda x:(x['date'],x.get('time','00:00')))

def apply_overrides(key,games,overrides):
    by={g['id']:g for g in games}
    for gid,patch in overrides.get(key,{}).items():
        if patch is None: by.pop(gid,None)
        elif gid in by: by[gid].update(patch)
        else: by[gid]={'id':gid,**patch}
    return sorted(by.values(),key=lambda x:(x['date'],x.get('time','00:00')))

def esc(s):
    return str(s or '').replace('\\','\\\\').replace('\n','\\n').replace(',','\\,').replace(';','\\;')

def fold(line):
    out=[]
    while len(line.encode('utf-8'))>73:
        cut=70
        while len(line[:cut].encode('utf-8'))>73:cut-=1
        out.append(line[:cut]); line=' '+line[cut:]
    out.append(line); return '\r\n'.join(out)

def make_ics(meta,games):
    now=datetime.now(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//RSV Eintracht Kalender//DE','CALSCALE:GREGORIAN','METHOD:PUBLISH',f"X-WR-CALNAME:{esc(meta['calendar_name'])}",'X-WR-TIMEZONE:Europe/Berlin','X-PUBLISHED-TTL:PT6H']
    team=meta['team_name']
    for g in games:
        start=datetime.fromisoformat(g['date']+'T'+g.get('time','14:00')).replace(tzinfo=TZ)
        end=start+timedelta(hours=2)
        opponent=g['away'] if g['home']==team else g['home']
        ha='Heim' if g['home']==team else 'Auswärts'
        score=f" {g['result']}" if g.get('result') else ''
        summary=f"RSV – {opponent}{score}" if ha=='Heim' else f"{opponent} – RSV{score}"
        desc=f"{ha}spiel · {g.get('competition','')}"
        if g.get('result'): desc+=f"\\nErgebnis: {g['result']}"
        if g.get('source_url'): desc+=f"\\nQuelle: {g['source_url']}"
        lines += ['BEGIN:VEVENT',f"UID:{g['id']}@rsv-kalender",f'DTSTAMP:{now}',f"DTSTART;TZID=Europe/Berlin:{start.strftime('%Y%m%dT%H%M%S')}",f"DTEND;TZID=Europe/Berlin:{end.strftime('%Y%m%dT%H%M%S')}",f'SUMMARY:{esc(summary)}',f'DESCRIPTION:{esc(desc)}',f"LOCATION:{esc(g.get('location',''))}",f"URL:{g.get('source_url','')}",'STATUS:CONFIRMED','END:VEVENT']
    lines.append('END:VCALENDAR')
    return '\r\n'.join(fold(x) for x in lines)+'\r\n'

def process(key,offline=False):
    path=DATA/f'{key}.json'; meta=load_json(path); games=meta['games']; remote=[]; err=None
    if not offline:
        try:
            html=fetch(meta['source_url'])
            remote=parse_dfb(html,meta['team_name']) if key=='regionalliga' else parse_fussball(html,meta['team_name'],meta['source_url'])
            if len(remote)<meta.get('minimum_games',1): raise RuntimeError(f'nur {len(remote)} Spiele erkannt; Mindestwert {meta.get("minimum_games")}')
        except Exception as e: err=str(e); remote=[]
    merged=merge(games,remote)
    merged=apply_overrides(key,merged,load_json(DATA/'overrides.json'))
    if not merged: raise RuntimeError(f'{key}: keine Basisdaten vorhanden')
    # Persist only when remote passed validation; baseline remains source of truth.
    if remote:
        meta['games']=merged; save_json(path,meta)
    DOCS.mkdir(exist_ok=True)
    out=DOCS/('rsv-regionalliga.ics' if key=='regionalliga' else 'rsv-u21.ics')
    out.write_text(make_ics(meta,merged),encoding='utf-8',newline='')
    print(f'{key}: {len(merged)} Termine erzeugt'+(f' (Online-Update übersprungen: {err})' if err else ''))
    return err is None or bool(merged)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); args=ap.parse_args()
    ok=True
    for key in ('regionalliga','u21'):
        try: ok=process(key,args.offline) and ok
        except Exception as e: print(f'{key}: FEHLER: {e}',file=sys.stderr); ok=False
    # Important: temporary source failures do not fail the workflow when valid baseline ICS files exist.
    if not ok and not all((DOCS/x).exists() for x in ('rsv-regionalliga.ics','rsv-u21.ics')): return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
