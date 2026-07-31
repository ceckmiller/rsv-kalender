#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
from urllib.parse import quote_plus
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

WEATHER_CODES = {
    0: 'klar', 1: 'überwiegend klar', 2: 'teilweise bewölkt', 3: 'bewölkt',
    45: 'Nebel', 48: 'Reifnebel', 51: 'leichter Nieselregen', 53: 'Nieselregen',
    55: 'starker Nieselregen', 56: 'leichter gefrierender Nieselregen',
    57: 'starker gefrierender Nieselregen', 61: 'leichter Regen', 63: 'Regen',
    65: 'starker Regen', 66: 'leichter gefrierender Regen', 67: 'starker gefrierender Regen',
    71: 'leichter Schneefall', 73: 'Schneefall', 75: 'starker Schneefall',
    77: 'Schneegriesel', 80: 'leichte Regenschauer', 81: 'Regenschauer',
    82: 'starke Regenschauer', 85: 'leichte Schneeschauer', 86: 'starke Schneeschauer',
    95: 'Gewitter', 96: 'Gewitter mit leichtem Hagel', 99: 'Gewitter mit starkem Hagel'
}

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

def competition_label(value):
    value = re.sub(r'\s+20\d{2}/\d{2}$', '', str(value or '')).strip()
    return value

def assign_matchdays(games):
    """Assign a matchday number separately for each league competition.

    Cup/friendly matches are deliberately not counted as league matchdays.
    An explicit matchday in JSON always wins.
    """
    counters = {}
    result = []
    for original in sorted(games, key=lambda x: (x['date'], x.get('time', '00:00'))):
        g = deepcopy(original)
        comp = competition_label(g.get('competition', ''))
        is_cup = any(word in comp.lower() for word in ('pokal', 'freundschaft', 'testspiel'))
        if not is_cup:
            counters[comp] = counters.get(comp, 0) + 1
            g.setdefault('matchday', counters[comp])
        result.append(g)
    return result

def load_venues():
    path = DATA / 'venues.json'
    return load_json(path) if path.exists() else {}

def venue_for_game(game, venues):
    explicit = str(game.get('location') or '').strip()
    if explicit:
        return explicit
    venue = venues.get(game.get('home', ''), {})
    if isinstance(venue, str):
        return venue
    name = str(venue.get('stadium') or '').strip()
    address = str(venue.get('address') or '').strip()
    return ', '.join(x for x in (name, address) if x)

def parse_score(value):
    m = re.match(r'^\s*(\d+)\s*:\s*(\d+)\s*$', str(value or ''))
    return (int(m.group(1)), int(m.group(2))) if m else None


def load_clubs():
    path = DATA / 'clubs.json'
    return load_json(path) if path.exists() else {}

def maps_url(location):
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(location)}" if location else ''

def weather_search_url(location, date):
    query = f"Wetter {location} {date}" if location else f"Wetter {date}"
    return f"https://www.google.com/search?q={quote_plus(query)}"

def youtube_search_url(game):
    query = f"{game.get('home','')} {game.get('away','')} OSTSPORT.TV"
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"

def geocode_location(location):
    if not location:
        return None
    try:
        r=requests.get('https://geocoding-api.open-meteo.com/v1/search', params={
            'name': location, 'count': 1, 'language': 'de', 'format': 'json'
        }, headers={'User-Agent':UA}, timeout=20)
        r.raise_for_status()
        results=r.json().get('results') or []
        if not results:
            return None
        return float(results[0]['latitude']), float(results[0]['longitude'])
    except Exception:
        return None

def weather_for_game(game, location):
    try:
        event_date=datetime.fromisoformat(game['date']).date()
        today=datetime.now(TZ).date()
        if not (today <= event_date <= today + timedelta(days=16)):
            return None
        coords=geocode_location(location)
        if not coords:
            return None
        lat,lon=coords
        r=requests.get('https://api.open-meteo.com/v1/forecast', params={
            'latitude':lat, 'longitude':lon, 'timezone':'Europe/Berlin',
            'start_date':game['date'], 'end_date':game['date'],
            'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max'
        }, headers={'User-Agent':UA}, timeout=20)
        r.raise_for_status()
        d=r.json().get('daily') or {}
        if not d.get('time'):
            return None
        code=int(d.get('weather_code',[3])[0])
        return {
            'summary': WEATHER_CODES.get(code, 'Wetterlage unbekannt'),
            'tmax': d.get('temperature_2m_max',[None])[0],
            'tmin': d.get('temperature_2m_min',[None])[0],
            'rain': d.get('precipitation_probability_max',[None])[0],
            'wind': d.get('wind_speed_10m_max',[None])[0],
        }
    except Exception:
        return None

def club_logo_url(team, clubs):
    info=clubs.get(team) or {}
    return str(info.get('logo_url') or '').strip()


