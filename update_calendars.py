#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os, re, sys, warnings
from urllib.parse import quote_plus, urljoin
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

TICKET_OVERVIEW_URL='https://rsv-eintracht.vereinsticket.de/herren/'

def normalize_match_name(value):
    name=canonical_club_name(value)
    name=re.sub(r'\bRSV Eintracht(?: 1949)?(?: I|1\. Herren|Herren)?\b','RSV Eintracht 1949',name,flags=re.I)
    name=re.sub(r'\s+',' ',name).strip().casefold()
    return name

def load_saved_ticket_events():
    path=DATA/'tickets.json'
    if not path.exists():
        return []
    raw=load_json(path)
    events=raw.get('events',[]) if isinstance(raw,dict) else raw
    return [{**x,'opponent_key':normalize_match_name(x.get('opponent',''))} for x in events if x.get('url')]

def fetch_ticket_events():
    """Read and cache event-specific links from the Herren ticket shop.

    The overview page is treated as the source of truth. Every newly published
    event detail link is discovered automatically, parsed, and matched to the
    corresponding home fixture. Existing saved mappings remain available if
    the shop is temporarily unreachable.
    """
    saved=load_saved_ticket_events()
    if os.environ.get('RSV_OFFLINE') == '1':
        return saved
    try:
        html=fetch(TICKET_OVERVIEW_URL)
        soup=BeautifulSoup(html,'html.parser')
        candidates=[]
        seen=set()
        for a in soup.find_all('a', href=True):
            href=urljoin(TICKET_OVERVIEW_URL,a.get('href','')).split('#',1)[0]
            # Vereinsticket currently uses numeric event pages, but accepting a
            # single non-empty path segment also keeps this future-proof if the
            # provider switches to slugs.
            if not re.fullmatch(r'https://rsv-eintracht\.vereinsticket\.de/herren/[^/?#]+/?',href):
                continue
            if href.rstrip('/') == TICKET_OVERVIEW_URL.rstrip('/') or href in seen:
                continue
            seen.add(href)
            context=a.find_parent(['article','li','section','div']) or a.parent
            candidates.append((href, ' '.join(context.get_text(' ',strip=True).split()) if context else ''))

        events=[]
        months={'januar':1,'februar':2,'märz':3,'april':4,'mai':5,'juni':6,'juli':7,'august':8,'september':9,'oktober':10,'november':11,'dezember':12}
        for href, overview_text in candidates:
            detail=BeautifulSoup(fetch(href),'html.parser')
            headings=[' '.join(h.get_text(' ',strip=True).split()) for h in detail.find_all(['h1','h2','h3'])]
            title=next((x for x in headings if re.search(r'RSV Eintracht(?: 1949)?\s*[-–:]',x,re.I)), '')
            if not title:
                title=next((x for x in headings if 'RSV Eintracht' in x), '')
            opponent=re.sub(r'^.*?RSV Eintracht(?: 1949)?\s*[-–:]\s*','',title,flags=re.I).strip()
            text=' '.join(detail.get_text(' ',strip=True).split())
            dm=re.search(r'(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(20\d{2})',text,re.I)
            if not dm:
                dm=re.search(r'(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(20\d{2})',overview_text,re.I)
            date=''
            if dm:
                date=f"{int(dm.group(3)):04d}-{months[dm.group(2).casefold()]:02d}-{int(dm.group(1)):02d}"
            if opponent:
                events.append({'url':href,'date':date,'opponent':opponent,'opponent_key':normalize_match_name(opponent)})
        if events:
            events.sort(key=lambda x:(x.get('date',''),x.get('opponent','')))
            save_json(DATA/'tickets.json',{'overview_url':TICKET_OVERVIEW_URL,'updated_at':datetime.now(TZ).isoformat(),'events':[{k:v for k,v in x.items() if k!='opponent_key'} for x in events]})
            print(f'Ticketshop: {len(events)} Detailseiten automatisch erkannt')
            return events
        warnings.warn('Ticketshop enthielt keine erkennbaren Detailseiten; gespeicherte Zuordnungen werden verwendet.')
    except Exception as exc:
        warnings.warn(f'Ticketshop konnte nicht gelesen werden: {exc}; gespeicherte Zuordnungen werden verwendet.')
    return saved

