#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, warnings
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
    # FUSSBALL.DE often exposes crest URLs next to team links. Preserve them per fixture.
    logo_map={}
    for a in soup.find_all('a'):
        name=' '.join(a.get_text(' ',strip=True).split())
        if not name: continue
        container=a.parent
        img=(container.find('img') if container else None) or a.find('img')
        if img:
            src=img.get('data-src') or img.get('src') or ''
            if src.startswith('//'): src='https:'+src
            if src.startswith('/'): src='https://www.fussball.de'+src
            if src.startswith('http'): logo_map[name]=src
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
        prefix='u19' if 'U19' in team else ('u23' if 'U23' in team else 'u21')
        out.append({'id':prefix+'-'+mid,'date':dt.strftime('%Y-%m-%d'),'time':time,'home':home,'away':away,'competition':comp+' 2026/27','result':None,'location':'','source_url':source_url,'match_number':mid,'home_logo':logo_map.get(home,''),'away_logo':logo_map.get(away,'')})
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

def venue_record_for_game(game, venues):
    venue=venues.get(game.get('home',''), {})
    return venue if isinstance(venue, dict) else {}

def parse_score(value):
    m = re.match(r'^\s*(\d+)\s*:\s*(\d+)\s*$', str(value or ''))
    return (int(m.group(1)), int(m.group(2))) if m else None


def load_clubs():
    path = DATA / 'clubs.json'
    return load_json(path) if path.exists() else {}

def load_club_aliases():
    path = DATA / 'club-aliases.json'
    return load_json(path) if path.exists() else {}

def canonical_club_name(team):
    name=' '.join(str(team or '').replace('\u200b','').split())
    aliases=load_club_aliases()
    seen=set()
    while name in aliases and name not in seen:
        seen.add(name); name=aliases[name]
    return name

def maps_url(location):
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(location)}" if location else ''

def weather_search_url(location, date):
    query = f"Wetter {location} {date}" if location else f"Wetter {date}"
    return f"https://www.google.com/search?q={quote_plus(query)}"

def youtube_search_url(game):
    query = f"{game.get('home','')} {game.get('away','')} OSTSPORT.TV"
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"

def geocode_location(location, venue=None):
    """Resolve coordinates with deterministic venue coordinates first.

    Falls back from the complete address to progressively simpler queries and
    emits a workflow warning instead of failing silently.
    """
    if isinstance(venue, dict) and venue.get('latitude') is not None and venue.get('longitude') is not None:
        return float(venue['latitude']), float(venue['longitude'])
    if not location:
        return None
    candidates=[location]
    parts=[x.strip() for x in re.split(r',', location) if x.strip()]
    if len(parts)>1:
        candidates.append(', '.join(parts[-2:]))
        candidates.append(parts[-1])
    candidates += [re.sub(r'\([^)]*\)', '', location).strip()]
    seen=set()
    for query in candidates:
        if not query or query in seen: continue
        seen.add(query)
        try:
            r=requests.get('https://geocoding-api.open-meteo.com/v1/search', params={
                'name': query, 'count': 5, 'language': 'de', 'format': 'json', 'countryCode':'DE'
            }, headers={'User-Agent':UA}, timeout=20)
            r.raise_for_status()
            results=r.json().get('results') or []
            if results:
                best=results[0]
                return float(best['latitude']), float(best['longitude'])
        except Exception as exc:
            warnings.warn(f'Geocoding fehlgeschlagen fuer {query}: {exc}')
    warnings.warn(f'Keine Koordinaten gefunden fuer: {location}')
    return None

def weather_for_game(game, location, venue=None):
    if os.environ.get('RSV_OFFLINE') == '1':
        return None
    """Hourly forecast at kickoff; supports Open-Meteo's forecast window."""
    try:
        event_dt=datetime.fromisoformat(game['date']+'T'+(game.get('time') or '14:00')).replace(tzinfo=TZ)
        now=datetime.now(TZ)
        if not (now - timedelta(hours=4) <= event_dt <= now + timedelta(days=16)):
            return None
        coords=geocode_location(location, venue)
        if not coords:
            return None
        lat,lon=coords
        r=requests.get('https://api.open-meteo.com/v1/forecast', params={
            'latitude':lat, 'longitude':lon, 'timezone':'Europe/Berlin',
            'start_date':game['date'], 'end_date':game['date'],
            'hourly':'weather_code,temperature_2m,precipitation_probability,wind_speed_10m',
            'forecast_days':16
        }, headers={'User-Agent':UA}, timeout=20)
        r.raise_for_status()
        h=r.json().get('hourly') or {}
        times=h.get('time') or []
        if not times: return None
        target=event_dt.replace(tzinfo=None)
        idx=min(range(len(times)), key=lambda i: abs(datetime.fromisoformat(times[i])-target))
        code=int((h.get('weather_code') or [3])[idx])
        return {
            'summary': WEATHER_CODES.get(code, 'Wetterlage unbekannt'),
            'temperature': (h.get('temperature_2m') or [None])[idx],
            'rain': (h.get('precipitation_probability') or [None])[idx],
            'wind': (h.get('wind_speed_10m') or [None])[idx],
            'forecast_time': times[idx],
            'latitude': lat, 'longitude': lon
        }
    except Exception as exc:
        warnings.warn(f'Wetterabfrage fehlgeschlagen fuer {game.get("home")} - {game.get("away")}: {exc}')
        return None