def enrich_team_stats(meta, games):
    """Add cumulative RSV points after completed league games.

    A true table position needs standings for every club. It is therefore only
    shown when the source or data/overrides.json supplies table_position.
    """
    team = meta.get('team_name', '')
    points_by_comp = {}
    enriched = []
    for original in sorted(games, key=lambda x: (x['date'], x.get('time', '00:00'))):
        g = deepcopy(original)
        comp = competition_label(g.get('competition', ''))
        is_league = not any(word in comp.lower() for word in ('pokal', 'freundschaft', 'testspiel'))
        score = parse_score(g.get('result'))
        if is_league and score and team in (g.get('home'), g.get('away')):
            home_goals, away_goals = score
            if home_goals == away_goals:
                gained = 1
            elif (g.get('home') == team and home_goals > away_goals) or (g.get('away') == team and away_goals > home_goals):
                gained = 3
            else:
                gained = 0
            points_by_comp[comp] = points_by_comp.get(comp, 0) + gained
            g.setdefault('points', points_by_comp[comp])
        enriched.append(g)
    return enriched


def make_ics(meta,games):
    now=datetime.now(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//RSV Eintracht Kalender//DE','CALSCALE:GREGORIAN','METHOD:PUBLISH',f"X-WR-CALNAME:{esc(meta['calendar_name'])}",'X-WR-TIMEZONE:Europe/Berlin','X-PUBLISHED-TTL:PT6H','REFRESH-INTERVAL;VALUE=DURATION:PT6H']
    venues = load_venues()
    clubs = load_clubs()
    is_first_team = bool(meta.get('first_team')) or 'Regionalliga' in meta.get('calendar_name','')
    games = enrich_team_stats(meta, assign_matchdays(games))
    for g in games:
        kickoff=g.get('time','14:00')
        start=datetime.fromisoformat(g['date']+'T'+kickoff).replace(tzinfo=TZ)
        end=start+timedelta(hours=2)
        comp=competition_label(g.get('competition',''))
        pairing=f"{g['home']} – {g['away']}"
        matchday=g.get('matchday')
        first_line=f"{matchday}. Spieltag" if matchday else (comp or 'Pflichtspiel')
        status_line=f"Endstand: {g['result']}" if g.get('result') else f"Anstoß: {kickoff} Uhr"
        # Keep SUMMARY on one physical/logical line for maximum Google Calendar compatibility.
        summary=' | '.join(x for x in (first_line, comp, pairing, status_line) if x)
        location=venue_for_game(g, venues)
        map_link=maps_url(location)
        weather_link=weather_search_url(location, g['date'])
        forecast=weather_for_game(g, location) if is_first_team and not g.get('result') else None
        home_logo=club_logo_url(g.get('home',''), clubs)
        away_logo=club_logo_url(g.get('away',''), clubs)

        desc=[first_line, comp, pairing, status_line, '']
        if g.get('result'):
            if g.get('table_position') not in (None, ''):
                desc.append(f"📈 Tabellenplatz: {g['table_position']}.")
            if g.get('points') not in (None, ''):
                desc.append(f"🏅 Punkte: {g['points']}")
            if g.get('scorers'):
                desc.extend(['', '⚽ Tore RSV'])
                if isinstance(g['scorers'], list):
                    desc.extend(str(x) for x in g['scorers'])
                else:
                    desc.append(str(g['scorers']))
            if g.get('referee'):
                desc.extend(['', f"👨‍⚖️ Schiedsrichter: {g['referee']}"])
            if g.get('attendance') not in (None, ''):
                desc.append(f"👥 Zuschauer: {g['attendance']}")
        if location:
            desc.extend(['', f"🏟️ Spielort: {location}"])
            if map_link:
                desc.append(f"🗺️ Google Maps: {map_link}")
        else:
            desc.extend(['', '🏟️ Spielort: noch nicht hinterlegt'])

        if is_first_team and not g.get('result'):
            if forecast:
                temp=f"{forecast['tmin']}–{forecast['tmax']} °C" if forecast['tmin'] is not None and forecast['tmax'] is not None else 'Temperatur offen'
                rain=f", Regenrisiko {forecast['rain']} %" if forecast['rain'] is not None else ''
                wind=f", Wind bis {forecast['wind']} km/h" if forecast['wind'] is not None else ''
                desc.extend(['', f"🌦️ Wetterprognose: {forecast['summary']}, {temp}{rain}{wind}"])
            else:
                desc.extend(['', '🌦️ Wetterprognose: wird automatisch ergänzt, sobald der Termin im Vorhersagezeitraum liegt'])
            desc.append(f"Wetter öffnen: {weather_link}")

        if is_first_team and g.get('result'):
            video=g.get('youtube_url') or youtube_search_url(g)
            label='OSTSPORT.TV-Beitrag' if g.get('youtube_url') else 'OSTSPORT.TV-Beitrag suchen'
            desc.extend(['', f"▶️ {label}: {video}"])

        if g.get('report_url'):
            desc.extend(['', f"📰 Spielbericht: {g['report_url']}"])
        if g.get('source_url'):
            desc.extend(['', f"Quelle: {g['source_url']}"])

        event_lines = [
            'BEGIN:VEVENT',
            f"UID:{g['id']}@rsv-kalender",
            f'DTSTAMP:{now}',
            f"DTSTART;TZID=Europe/Berlin:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID=Europe/Berlin:{end.strftime('%Y%m%dT%H%M%S')}",
            f'SUMMARY:{esc(summary)}',
            f'DESCRIPTION:{esc(chr(10).join(desc))}',
            f'LOCATION:{esc(location)}',
        ]
        # External image attachments are intentionally omitted. Google Calendar
        # can reject URL subscriptions containing remote ATTACH properties.
        event_lines += ['STATUS:CONFIRMED', 'TRANSP:OPAQUE', 'END:VEVENT']
        lines += event_lines
    lines.append('END:VCALENDAR')
    return '\r\n'.join(fold(x) for x in lines)+'\r\n'

def build_site_data(team_configs):
    """Create one compact JSON file used by the mobile results/table view."""
    payload={'teams':{}, 'tables': load_json(DATA/'tables.json') if (DATA/'tables.json').exists() else {}}
    for key, meta, games in team_configs:
        enriched=enrich_team_stats(meta, assign_matchdays(games))
        completed=[]
        for g in enriched:
            if not g.get('result'):
                continue
            comp=competition_label(g.get('competition',''))
            # The user requested completed matchdays only; cup/friendlies remain excluded here.
            if any(x in comp.lower() for x in ('pokal','freundschaft','testspiel')):
                continue
            completed.append({
                'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                'competition':comp, 'home':g.get('home'), 'away':g.get('away'),
                'result':g.get('result'), 'scorers':g.get('scorers') or [],
                'attendance':g.get('attendance'), 'referee':g.get('referee'),
                'location':venue_for_game(g, load_venues()),
                'youtube_url':g.get('youtube_url') or (youtube_search_url(g) if key=='regionalliga' else ''),
                'report_url':g.get('report_url') or '', 'points':g.get('points'),
                'table_position':g.get('table_position')
            })
        completed.sort(key=lambda x: ((x.get('matchday') or 9999), x.get('date') or ''))
        payload['teams'][key]={'name':meta.get('calendar_name',''), 'competition':competition_label(meta.get('games',[{}])[0].get('competition','')) if meta.get('games') else '', 'matches':completed}
    (DOCS/'site-data.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def process(key,offline=False):
    path=DATA/f'{key}.json'; meta=load_json(path); games=meta['games']; remote=[]; err=None
    if not offline:
        try:
            html=fetch(meta['source_url'])
            remote=parse_dfb(html,meta['team_name']) if key=='regionalliga' else (parse_fussball(html,meta['team_name'],meta['source_url']) if 'fussball.de' in meta.get('source_url','') else [])
            if len(remote)<meta.get('minimum_games',0): raise RuntimeError(f'nur {len(remote)} Spiele erkannt; Mindestwert {meta.get("minimum_games")}')
        except Exception as e: err=str(e); remote=[]
    merged=merge(games,remote)
    merged=apply_overrides(key,merged,load_json(DATA/'overrides.json'))
    if not merged and meta.get('minimum_games',0)>0: raise RuntimeError(f'{key}: keine Basisdaten vorhanden')
    # Persist only when remote passed validation; baseline remains source of truth.
    if remote:
        meta['games']=merged; save_json(path,meta)
    DOCS.mkdir(exist_ok=True)
    out_names={'regionalliga':'rsv-regionalliga.ics','u23':'rsv-u23.ics','u21':'rsv-u21.ics'}
    out=DOCS/out_names[key]
    out.write_text(make_ics(meta,merged),encoding='utf-8',newline='')
    print(f'{key}: {len(merged)} Termine erzeugt'+(f' (Online-Update übersprungen: {err})' if err else ''))
    return err is None or bool(merged)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); args=ap.parse_args()
    ok=True; configs=[]
    for key in ('regionalliga','u23','u21'):
        try:
            ok=process(key,args.offline) and ok
            meta=load_json(DATA/f'{key}.json')
            games=apply_overrides(key,meta.get('games',[]),load_json(DATA/'overrides.json'))
            configs.append((key,meta,games))
        except Exception as e:
            print(f'{key}: FEHLER: {e}',file=sys.stderr); ok=False
    build_site_data(configs)
    required=('rsv-regionalliga.ics','rsv-u23.ics','rsv-u21.ics')
    if not ok and not all((DOCS/x).exists() for x in required): return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