def ticket_url_for_game(game, team_name, ticket_events):
    if game.get('home') != team_name:
        return ''
    opponent_key=normalize_match_name(game.get('away',''))
    date=game.get('date','')
    for event in ticket_events:
        if event.get('date') == date and event.get('opponent_key') == opponent_key:
            return event['url']
    # Name match is a safe fallback if a fixture date was moved in one source
    # before the other source was updated.
    matches=[event for event in ticket_events if event.get('opponent_key') == opponent_key]
    if len(matches)==1:
        return matches[0]['url']
    return TICKET_OVERVIEW_URL

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

def extract_location_from_text(text):
    # Official print pages use varying labels. Keep only explicit venue/address
    # text from the match block; never infer a venue from the home club here.
    compact=' | '.join(x.strip() for x in str(text).split('|') if x.strip())
    patterns=(
        r'(?:Spielst(?:ä|ae)tte|Spielort|Sportplatz|Austragungsort|Platzanlage)\s*:?\s*([^|]{4,180})',
        r'(?:Stadion|Sportpark|Sportanlage|Sportplatz|Arena|Kunstrasenplatz|Rasenplatz)\s+([^|]{0,150})',
    )
    for pat in patterns:
        m=re.search(pat,compact,re.I)
        if m:
            value=m.group(0 if pat.startswith('(?:Stadion') else 1).strip(' :-|')
            value=re.split(r'\s+(?:Schiedsrichter|Zuschauer|Zum Spiel|ME|PO|FS)\b',value,1,flags=re.I)[0].strip()
            if 4 <= len(value) <= 200:
                return value
    # Address-only fallback, but only when a street suffix and postal code occur
    # in the same official match block.
    m=re.search(r'([^|]{2,80}(?:straße|strasse|weg|allee|damm|ring|platz)\s+\d+[a-zA-Z]?(?:[–-]\d+)?\s*,?\s*\d{5}\s+[^|]{2,60})',compact,re.I)
    return m.group(1).strip(' :-|') if m else ''

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
        next_i=next((j for j in range(i+1,len(lines)) if re.match(r'(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s*\d{2}\.\d{2}\.\d{4}',lines[j])), min(len(lines),i+45))
        block=' | '.join(lines[i+1:next_i])
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
        out.append({'id':prefix+'-'+mid,'date':dt.strftime('%Y-%m-%d'),'time':time,'home':home,'away':away,'competition':comp+' 2026/27','result':None,'location':extract_location_from_text(block),'source_url':source_url,'match_number':mid,'home_logo':logo_map.get(home,''),'away_logo':logo_map.get(away,'')})
    # Fallback for the compact text representation used by FUSSBALL.DE
    # on team and print pages, e.g.:
    #   So, 30.08.26 | 14:00 Kreisliga ME | 610088005 Team A : Team B Zum Spiel
    # The older parser above only recognizes the long date heading and can
    # therefore see just the initially rendered subset of fixtures.
    flat=' '.join(soup.get_text(' ',strip=True).split())
    compact_re=re.compile(
        r'(?P<day>Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*'
        r'(?P<date>\d{2}\.\d{2}\.(?:\d{2}|\d{4}))\s*\|\s*'
        r'(?P<time>\d{2}:\d{2})\s+'
        r'(?P<competition>.*?)\s+(?P<kind>ME|PO|FS)\s*\|\s*'
        r'(?P<number>[678]\d{8})\s+'
        r'(?P<home>.*?)\s*:\s*(?P<away>.*?)'
        r'(?=\s+Zum Spiel|\s+(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*\d{2}\.\d{2}\.|$)',
        re.I
    )
    known={(g.get('match_number') or '',g['date'],g['home'],g['away']) for g in out}
    for m in compact_re.finditer(flat):
        home=' '.join(m.group('home').split()).strip()
        away=' '.join(m.group('away').split()).strip()
        # Remove stray UI labels that sometimes precede a team name.
        home=re.sub(r'^(?:Nächste Spiele|Letzte Spiele|Mannschaftsspielplan|Wichtiger Hinweis zum Spielplan)\s+','',home,flags=re.I)
        if team.casefold() not in home.casefold() and team.casefold() not in away.casefold():
            continue
        raw_date=m.group('date')
        fmt='%d.%m.%Y' if len(raw_date.split('.')[-1])==4 else '%d.%m.%y'
        dt=datetime.strptime(raw_date+' '+m.group('time'),fmt+' %H:%M')
        number=m.group('number')
        identity=(number,dt.strftime('%Y-%m-%d'),home,away)
        if identity in known:
            continue
        prefix='u19' if 'U19' in team else ('u23' if 'U23' in team else 'u21')
        competition=' '.join(m.group('competition').split()).strip()
        # Search a small slice after the match for an explicitly labelled venue.
        tail=flat[m.end():m.end()+500]
        location=extract_location_from_text(tail)
        out.append({
            'id':prefix+'-'+number,'date':dt.strftime('%Y-%m-%d'),'time':m.group('time'),
            'home':home,'away':away,'competition':competition+' 2026/27','result':None,
            'location':location,'source_url':source_url,'match_number':number,
            'home_logo':logo_map.get(home,''),'away_logo':logo_map.get(away,'')
        })
        known.add(identity)
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