def club_logo_url(team, clubs):
    canonical=canonical_club_name(team)
    info=clubs.get(canonical) or clubs.get(team) or {}
    if info.get('logo_url'):
        return str(info.get('logo_url')).strip()
    # Last-resort parent-club lookup for youth/reserve suffixes.
    parent=re.sub(r'\s+(?:U19|U21|U23|I|II|III|1)$','',canonical).strip()
    info=clubs.get(parent) or {}
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
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//RSV Eintracht Kalender//DE','CALSCALE:GREGORIAN','METHOD:PUBLISH',f"X-WR-CALNAME:{esc(meta['calendar_name'])}",'X-PUBLISHED-TTL:PT6H']
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

        if not g.get('result') and weather_link:
            desc.extend(['', f"🌦️ Wetter am Spielort öffnen: {weather_link}"])

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
            f"DTSTART:{start.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
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
    """Create the JSON used by the results, upcoming matches and table view."""
    payload={'generated_at': datetime.now(TZ).isoformat(), 'teams':{}, 'tables': load_json(DATA/'tables.json') if (DATA/'tables.json').exists() else {}, 'club_websites': {name: info.get('website','') for name, info in load_clubs().items() if isinstance(info, dict) and info.get('website')}}
    venues = load_venues()
    clubs = load_clubs()
    today = datetime.now(TZ).date()

    for key, meta, games in team_configs:
        enriched=enrich_team_stats(meta, assign_matchdays(games))
        completed=[]
        future=[]
        fixtures=[]
        team_name=meta.get('team_name','')

        for g in enriched:
            comp=competition_label(g.get('competition',''))
            is_non_league=any(x in comp.lower() for x in ('pokal','freundschaft','testspiel'))
            location=venue_for_game(g, venues)
            # Alle Wettbewerbe gehören in die vollständige Terminliste.
            fixtures.append({
                    'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                    'competition':comp, 'home':g.get('home'), 'away':g.get('away'),
                    'home_logo':g.get('home_logo') or club_logo_url(g.get('home',''), clubs), 'away_logo':g.get('away_logo') or club_logo_url(g.get('away',''), clubs),
                    'result':g.get('result') or ''
            })

            if g.get('result'):
                completed.append({
                    'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                    'competition':comp, 'home':g.get('home'), 'away':g.get('away'),
                    'home_logo':g.get('home_logo') or club_logo_url(g.get('home',''), clubs), 'away_logo':g.get('away_logo') or club_logo_url(g.get('away',''), clubs),
                    'result':g.get('result'), 'halftime_result':g.get('halftime_result') or g.get('halftime') or '', 'scorers':g.get('scorers') or [],
                    'attendance':g.get('attendance'), 'referee':g.get('referee'),
                    'location':location,
                    'maps_url':maps_url(location),
                    'weather_url':weather_search_url(location, g.get('date','')),
                    'youtube_url':g.get('youtube_url') or (youtube_search_url(g) if key=='regionalliga' else ''),
                    'report_url':g.get('report_url') or '', 'points':g.get('points'),
                    'table_position':g.get('table_position')
                })
                continue

            try:
                event_date=datetime.fromisoformat(g.get('date','')).date()
            except Exception:
                continue
            if event_date < today:
                continue

            forecast=None  # Version 2.1: Wetter wird nur noch extern verlinkt.
            future.append({
                'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                'competition':comp, 'home':g.get('home'), 'away':g.get('away'),
                'home_logo':g.get('home_logo') or club_logo_url(g.get('home',''), clubs), 'away_logo':g.get('away_logo') or club_logo_url(g.get('away',''), clubs),
                'location':location, 'maps_url':maps_url(location),
                'weather':None, 'weather_url':weather_search_url(location, g.get('date','')),
                'is_home':g.get('home') == team_name
            })

        completed.sort(key=lambda x: (x.get('date') or '', x.get('time') or '00:00'))
        fixtures.sort(key=lambda x: (x.get('date') or '', x.get('time') or '00:00'))
        future.sort(key=lambda x: (x.get('date') or '', x.get('time') or '00:00'))
        next_game=future[0] if future else None
        next_home=None
        if next_game and not next_game.get('is_home'):
            next_home=next((g for g in future[1:] if g.get('is_home')), None)

        payload['teams'][key]={
            'name':meta.get('calendar_name',''),
            'team_name':team_name,
            'competition':competition_label(meta.get('games',[{}])[0].get('competition','')) if meta.get('games') else '',
            'matches':completed,
            'fixtures':fixtures,
            'next_game':next_game,
            'next_home':next_home
        }
    # U21/U23: show a useful zero table before the association publishes standings.
    for key, meta, games in team_configs:
        if key in payload['tables'] and payload['tables'][key].get('rows'):
            continue
        league_games=[g for g in games if not any(w in competition_label(g.get('competition','')).lower() for w in ('pokal','freundschaft','testspiel'))]
        teams=sorted({str(g.get('home','')).strip() for g in league_games}|{str(g.get('away','')).strip() for g in league_games})
        teams=[t for t in teams if t]
        payload['tables'][key]={
            'competition': competition_label(league_games[0].get('competition','')) if league_games else '',
            'updated_at':'Saisonstart – alphabetisch, bis die offizielle Tabelle vorliegt',
            'rows':[{'position':i,'team':t,'played':0,'wins':0,'draws':0,'losses':0,'goals':'0:0','diff':'0','points':0,'logo_url':club_logo_url(t, clubs)} for i,t in enumerate(teams,1)]
        }

    for table in payload.get('tables', {}).values():
        for row in table.get('rows', []):
            row['logo_url'] = club_logo_url(row.get('team', ''), clubs)
    (DOCS/'site-data.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def process(key,offline=False):
    path=DATA/f'{key}.json'; meta=load_json(path); games=meta['games']; remote=[]; err=None
    if not offline:
        try:
            urls=meta.get('source_urls') or [meta.get('source_url','')]
            parsed=[]
            source_errors=[]
            for url in [u for u in urls if u]:
                try:
                    html=fetch(url)
                    parsed += parse_dfb(html,meta['team_name']) if 'datencenter.dfb.de' in url else parse_fussball(html,meta['team_name'],url)
                except Exception as source_exc:
                    source_errors.append(f'{url}: {source_exc}')
            remote=dedupe(parsed)
            if len(remote)<meta.get('minimum_games',0):
                raise RuntimeError(f'nur {len(remote)} Spiele erkannt; Mindestwert {meta.get("minimum_games")}; '+ ' | '.join(source_errors))
        except Exception as e: err=str(e); remote=[]
    merged=merge(games,remote)
    merged=apply_overrides(key,merged,load_json(DATA/'overrides.json'))
    if not merged and meta.get('minimum_games',0)>0: raise RuntimeError(f'{key}: keine Basisdaten vorhanden')
    # Persist only when remote passed validation; baseline remains source of truth.
    if remote:
        meta['games']=merged; save_json(path,meta)
    DOCS.mkdir(exist_ok=True)
    out_names={'regionalliga':'rsv-regionalliga.ics','u23':'rsv-u23.ics','u21':'rsv-u21.ics','u19':'rsv-u19.ics'}
    out=DOCS/out_names[key]
    out.write_text(make_ics(meta,merged),encoding='utf-8',newline='')
    print(f'{key}: {len(merged)} Termine erzeugt'+(f' (Online-Update übersprungen: {err})' if err else ''))
    return err is None or bool(merged)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); args=ap.parse_args()
    ok=True; configs=[]
    for key in ('regionalliga','u23','u21','u19'):
        try:
            ok=process(key,args.offline) and ok
            meta=load_json(DATA/f'{key}.json')
            games=apply_overrides(key,meta.get('games',[]),load_json(DATA/'overrides.json'))
            configs.append((key,meta,games))
        except Exception as e:
            print(f'{key}: FEHLER: {e}',file=sys.stderr); ok=False
    build_site_data(configs)
    required=('rsv-regionalliga.ics','rsv-u23.ics','rsv-u21.ics','rsv-u19.ics')
    if not ok and not all((DOCS/x).exists() for x in required): return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