def load_venue_cache():
    path = DATA / 'venue-cache.json'
    if not path.exists():
        return {'games': {}}
    raw = load_json(path)
    return raw if isinstance(raw, dict) and isinstance(raw.get('games'), dict) else {'games': {}}

def game_identity(game):
    return '|'.join((str(game.get('date','')), str(game.get('time','')), canonical_club_name(game.get('home','')), canonical_club_name(game.get('away',''))))

def venue_cache_key(game):
    return str(game.get('match_number') or game.get('id') or game_identity(game))

def apply_venue_cache(games, cache):
    records = cache.get('games', {}) if isinstance(cache, dict) else {}
    by_identity = {str(v.get('identity','')): v for v in records.values() if isinstance(v, dict) and v.get('identity')}
    out=[]
    for original in games:
        g=deepcopy(original)
        if not str(g.get('location') or '').strip():
            rec=records.get(venue_cache_key(g)) or by_identity.get(game_identity(g))
            if isinstance(rec, dict) and rec.get('location'):
                g['location']=rec['location']
                g['location_source']=rec.get('source_url','')
        out.append(g)
    return out

def update_venue_cache(games, cache):
    records = cache.setdefault('games', {})
    changed=0
    now=datetime.now(TZ).isoformat()
    for g in games:
        location=str(g.get('location') or '').strip()
        if not location:
            continue
        key=venue_cache_key(g)
        record={'identity':game_identity(g),'location':location,'source_url':g.get('source_url',''),'updated_at':now}
        if records.get(key,{}).get('location') != location:
            records[key]=record; changed+=1
        else:
            records[key].update(record)
    cache['updated_at']=now
    return changed

def venue_for_game(game, venues, venue_cache=None):
    """Return only an explicitly sourced or exact-team venue.

    Youth/reserve aliases must never inherit the first team's ground. This
    prevents an unverified home venue (for example the Preussenstadion) from
    being shown for U19/U21/U23 fixtures.
    """
    explicit = str(game.get('location') or '').strip()
    if explicit:
        return explicit
    if venue_cache:
        records=venue_cache.get('games',{})
        rec=records.get(venue_cache_key(game))
        if not rec:
            identity=game_identity(game)
            rec=next((v for v in records.values() if isinstance(v,dict) and v.get('identity')==identity),None)
        if isinstance(rec,dict) and rec.get('location'):
            return str(rec['location']).strip()
    venue = venues.get(str(game.get('home', '')).strip(), {})
    if isinstance(venue, str):
        return venue
    name = str(venue.get('stadium') or '').strip()
    address = str(venue.get('address') or '').strip()
    return ', '.join(x for x in (name, address) if x)

def venue_record_for_game(game, venues):
    venue=venues.get(str(game.get('home','')).strip(), {})
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

def _safe_logo_filename(team, url=''):
    canonical=canonical_club_name(team)
    slug=re.sub(r'[^a-z0-9]+','-',canonical.casefold().replace('ä','ae').replace('ö','oe').replace('ü','ue').replace('ß','ss')).strip('-') or 'verein'
    ext=Path(url.split('?',1)[0]).suffix.lower()
    if ext not in ('.png','.jpg','.jpeg','.webp','.gif','.svg'):
        ext='.png'
    return slug+ext


def cache_logo(team, url):
    """Download a crest once and return a same-origin URL.

    Failed downloads are harmless: the UI falls back to initials rather than a
    question mark. Source-provided crests take precedence over favicon URLs.
    """
    if not url:
        return ''
    if 'gstatic.com/favicon' in str(url) or 'google.com/s2/favicons' in str(url):
        return ''
    if os.environ.get('RSV_OFFLINE') == '1':
        return str(url) if str(url).startswith('/assets/') else ''
    if str(url).startswith('/assets/clubs/'):
        return str(url)
    folder=DOCS/'assets'/'clubs'
    folder.mkdir(parents=True,exist_ok=True)
    filename=_safe_logo_filename(team,str(url))
    target=folder/filename
    if target.exists() and target.stat().st_size>200:
        return '/assets/clubs/'+filename
    try:
        r=requests.get(str(url),headers={'User-Agent':UA,'Accept':'image/*'},timeout=20)
        r.raise_for_status()
        ctype=(r.headers.get('content-type') or '').lower()
        if not r.content or len(r.content)<200 or ('image' not in ctype and not str(url).lower().endswith('.svg')):
            return ''
        # Correct extension when the server tells us the actual format.
        ext=mimetypes.guess_extension(ctype.split(';',1)[0].strip()) or target.suffix
        if ext=='.jpe': ext='.jpg'
        if ext in ('.png','.jpg','.jpeg','.webp','.gif','.svg') and ext!=target.suffix:
            target=target.with_suffix(ext); filename=target.name
        target.write_bytes(r.content)
        return '/assets/clubs/'+filename
    except Exception as exc:
        warnings.warn(f'Logo konnte nicht lokal gespeichert werden ({team}): {exc}')
        return ''


def game_logo_candidates(games):
    found={}
    for g in games:
        for side in ('home','away'):
            name=str(g.get(side,'')).strip()
            url=str(g.get(side+'_logo','') or '').strip()
            if name and url:
                # Prefer federation/team-page crests to generic Google favicons.
                current=found.get(canonical_club_name(name),'')
                if not current or ('google.com/s2/favicons' in current and 'google.com/s2/favicons' not in url):
                    found[canonical_club_name(name)]=url
    return found

def club_logo_url(team, clubs, discovered=None):
    canonical=canonical_club_name(team)
    discovered=discovered or {}
    source_logo=str(discovered.get(canonical) or discovered.get(team) or '').strip()
    info=clubs.get(canonical) or clubs.get(team) or {}
    configured=str(info.get('logo_url') or '').strip()
    preferred=source_logo or configured
    if preferred:
        return cache_logo(canonical, preferred) or preferred
    # Last-resort parent-club lookup for youth/reserve suffixes.
    parent=re.sub(r'\s+(?:U19|U21|U23|I|II|III|1)$','',canonical).strip()
    info=clubs.get(parent) or {}
    fallback=str(info.get('logo_url') or '').strip()
    return cache_logo(parent, fallback) or fallback


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
    venue_cache = load_venue_cache()
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
        location=venue_for_game(g, venues, venue_cache)
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



def round_kind_and_label(game):
    comp=competition_label(game.get('competition',''))
    low=comp.casefold()
    if 'pokal' in low:
        raw=str(game.get('round') or game.get('cup_round') or '').strip()
        if not raw:
            # Prefer explicit round wording contained in the competition name.
            m=re.search(r'(\d+\.\s*Runde|Achtelfinale|Viertelfinale|Halbfinale|Finale)', comp, re.I)
            raw=m.group(1) if m else 'Pokalrunde'
        return 'cup', raw, f'{raw} – {comp}'
    md=game.get('matchday')
    if md:
        try:
            n=int(md)
            ordinals={1:'Erster',2:'Zweiter',3:'Dritter',4:'Vierter',5:'Fünfter',6:'Sechster',7:'Siebter',8:'Achter',9:'Neunter',10:'Zehnter'}
            lead=ordinals.get(n, f'{n}.')
            title=f'{lead} Spieltag {comp}' if n<=10 else f'{n}. Spieltag {comp}'
        except Exception:
            title=f'{md}. Spieltag {comp}'
        return 'league', str(md), title
    return 'other', game.get('id',''), comp or 'Spieltermin'

def load_round_pairings():
    path=DATA/'rounds.json'
    return load_json(path) if path.exists() else {}

def build_round_groups(key, games, clubs, discovered_logos):
    configured=load_round_pairings().get(key, [])
    groups={}
    # Official full-round data wins whenever present.
    for item in configured:
        gid=str(item.get('id') or '')
        if not gid: continue
        groups[gid]={**item, 'matches':list(item.get('matches') or [])}
    for g in games:
        kind, token, title=round_kind_and_label(g)
        if kind=='other':
            gid='game:'+str(g.get('id'))
            groups.setdefault(gid,{'id':gid,'kind':'game','title':title,'competition':competition_label(g.get('competition','')),'matches':[]})
        else:
            gid=f'{kind}:{competition_label(g.get("competition",""))}:{token}'
            groups.setdefault(gid,{'id':gid,'kind':kind,'title':title,'competition':competition_label(g.get('competition','')),'round':token,'matches':[]})
        if not any((x.get('id') and x.get('id')==g.get('id')) or (x.get('date')==g.get('date') and x.get('home')==g.get('home') and x.get('away')==g.get('away')) for x in groups[gid]['matches']):
            groups[gid]['matches'].append({k:g.get(k) for k in ('id','date','time','home','away','result','halftime_result','location','matchday')})
    out=[]
    for grp in groups.values():
        for m in grp['matches']:
            m['home_logo']=m.get('home_logo') or club_logo_url(m.get('home',''),clubs,discovered_logos)
            m['away_logo']=m.get('away_logo') or club_logo_url(m.get('away',''),clubs,discovered_logos)
        grp['matches'].sort(key=lambda x:(x.get('date') or '',x.get('time') or '00:00',x.get('home') or ''))
        dates=[m.get('date') for m in grp['matches'] if m.get('date')]
        grp['date']=min(dates) if dates else ''
        out.append(grp)
    return sorted(out,key=lambda x:(x.get('date') or '',x.get('title') or ''))

def build_site_data(team_configs, ticket_events=None):
    """Create the JSON used by the results, upcoming matches and table view."""
    payload={'generated_at': datetime.now(TZ).isoformat(), 'teams':{}, 'tables': load_json(DATA/'tables.json') if (DATA/'tables.json').exists() else {}, 'club_websites': {name: info.get('website','') for name, info in load_clubs().items() if isinstance(info, dict) and info.get('website')}, 'club_aliases': load_club_aliases()}
    venues = load_venues()
    venue_cache = load_venue_cache()
    clubs = load_clubs()
    all_games=[g for _key,_meta,gs in team_configs for g in gs]
    discovered_logos=game_logo_candidates(all_games)
    ticket_events = ticket_events or []
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
            location=venue_for_game(g, venues, venue_cache)
            # Alle Wettbewerbe gehören in die vollständige Terminliste.
            fixtures.append({
                    'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                    'competition':comp, 'home':g.get('home'), 'away':g.get('away'),
                    'home_logo':g.get('home_logo') or club_logo_url(g.get('home',''), clubs, discovered_logos), 'away_logo':g.get('away_logo') or club_logo_url(g.get('away',''), clubs, discovered_logos),
                    'result':g.get('result') or '', 'location':location, 'maps_url':maps_url(location),
                    'weather_url':weather_search_url(location, g.get('date','')),
                    'ticket_url':ticket_url_for_game(g, team_name, ticket_events) if key=='regionalliga' and not g.get('result') and str(g.get('date','')) >= today.isoformat() else ''
            })

            if g.get('result'):
                completed.append({
                    'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                    'competition':comp, 'home':g.get('home'), 'away':g.get('away'),
                    'home_logo':g.get('home_logo') or club_logo_url(g.get('home',''), clubs, discovered_logos), 'away_logo':g.get('away_logo') or club_logo_url(g.get('away',''), clubs, discovered_logos),
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
                'home_logo':g.get('home_logo') or club_logo_url(g.get('home',''), clubs, discovered_logos), 'away_logo':g.get('away_logo') or club_logo_url(g.get('away',''), clubs, discovered_logos),
                'location':location, 'maps_url':maps_url(location),
                'weather':None, 'weather_url':weather_search_url(location, g.get('date','')),
                'is_home':g.get('home') == team_name,
                'ticket_url':ticket_url_for_game(g, team_name, ticket_events) if key=='regionalliga' else ''
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
            'round_groups':build_round_groups(key, enriched, clubs, discovered_logos),
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
            'rows':[{'position':i,'team':t,'played':0,'wins':0,'draws':0,'losses':0,'goals':'0:0','diff':'0','points':0,'logo_url':club_logo_url(t, clubs, discovered_logos)} for i,t in enumerate(teams,1)]
        }

    # Complete every table with every league participant seen in the full
    # fixture list. This prevents abbreviated source tables from hiding clubs.
    for key, meta, games in team_configs:
        table=payload.setdefault('tables',{}).setdefault(key,{'competition':'','updated_at':'','rows':[]})
        rows=table.setdefault('rows',[])
        known={canonical_club_name(str(r.get('team','')).strip()) for r in rows if r.get('team')}
        league_games=[g for g in games if not any(w in competition_label(g.get('competition','')).lower() for w in ('pokal','freundschaft','testspiel'))]
        participants=sorted({str(g.get('home','')).strip() for g in league_games}|{str(g.get('away','')).strip() for g in league_games}, key=str.casefold)
        for team in participants:
            if team and canonical_club_name(team) not in known:
                rows.append({'position':len(rows)+1,'team':team,'played':0,'wins':0,'draws':0,'losses':0,'goals':'0:0','diff':'0','points':0})
                known.add(canonical_club_name(team))
        for i,row in enumerate(rows,1):
            if row.get('position') in (None,''): row['position']=i
            row['logo_url'] = club_logo_url(row.get('team', ''), clubs, discovered_logos)
    (DOCS/'site-data.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def is_league_game(game):
    competition = competition_label(game.get('competition', '')).lower()
    return not any(word in competition for word in ('pokal', 'freundschaft', 'testspiel'))


def league_game_count(games):
    return sum(1 for game in games if is_league_game(game))


def validate_schedule_completeness(key, meta, existing, remote, source_errors=None):
    """Validate the official league schedule, not an arbitrary total count.

    Cup and friendly fixtures are additional and may legitimately make the total
    larger or smaller at different points in the season. The stable completeness
    criterion is therefore the number of published league fixtures expected for
    the specific competition.
    """
    if not remote:
        details = ' | '.join(source_errors or [])
        raise RuntimeError('keine Spiele erkannt' + (f'; {details}' if details else ''))

    expected = int(meta.get('expected_league_games') or 0)
    remote_league = league_game_count(remote)
    existing_league = league_game_count(existing)

    # A known complete local/live baseline must never be replaced by a clearly
    # truncated page response (for example the first 9 or 10 visible fixtures).
    reference = max(expected, existing_league)
    if reference and remote_league < reference:
        details = ' | '.join(source_errors or [])
        raise RuntimeError(
            f'nur {remote_league} Ligaspiele erkannt; erwartet sind {reference}. '
            'Pokal- und Freundschaftsspiele werden separat und ohne Mindestzahl übernommen.'
            + (f'; {details}' if details else '')
        )


def validate_merged_schedule(key, meta, merged):
    expected = int(meta.get('expected_league_games') or 0)
    actual = league_game_count(merged)
    if expected and actual < expected:
        raise RuntimeError(
            f'{key}: unvollständiger Ligaspielplan ({actual}/{expected} Ligaspiele); '
            'vorhandene Live-Daten werden nicht überschrieben. '
            'Pokal- und Freundschaftsspiele zählen zusätzlich, aber nicht zur Liga-Vollständigkeit.'
        )


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
            validate_schedule_completeness(key, meta, games, remote, source_errors)
        except Exception as e: err=str(e); remote=[]
    venue_cache=load_venue_cache()
    merged=merge(games,remote)
    merged=apply_overrides(key,merged,load_json(DATA/'overrides.json'))
    merged=apply_venue_cache(merged,venue_cache)
    update_venue_cache(merged,venue_cache)
    save_json(DATA/'venue-cache.json',venue_cache)
    validate_merged_schedule(key, meta, merged)
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
    ticket_events=fetch_ticket_events()
    for key in ('regionalliga','u23','u21','u19'):
        try:
            ok=process(key,args.offline) and ok
            meta=load_json(DATA/f'{key}.json')
            games=apply_overrides(key,meta.get('games',[]),load_json(DATA/'overrides.json'))
            configs.append((key,meta,games))
        except Exception as e:
            print(f'{key}: FEHLER: {e}',file=sys.stderr); ok=False
    build_site_data(configs, ticket_events)
    required=('rsv-regionalliga.ics','rsv-u23.ics','rsv-u21.ics','rsv-u19.ics')
    if not ok:
        print('Mindestens eine Mannschaft konnte nicht vollständig aktualisiert werden; Veröffentlichung wird abgebrochen.', file=sys.stderr)
        return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
