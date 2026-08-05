#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os, re, sys, warnings
from io import BytesIO
from urllib.parse import quote_plus, unquote_plus, urljoin
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from fontTools.ttLib import TTFont

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; DOCS=ROOT/'docs'; STATE=ROOT/'state'
TZ=ZoneInfo('Europe/Berlin')
UA='Mozilla/5.0 (compatible; RSV-Kalender/1.0; +https://github.com/)'

DATE_RE=re.compile(r'(\d{2})\.(\d{2})\.(\d{4}).*?(\d{2}):(\d{2})')
PUA_RE=re.compile(r'[\ue000-\uf8ff]')

TICKET_OVERVIEW_URL='https://rsv-eintracht.vereinsticket.de/herren/'
FUSSBALL_FONT_URL='https://www.fussball.de/export.fontface/-/format/ttf/id/{font_id}/type/font'

# FUSSBALL.DE encodes dates, times and scores with one-off webfonts. Glyph
# names in those fonts stay stable (four -> "4", period -> ".", ...).
_OBFUSCATION_GLYPH_CHARS={
    'comma':',','period':'.','colon':':','hyphen':'-','minus':'-',
    'zero':'0','one':'1','two':'2','three':'3','four':'4',
    'five':'5','six':'6','seven':'7','eight':'8','nine':'9',
}
_OBFUSCATION_MAP_CACHE: dict[str, dict[int, str]] = {}

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

def _parse_ticket_card(text):
    """Parse opponent + date from a Vereinsticket card/overview snippet."""
    months={'januar':1,'februar':2,'märz':3,'april':4,'mai':5,'juni':6,'juli':7,'august':8,'september':9,'oktober':10,'november':11,'dezember':12}
    m=re.search(
        r'RSV Eintracht(?: 1949)?\s*[-–:]\s*(.+?)\s+(?:Mo|Di|Mi|Do|Fr|Sa|So),?\s+(\d{1,2})\.\s*'
        r'(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(20\d{2})',
        text or '', re.I,
    )
    if not m:
        return '', ''
    opponent=' '.join(m.group(1).split()).strip(' -–:')
    date=f"{int(m.group(4)):04d}-{months[m.group(3).casefold()]:02d}-{int(m.group(2)):02d}"
    return opponent, date

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
            slug=href.rstrip('/').rsplit('/',1)[-1]
            if href.rstrip('/') == TICKET_OVERVIEW_URL.rstrip('/') or href in seen:
                continue
            # Utility pages like /resend/ are not match events.
            if not slug.isdigit():
                continue
            seen.add(href)
            context=a.find_parent(['article','li','section','div']) or a.parent
            candidates.append((href, ' '.join(context.get_text(' ',strip=True).split()) if context else ''))

        events=[]
        for href, overview_text in candidates:
            # Detail pages include a "Termin wechseln" list of every event, so the
            # first RSV heading is often the wrong opponent. Prefer the overview card.
            opponent, date=_parse_ticket_card(overview_text)
            if not opponent:
                detail=BeautifulSoup(fetch(href),'html.parser')
                # Current event title is usually repeated after the switcher list.
                titles=[
                    ' '.join(h.get_text(' ',strip=True).split())
                    for h in detail.find_all(['h1','h2','h3'])
                    if re.search(r'RSV Eintracht(?: 1949)?\s*[-–:]', h.get_text(' ',strip=True), re.I)
                ]
                title=titles[-1] if titles else ''
                opponent=re.sub(r'^.*?RSV Eintracht(?: 1949)?\s*[-–:]\s*','',title,flags=re.I).strip()
                page_head=' '.join((detail.find(['h1','title']) or detail).get_text(' ',strip=True).split())
                _, date=_parse_ticket_card(f"RSV Eintracht - {opponent} {page_head}")
                if not date:
                    dm=re.search(
                        r'(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(20\d{2})',
                        page_head, re.I,
                    )
                    if dm:
                        months={'januar':1,'februar':2,'märz':3,'april':4,'mai':5,'juni':6,'juli':7,'august':8,'september':9,'oktober':10,'november':11,'dezember':12}
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
    # Ticket shop dates can differ by a day from the competition calendar.
    near=[]
    try:
        gday=datetime.fromisoformat(date).date()
    except Exception:
        gday=None
    if gday:
        for event in ticket_events:
            if event.get('opponent_key') != opponent_key or not event.get('date'):
                continue
            try:
                eday=datetime.fromisoformat(event['date']).date()
            except Exception:
                continue
            if abs((eday-gday).days) <= 1:
                near.append(event)
        if len(near)==1:
            return near[0]['url']
    # Name match is a safe fallback if a fixture date was moved in one source
    # before the other source was updated.
    matches=[event for event in ticket_events if event.get('opponent_key') == opponent_key]
    if len(matches)==1:
        return matches[0]['url']
    return TICKET_OVERVIEW_URL

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


def fetch_bytes(url):
    r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'de-DE,de;q=0.9'},timeout=30)
    r.raise_for_status()
    if not r.content:
        raise RuntimeError(f'Leere Binärantwort für {url}')
    return r.content


def _obfuscation_map(font_id):
    """Map private-use codepoints of a FUSSBALL.DE obfuscation font to characters."""
    if font_id in _OBFUSCATION_MAP_CACHE:
        return _OBFUSCATION_MAP_CACHE[font_id]
    mapping={}
    try:
        font=TTFont(BytesIO(fetch_bytes(FUSSBALL_FONT_URL.format(font_id=font_id))))
        for table in font['cmap'].tables:
            for codepoint, glyph_name in table.cmap.items():
                if glyph_name in _OBFUSCATION_GLYPH_CHARS:
                    mapping[codepoint]=_OBFUSCATION_GLYPH_CHARS[glyph_name]
                elif len(glyph_name)==1:
                    mapping[codepoint]=glyph_name
    except Exception as exc:
        warnings.warn(f'FUSSBALL.DE-Schriftart {font_id} konnte nicht geladen werden: {exc}')
        mapping={}
    _OBFUSCATION_MAP_CACHE[font_id]=mapping
    return mapping


def deobfuscate_fussball_html(html):
    """Decode ``data-obfuscation`` spans so dates/times/scores become plain text.

    Without this step the official print pages expose only private-use glyphs,
    and the table parser cannot read kickoff times or results.
    """
    soup=BeautifulSoup(html,'html.parser')
    spans=soup.select('[data-obfuscation]')
    if not spans:
        return html
    font_ids=sorted({span.get('data-obfuscation') for span in spans if span.get('data-obfuscation')})
    maps={font_id:_obfuscation_map(font_id) for font_id in font_ids}
    for span in spans:
        mapping=maps.get(span.get('data-obfuscation')) or {}
        if not mapping:
            continue
        for node in span.find_all(string=True):
            decoded=''.join(mapping.get(ord(ch), ch) for ch in str(node))
            if decoded != str(node):
                node.replace_with(decoded)
    return str(soup)


def parse_dfb(html, team):
    soup=BeautifulSoup(html,'html.parser')
    text=soup.get_text(' ',strip=True)
    # Map finished/open fixtures to official DFB match report URLs.
    report_urls={}
    for a in soup.find_all('a', href=True):
        href=a['href'].strip()
        if '/datencenter/' not in href or 'spieltag/' not in href:
            continue
        label=' '.join(a.get_text(' ',strip=True).split())
        if not re.fullmatch(r'\d+\s*:\s*\d+|-\s*:\s*-', label):
            continue
        dm=None
        node=a.parent
        for _ in range(6):
            if not node:
                break
            block=' '.join(node.get_text(' ',strip=True).split())
            dm=re.search(
                r'(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s*'
                r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+Uhr\s+(.+?)\s+(\d+\s*:\s*\d+|-\s*:\s*-)\s+(.+?)(?:Schema|Vergleich|Liveticker|$)',
                block,re.I
            )
            if dm:
                break
            node=node.parent
        if not dm:
            continue
        d,t,home,res,away=dm.groups()
        home=re.sub(r'^(?:Schema|Vergleich|Liveticker)\s+','',home).strip()
        away=re.split(r'\s+(?:Schema|Vergleich|Liveticker)\b',away)[0].strip()
        if team not in (home,away):
            continue
        try:
            date=datetime.strptime(d,'%d.%m.%Y').strftime('%Y-%m-%d')
        except ValueError:
            continue
        report_urls[(date,t,home,away)]=href if href.startswith('http') else 'https://datencenter.dfb.de'+href
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
        date=dt.strftime('%Y-%m-%d')
        out.append({
            'id':'rl-'+key,'date':date,'time':t,'home':home,'away':away,
            'competition':'Regionalliga Nordost 2026/27',
            'result':None if '-' in res else re.sub(r'\s','',res),
            'location':'','source_url':'',
            'report_url':report_urls.get((date,t,home,away),''),
        })
    return dedupe(out)


def extract_dfb_match_detail(html):
    """Read result, halftime, scorers and referee from a DFB match report page."""
    soup=BeautifulSoup(html,'html.parser')
    score_tag=soup.select_one('.m-MatchDetails-score')
    if not score_tag:
        return {}
    score_text=' '.join(score_tag.get_text(' ',strip=True).split())
    final=None
    halftime=None
    m=re.search(r'(\d+:\d+)\s*\((\d+:\d+)\)', score_text)
    if m:
        final, halftime=m.group(1), m.group(2)
    else:
        m=re.search(r'(\d+:\d+)', score_text)
        if m:
            final=m.group(1)
    ht_tag=soup.select_one('.m-MatchDetails-score-halftime')
    if ht_tag and not halftime:
        ht_m=re.search(r'(\d+:\d+)', ht_tag.get_text(' ',strip=True))
        if ht_m:
            halftime=ht_m.group(1)
    teams=[x.get_text(' ',strip=True) for x in soup.select('.m-MatchDetails-team') if x.get_text(strip=True)]
    home=teams[0] if teams else ''
    away=teams[1] if len(teams) > 1 else ''
    referee=''
    ref_tag=soup.select_one('.m-MatchDetails-referees-name')
    if ref_tag:
        referee=ref_tag.get_text(' ',strip=True)
    scorers=[]
    seen=set()
    for ev in soup.select('.m-MatchDetails-history-item'):
        if not ev.select('.m-MatchDetails-icon-goal--goal'):
            continue
        minute_tag=ev.select_one('.m-MatchDetails-history-minute')
        minute=re.sub(r'\D','', minute_tag.get_text(' ',strip=True) if minute_tag else '') or ''
        parts=[x.get_text(' ',strip=True) for x in ev.select('.m-MatchDetails-history-event-text-item') if x.get_text(strip=True)]
        if not parts:
            continue
        text=' '.join(parts)
        score_in_event=re.search(r'(\d+:\d+)\s*$', text)
        running=score_in_event.group(1) if score_in_event else ''
        name=re.sub(r'\s*\d+:\d+\s*$', '', text).strip()
        if not name:
            continue
        side='home' if ev.select('.m-MatchDetails-history-event--home') else 'away'
        club=home if side=='home' else away
        key=(minute,name,running)
        if key in seen:
            continue
        seen.add(key)
        label=f"{minute}. Minute – {name} ({club})"
        if running:
            label+=f" – {running}"
        scorers.append(label)
    out={}
    if final:
        out['result']=final
    if halftime:
        out['halftime_result']=halftime
    if referee:
        out['referee']=referee
    if scorers:
        out['scorers']=scorers
    return out


def enrich_dfb_match_details(games, offline=False):
    """Fill Regionalliga results from official DFB match report pages."""
    if offline:
        return games
    out=[]
    now=datetime.now(TZ)
    for original in games:
        g=deepcopy(original)
        url=str(g.get('report_url') or '').strip()
        if not url or 'datencenter.dfb.de' not in url:
            out.append(g)
            continue
        kickoff=parse_kickoff_datetime(g)
        live_window=bool(kickoff and kickoff <= now <= kickoff + timedelta(hours=4))
        needs_detail=bool(g.get('result') or live_window)
        if not needs_detail:
            out.append(g)
            continue
        try:
            detail=extract_dfb_match_detail(fetch(url))
        except Exception as exc:
            warnings.warn(f'DFB-Spielbericht fehlgeschlagen ({url}): {exc}')
            out.append(g)
            continue
        for key in ('result','halftime_result','referee','scorers'):
            if detail.get(key):
                g[key]=detail[key]
        out.append(g)
    return out


def extract_fussball_match_score(html):
    """Best-effort final score from a fussball.de match detail page."""
    soup=BeautifulSoup(html,'html.parser')
    for node in soup.select('.score, .result, [class*=score], [class*=result]'):
        text=' '.join(node.get_text(' ',strip=True).split())
        m=re.search(r'(?<!\d)(\d{1,2})\s*:\s*(\d{1,2})(?!\d)', text)
        if m:
            return f'{m.group(1)}:{m.group(2)}'
    text=' '.join(soup.get_text(' ',strip=True).split())
    m=re.search(r'(?<!\d)(\d{1,2})\s*:\s*(\d{1,2})(?!\d)', text)
    return f'{m.group(1)}:{m.group(2)}' if m else ''


def enrich_scores_from_detail_pages(games, offline=False):
    """Fill missing results from official match detail pages around kickoff."""
    if offline:
        return games
    out=[]
    now=datetime.now(TZ)
    for original in games:
        g=deepcopy(original)
        if g.get('result'):
            out.append(g)
            continue
        source=str(g.get('source_url') or '').strip()
        if '/spiel/' not in source:
            out.append(g)
            continue
        kickoff=parse_kickoff_datetime(g)
        if not kickoff or kickoff > now:
            out.append(g)
            continue
        if now > kickoff + timedelta(hours=4):
            out.append(g)
            continue
        try:
            score=extract_fussball_match_score(fetch(source))
        except Exception as exc:
            warnings.warn(f'FUSSBALL.DE-Spielstand fehlgeschlagen ({source}): {exc}')
            out.append(g)
            continue
        if score:
            g['result']=score
        out.append(g)
    return out


def parse_kickoff_datetime(game):
    date=str(game.get('date') or '').strip()
    time=str(game.get('time') or '00:00').strip() or '00:00'
    if not date:
        return None
    try:
        return datetime.fromisoformat(f'{date}T{time}:00').replace(tzinfo=TZ)
    except ValueError:
        return None

def _is_address_part(part):
    """True when a fussball.de pipe segment looks like street / PLZ / city."""
    part=' '.join(str(part or '').split())
    if not part or len(part) > 120:
        return False
    if re.search(r'\b\d{5}\b', part):
        return True
    if re.search(
        r'(?:str(?:\.|asse)?|straße|strasse|weg|allee|damm|ring|platz|eing\.?|chaussee|promenade)\b',
        part,re.I
    ):
        return True
    return bool(re.search(r'\d', part)) and len(part) <= 80


def extract_location_from_text(text):
    """Extract venue + street + PLZ/city from official fussball.de match text.

    Print pages typically expose:
    ``Spielstätte:Name | Straße Nr | 12345 Ort``
    All of that must be kept — never invent, never drop the address parts.
    """
    compact=' | '.join(x.strip() for x in re.split(r'\s*\|\s*', str(text)) if x.strip())
    m=re.search(
        r'(?:Spielst(?:ä|ae)tte|Spielort|Austragungsort|Platzanlage)\s*:?\s*(.+)$',
        compact,re.I
    )
    if m:
        rest=re.split(
            r'\s+(?:Schiedsrichter|Zuschauer|Zum Spiel|Absetzung)\b',
            m.group(1),1,flags=re.I
        )[0]
        parts=[]
        for part in re.split(r'\s*\|\s*', rest):
            part=part.strip(' :-')
            if not part or re.search(r'\b(?:ME|PO|FS)\b', part):
                break
            if not parts:
                parts.append(part)
                continue
            if _is_address_part(part):
                parts.append(part)
            else:
                break
            if len(parts) >= 3:
                break
        value=', '.join(parts)
        if 4 <= len(value) <= 240:
            return value
    # Fallback: venue-like name without the Spielstätte label.
    m=re.search(
        r'((?:Stadion|Sportpark|Sportanlage|Sportplatz|Arena|Kunstrasenplatz|Rasenplatz)\s+[^|]{2,150})'
        r'(?:\s*\|\s*([^|]{2,120}))?(?:\s*\|\s*(\d{5}\s+[^|]{2,80}))?',
        compact,re.I
    )
    if m:
        parts=[p.strip(' :-|') for p in m.groups() if p and str(p).strip(' :-|')]
        value=', '.join(parts)
        value=re.split(r'\s+(?:Schiedsrichter|Zuschauer|Zum Spiel|ME|PO|FS)\b',value,1,flags=re.I)[0].strip()
        if 4 <= len(value) <= 240:
            return value
    # Address-only fallback, but only when a street suffix and postal code occur
    # in the same official match block.
    m=re.search(
        r'([^|]{2,80}(?:straße|strasse|weg|allee|damm|ring|platz)\s+\d+[a-zA-Z]?(?:[–-]\d+)?'
        r'\s*,?\s*\d{5}\s+[^|]{2,60})',
        compact,re.I
    )
    return m.group(1).strip(' :-|') if m else ''

def _absolute_fussball_url(value):
    value=(value or '').strip()
    if not value:
        return ''
    if value.startswith('//'):
        return 'https:'+value
    if value.startswith('/'):
        return 'https://www.fussball.de'+value
    return value


def _team_prefix(team):
    folded=team.casefold()
    if 'u19' in folded: return 'u19'
    if 'u23' in folded: return 'u23'
    return 'u21'


def _team_match_names(team):
    """Return name variants used to recognize a team on fussball.de print pages.

    Cup print rows often list the club without the U19/U21/U23 suffix while the
    configured team_name includes it. Matching must accept both forms, but never
    invent venues from another club.
    """
    name=' '.join(str(team or '').split())
    if not name:
        return []
    names=[name]
    base=re.sub(r'\s+U(?:19|21|23)\s*$', '', name, flags=re.I).strip()
    if base and base.casefold() != name.casefold():
        names.append(base)
    return names


def _team_in_fixture(team, home, away):
    home_cf=str(home or '').casefold()
    away_cf=str(away or '').casefold()
    for candidate in _team_match_names(team):
        cf=candidate.casefold()
        if cf and (cf in home_cf or cf in away_cf):
            return True
    return False


def _clean_team_name(name):
    name=PUA_RE.sub('', str(name or ''))
    name=' '.join(name.split()).strip(' :|-')
    # Print-page scrapes sometimes glue venue/referee text onto the away name.
    name=re.split(
        r'\s+(?:-|–|:)\s*(?:-|–|:)\s*|Schiedsrichter:|Spielstätte:|Zum Spiel|\b(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*\d{2}\.\d{2}\.',
        name,1,flags=re.I
    )[0].strip(' :|-')
    return name


def _location_from_match_tail(text):
    """Take only the first explicit venue before the next fixture block."""
    chunk=str(text or '')
    chunk=re.split(
        r'\s+(?:Zum Spiel|Absetzung|(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)|(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*\d{2}\.\d{2}\.)\b',
        chunk,1,flags=re.I
    )[0]
    return extract_location_from_text(chunk)


def _extract_team_cell(cell):
    if not cell:
        return '', ''
    name_tag=cell.select_one('.club-name')
    if name_tag:
        name=' '.join(name_tag.get_text(' ',strip=True).split())
    else:
        # Remove image/utility text before taking the cell text.
        name=' '.join(cell.get_text(' ',strip=True).split())
    name=_clean_team_name(name)
    logo=''
    responsive=cell.select_one('[data-responsive-image]')
    if responsive:
        logo=responsive.get('data-responsive-image','')
    if not logo:
        img=cell.find('img')
        if img:
            logo=img.get('data-src') or img.get('src') or ''
    return name, _absolute_fussball_url(logo)


def _parse_header_info(text):
    text=' '.join(str(text).replace('\xa0',' ').split())
    # Long print-page header, for example:
    # Samstag, 30.08.2026 - 14:00 Uhr | Herren | Kreisoberliga
    m=re.search(
        r'(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s*'
        r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})\s*Uhr\s*\|\s*(.+)$',
        text,re.I)
    if m:
        parts=[x.strip() for x in m.group(3).split('|') if x.strip()]
        return m.group(1),m.group(2),parts[-1] if parts else ''
    # Compact AJAX/print header.
    m=re.search(
        r'(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*(\d{2}\.\d{2}\.(?:\d{2}|\d{4}))\s*\|\s*'
        r'(\d{2}:\d{2})\s+(.+?)(?:\s+(?:ME|PO|FS))?(?:\s*\||$)',text,re.I)
    if m:
        raw=m.group(1)
        fmt='%d.%m.%Y' if len(raw.rsplit('.',1)[-1])==4 else '%d.%m.%y'
        date=datetime.strptime(raw,fmt).strftime('%d.%m.%Y')
        return date,m.group(2),m.group(3).strip()
    return None


def _plain_score(score_cell):
    if not score_cell:
        return None
    text=' '.join(score_cell.get_text(' ',strip=True).split())
    m=re.search(r'(?<!\d)(\d{1,2})\s*:\s*(\d{1,2})(?!\d)',text)
    return f'{m.group(1)}:{m.group(2)}' if m else None


def _match_number_from_link(url):
    if not url:
        return ''
    patterns=(r'/spiel/([^/?#]+)',r'/game/([^/?#]+)',r'\b([678]\d{8})\b')
    for pat in patterns:
        m=re.search(pat,url)
        if m: return m.group(1)
    return ''


def _normalize_location_value(value):
    value=' '.join(str(value or '').split())
    value=re.sub(r'^\s*Rasenplatz,\s*','',value,flags=re.I)
    value=re.sub(r'\s*\|\s*',', ',value)
    value=re.sub(r'\s*,\s*',', ',value).strip(' ,')
    return value


def _explicit_location_from_tag(tag):
    if not tag:
        return ''
    # Prefer an explicit location link or labelled venue element.
    for selector in ('a.location','.location','[data-location]','.venue','.spielort','.sports-location'):
        node=tag.select_one(selector)
        if node:
            value=node.get('data-location') or node.get_text(' ',strip=True)
            value=_normalize_location_value(value)
            # Detail links sometimes only expose the maps query — keep full text.
            if value and not re.search(r'\b\d{5}\b', value):
                href=_normalize_location_value(node.get('href') or '')
                maps=re.search(r'[?&]q=([^&]+)', href)
                if maps:
                    query=_normalize_location_value(unquote_plus(maps.group(1)))
                    if re.search(r'\b\d{5}\b', query):
                        value=f'{value}, {query}' if value.casefold() not in query.casefold() else query
            if value:
                return value
    return extract_location_from_text(tag.get_text(' | ',strip=True))


def _competition_from_cell(text):
    parts=[p.strip() for p in re.split(r'\s*\|\s*', str(text or '')) if p.strip()]
    # Print pages use "Herren | Kreisliga"; keep the competition name only.
    skip={'herren','a-junioren','b-junioren','c-junioren','d-junioren','e-junioren','f-junioren','g-junioren'}
    for part in reversed(parts):
        if part.casefold() not in skip:
            return part
    return parts[-1] if parts else ''


def _match_number_from_info(text):
    m=re.search(r'\b(?:ME|PO|FS)\s*\|\s*([A-Za-z0-9_-]{6,})\b', str(text or ''), re.I)
    return m.group(1) if m else ''


def _enrich_current_from_competition_row(row, current):
    """Read competition name + official match id from print ``row-competition``."""
    if current is None:
        date_cell=row.select_one('td.column-date')
        if date_cell:
            date_text=' '.join(date_cell.get_text(' ',strip=True).split())
            header=_parse_header_info(date_text if '|' in date_text else date_text+' | x')
            if not header:
                # "So, 16.08.26 | 10:30" split across spans becomes one cell.
                m=re.search(
                    r'(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*(\d{2}\.\d{2}\.(?:\d{2}|\d{4}))\s*\|\s*(\d{2}:\d{2})',
                    date_text,re.I)
                if m:
                    raw=m.group(1)
                    fmt='%d.%m.%Y' if len(raw.rsplit('.',1)[-1])==4 else '%d.%m.%y'
                    date=datetime.strptime(raw,fmt).strftime('%d.%m.%Y')
                    current={'date':date,'time':m.group(2),'competition':'','match_number':''}
            else:
                date,time,competition=header
                current={'date':date,'time':time,'competition':competition,'match_number':''}
    if current is None:
        return None
    team_cell=row.select_one('td.column-team')
    if team_cell:
        competition=_competition_from_cell(team_cell.get_text(' ',strip=True))
        if competition:
            current['competition']=competition
    info_text=' '.join(row.get_text(' ',strip=True).split())
    match_number=_match_number_from_info(info_text)
    if match_number:
        current['match_number']=match_number
    return current


def _prefer_game(existing, candidate):
    """Prefer the richer of two equivalent fixtures during dedupe."""
    def score(game):
        match_number=str(game.get('match_number') or '')
        location=str(game.get('location') or '')
        glued=bool(re.search(r'Schiedsrichter:|Spielstätte:', f"{game.get('home','')} {game.get('away','')}", re.I))
        detail=1 if '/spiel/' in str(game.get('source_url') or '') else 0
        full_address=1 if re.search(r'\b\d{5}\b', location) else 0
        return (
            1 if re.fullmatch(r'\d{6,}', match_number) else 0,
            0 if glued else 1,
            detail,
            full_address,
            1 if location else 0,
            1 if game.get('result') else 0,
            1 if game.get('home_logo') or game.get('away_logo') else 0,
            0 if PUA_RE.search(f"{game.get('home','')}{game.get('away','')}") else 1,
            len(match_number),
            len(location),
        )
    return candidate if score(candidate) > score(existing) else existing


def parse_fussball_table(html, team, source_url):
    """Parse the complete FUSSBALL.DE print/AJAX table structure.

    FUSSBALL.DE renders each fixture as a date header row followed by a row with
    club and score cells. Print pages additionally expose a ``row-competition``
    line with the official match id (``ME|PO|FS | 610480004``). The parser
    intentionally reads every table row, so it does not stop at the initially
    visible 6-10 fixtures.
    """
    soup=BeautifulSoup(html,'html.parser')
    rows=soup.find_all('tr')
    out=[]; current=None; prefix=_team_prefix(team)
    for idx,row in enumerate(rows):
        classes=set(row.get('class') or [])
        if 'row-competition' in classes:
            current=_enrich_current_from_competition_row(row, current)
            continue
        row_text=' '.join(row.get_text(' ',strip=True).split())
        header=_parse_header_info(row_text)
        if 'visible-small' in classes or (header and not row.select_one('td.column-score')):
            if header:
                date,time,competition=header
                current={
                    'date':date,
                    'time':time,
                    'competition':_competition_from_cell(competition) or competition,
                    'match_number':(current or {}).get('match_number',''),
                }
            continue
        score_cell=row.select_one('td.column-score')
        if not score_cell or not current:
            continue
        home_cell=row.select_one('td.column-club-left')
        away_cell=row.select_one('td.column-club-right')
        if not home_cell or not away_cell:
            cells=row.select('td.column-club')
            if len(cells)>=2:
                home_cell,away_cell=cells[0],cells[1]
        home,home_logo=_extract_team_cell(home_cell)
        away,away_logo=_extract_team_cell(away_cell)
        home=PUA_RE.sub('', home).strip()
        away=PUA_RE.sub('', away).strip()
        if not home or not away:
            continue
        if not _team_in_fixture(team, home, away):
            continue
        link=score_cell.find('a',href=True) or row.find('a',href=re.compile(r'/spiel/'))
        detail_url=_absolute_fussball_url(link.get('href','') if link else '')
        match_number=current.get('match_number') or _match_number_from_link(detail_url)
        date=current['date']; time=current['time']
        dt=datetime.strptime(date+' '+time,'%d.%m.%Y %H:%M')
        if not match_number:
            match_number=hashlib.sha1(f'{dt.isoformat()}|{home}|{away}'.encode()).hexdigest()[:12]
        location=_explicit_location_from_tag(row)
        # Venue belongs to the immediate following row-venue only — never a later fixture.
        if not location and idx+1<len(rows):
            next_row=rows[idx+1]
            next_classes=set(next_row.get('class') or [])
            if 'row-venue' in next_classes:
                location=_explicit_location_from_tag(next_row)
            elif (
                not next_row.select_one('td.column-score')
                and not _parse_header_info(next_row.get_text(' ',strip=True))
                and re.search(r'Spielst(?:ä|ae)tte|Spielort', next_row.get_text(' ',strip=True), re.I)
            ):
                location=_explicit_location_from_tag(next_row)
        competition=current.get('competition','').strip()
        out.append({
            'id':prefix+'-'+match_number,
            'date':dt.strftime('%Y-%m-%d'),'time':time,
            'home':home,'away':away,
            'competition':(competition+' 2026/27').strip(),
            'result':_plain_score(score_cell),'location':location,
            'source_url':detail_url or source_url,'match_number':match_number,
            'home_logo':home_logo,'away_logo':away_logo,
        })
        # Match id belongs to a single fixture; avoid leaking it to the next row.
        current={**current,'match_number':''}
    return dedupe(out)


def parse_fussball_text_fallback(html, team, source_url):
    """Compatibility fallback for uncommon text-only FUSSBALL.DE responses."""
    soup=BeautifulSoup(html,'html.parser')
    flat=' '.join(soup.get_text(' ',strip=True).split())
    out=[]; prefix=_team_prefix(team)
    compact_re=re.compile(
        r'(?P<day>Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*'
        r'(?P<date>\d{2}\.\d{2}\.(?:\d{2}|\d{4}))\s*\|\s*'
        r'(?P<time>\d{2}:\d{2})\s+'
        r'(?P<competition>.*?)\s+(?P<kind>ME|PO|FS)\s*\|\s*'
        r'(?P<number>[A-Za-z0-9_-]{8,})\s+'
        r'(?P<home>.*?)\s*:\s*(?P<away>.*?)'
        r'(?=\s+(?:-|–|:)\s*(?:-|–|:)\s*|\s+Schiedsrichter:|\s+Spielstätte:|\s+Zum Spiel|\s+Absetzung|'
        r'\s+(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)\b|'
        r'\s+(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*\d{2}\.\d{2}\.|$)',re.I)
    for m in compact_re.finditer(flat):
        home=_clean_team_name(m.group('home'))
        away=_clean_team_name(m.group('away'))
        if not _team_in_fixture(team, home, away):
            continue
        raw=m.group('date'); fmt='%d.%m.%Y' if len(raw.rsplit('.',1)[-1])==4 else '%d.%m.%y'
        dt=datetime.strptime(raw+' '+m.group('time'),fmt+' %H:%M')
        number=m.group('number')
        competition=_competition_from_cell(m.group('competition')) or ' '.join(m.group('competition').split()).strip()
        # Only the immediate post-match block may supply the venue.
        tail=flat[m.end():m.end()+280]
        out.append({
            'id':prefix+'-'+number,'date':dt.strftime('%Y-%m-%d'),'time':m.group('time'),
            'home':home,'away':away,'competition':competition+' 2026/27',
            'result':None,'location':_location_from_match_tail(tail),'source_url':source_url,
            'match_number':number,'home_logo':'','away_logo':''})
    return dedupe(out)


def parse_fussball(html, team, source_url):
    html=deobfuscate_fussball_html(html)
    table_games=parse_fussball_table(html,team,source_url)
    fallback_games=parse_fussball_text_fallback(html,team,source_url)
    games=dedupe(table_games+fallback_games)
    print(
        f'FUSSBALL.DE Parser {team}: Tabellenstruktur={len(table_games)}, '
        f'Text-Fallback={len(fallback_games)}, zusammen={len(games)}'
    )
    return games

def dedupe(games):
    by_id={}
    for game in games:
        previous=by_id.get(game['id'])
        by_id[game['id']]=game if previous is None else _prefer_game(previous, game)
    by_identity={}
    for game in by_id.values():
        identity=(
            game.get('date',''),
            normalize_match_name(game.get('home','')),
            normalize_match_name(game.get('away','')),
        )
        previous=by_identity.get(identity)
        by_identity[identity]=game if previous is None else _prefer_game(previous, game)
    return sorted(by_identity.values(),key=lambda x:(x['date'],x.get('time','00:00'),x.get('id','')))

def location_has_full_address(location):
    """True when location includes a German PLZ (street/city usually accompany it)."""
    return bool(re.search(r'\b\d{5}\b', str(location or '')))


def prefer_location(old, new):
    """Keep the more complete fussball.de venue string; never invent one."""
    old=str(old or '').strip()
    new=str(new or '').strip()
    if not new:
        return old
    if not old:
        return new
    old_full=location_has_full_address(old)
    new_full=location_has_full_address(new)
    if new_full and not old_full:
        return new
    if old_full and not new_full:
        return old
    return new if len(new) >= len(old) else old


def _venue_name_key(location):
    name=str(location or '').split(',')[0].strip()
    name=re.sub(r'\s+', ' ', name).casefold()
    return name if len(name) >= 4 else ''


def merge(base, remote):
    result={g['id']:deepcopy(g) for g in base}
    for game in result.values():
        game['home']=_clean_team_name(game.get('home',''))
        game['away']=_clean_team_name(game.get('away',''))
    # Secondary identity lets remote IDs change without duplicating games.
    by_identity={(g['date'],g['home'],g['away']):g['id'] for g in result.values()}
    by_pair={(normalize_match_name(g['home']), normalize_match_name(g['away'])):g['id'] for g in result.values()}
    for g in remote:
        g={**g,'home':_clean_team_name(g.get('home','')),'away':_clean_team_name(g.get('away',''))}
        pair=(normalize_match_name(g['home']), normalize_match_name(g['away']))
        target=(
            g['id'] if g['id'] in result
            else by_identity.get((g['date'],g['home'],g['away']))
            or by_pair.get(pair, g['id'])
        )
        old=result.get(target,{})
        merged={**old,**{k:v for k,v in g.items() if v not in ('',None)},'id':target}
        merged['location']=prefer_location(old.get('location'), g.get('location'))
        result[target]=merged
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

def ics_plain(s):
    """Strip emoji/symbols that break Apple Calendar subscriptions when folded."""
    text=str(s or '')
    text=re.sub(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F\u200d]+','',text)
    return re.sub(r'[ \t]{2,}',' ',text).strip()

def fold(line):
    """RFC 5545 folding without splitting multi-byte UTF-8 codepoints."""
    out=[]
    raw=str(line or '')
    while len(raw.encode('utf-8'))>75:
        cut=min(len(raw), 75)
        while cut>1 and len(raw[:cut].encode('utf-8'))>75:
            cut-=1
        # Prefer breaking on spaces when possible for readability.
        space=raw.rfind(' ', 40, cut+1)
        if space>=40:
            cut=space+1
            while cut>1 and len(raw[:cut].encode('utf-8'))>75:
                cut-=1
        out.append(raw[:cut])
        raw=' '+raw[cut:].lstrip(' ') if raw[cut:cut+1]==' ' else ' '+raw[cut:]
    out.append(raw)
    return '\r\n'.join(out)

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
        current=str(g.get('location') or '').strip()
        rec=records.get(venue_cache_key(g)) or by_identity.get(game_identity(g))
        cached=str((rec or {}).get('location') or '').strip() if isinstance(rec, dict) else ''
        chosen=prefer_location(current, cached)
        if chosen and chosen != current:
            g['location']=chosen
            if isinstance(rec, dict):
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
        previous=str((records.get(key) or {}).get('location') or '')
        location=prefer_location(previous, location)
        if not location_has_full_address(location) and location_has_full_address(previous):
            location=previous
        record={'identity':game_identity(g),'location':location,'source_url':g.get('source_url',''),'updated_at':now}
        if previous != location:
            records[key]=record; changed+=1
        else:
            records[key]= {**records.get(key,{}), **record}
    cache['updated_at']=now
    return changed


def extract_location_from_match_html(html):
    """Full venue string from a fussball.de match detail page."""
    soup=BeautifulSoup(html,'html.parser')
    node=soup.select_one('a.location')
    if node:
        value=_normalize_location_value(node.get_text(' ',strip=True))
        if not location_has_full_address(value):
            href=node.get('href') or ''
            maps=re.search(r'[?&]q=([^&]+)', href)
            if maps:
                query=_normalize_location_value(unquote_plus(maps.group(1)))
                if location_has_full_address(query):
                    value=f'{value}, {query}' if value and value.casefold() not in query.casefold() else query
        if value:
            return value
    return extract_location_from_text(soup.get_text(' | ',strip=True))


def enrich_locations_from_detail_pages(games, offline=False):
    """Fill missing street/PLZ/city from the official match detail page."""
    if offline:
        return games
    out=[]
    for original in games:
        g=deepcopy(original)
        location=str(g.get('location') or '').strip()
        source=str(g.get('source_url') or '')
        if location_has_full_address(location) or '/spiel/' not in source:
            out.append(g)
            continue
        try:
            detail=extract_location_from_match_html(fetch(source))
        except Exception as exc:
            warnings.warn(f'Spielort-Detailseite fehlgeschlagen ({source}): {exc}')
            detail=''
        chosen=prefer_location(location, detail)
        if chosen:
            g['location']=chosen
            g['location_source']=source
        out.append(g)
    return out


def enrich_locations_from_known_venues(games, cache=None):
    """Upgrade truncated pitch names using fuller fussball.de strings already seen."""
    catalog={}
    records=(cache or {}).get('games', {}) if isinstance(cache, dict) else {}
    for source in list(games) + [v for v in records.values() if isinstance(v, dict)]:
        loc=str((source.get('location') if isinstance(source, dict) else '') or '').strip()
        if not location_has_full_address(loc):
            continue
        key=_venue_name_key(loc)
        if key and len(loc) >= len(catalog.get(key, '')):
            catalog[key]=loc
    out=[]
    for original in games:
        g=deepcopy(original)
        loc=str(g.get('location') or '').strip()
        if loc and not location_has_full_address(loc):
            fuller=catalog.get(_venue_name_key(loc))
            if fuller:
                g['location']=fuller
        out.append(g)
    return out


def drop_incomplete_locations(games):
    """Never keep pitch-only leftovers without street/PLZ/city from fussball.de."""
    out=[]
    for original in games:
        g=deepcopy(original)
        loc=str(g.get('location') or '').strip()
        if loc and not location_has_full_address(loc):
            g['location']=''
        out.append(g)
    return out

def venue_for_game(game, venues, venue_cache=None):
    """Return only an explicitly sourced or exact-team venue.

    Youth/reserve aliases must never inherit the first team's ground. This
    prevents an unverified home venue (for example the Preussenstadion) from
    being shown for U19/U21/U23 fixtures.
    """
    explicit = str(game.get('location') or '').strip()
    if location_has_full_address(explicit):
        return explicit
    if venue_cache:
        records=venue_cache.get('games',{})
        rec=records.get(venue_cache_key(game))
        if not rec:
            identity=game_identity(game)
            rec=next((v for v in records.values() if isinstance(v,dict) and v.get('identity')==identity),None)
        cached=str((rec or {}).get('location') or '').strip() if isinstance(rec, dict) else ''
        chosen=prefer_location(explicit, cached)
        if location_has_full_address(chosen):
            return chosen
    venue = venues.get(str(game.get('home', '')).strip(), {})
    if isinstance(venue, str):
        return prefer_location(explicit, venue)
    name = str(venue.get('stadium') or '').strip()
    address = str(venue.get('address') or '').strip()
    fallback=', '.join(x for x in (name, address) if x)
    return prefer_location(explicit, fallback)

def venue_record_for_game(game, venues):
    venue=venues.get(str(game.get('home','')).strip(), {})
    return venue if isinstance(venue, dict) else {}

def parse_score(value):
    m = re.match(r'^\s*(\d+)\s*:\s*(\d+)\s*$', str(value or ''))
    return (int(m.group(1)), int(m.group(2))) if m else None


def compute_standings(matches):
    """Build league table rows from finished matches."""
    stats={}
    def ensure(team):
        if team not in stats:
            stats[team]={'team':team,'played':0,'wins':0,'draws':0,'losses':0,'goals_for':0,'goals_against':0,'points':0}
        return stats[team]
    for g in matches:
        score=parse_score(g.get('result'))
        if not score:
            continue
        home=_clean_team_name(g.get('home',''))
        away=_clean_team_name(g.get('away',''))
        if not home or not away:
            continue
        hg,ag=score
        sh,sa=ensure(home),ensure(away)
        sh['played']+=1; sa['played']+=1
        sh['goals_for']+=hg; sh['goals_against']+=ag
        sa['goals_for']+=ag; sa['goals_against']+=hg
        if hg>ag:
            sh['wins']+=1; sh['points']+=3; sa['losses']+=1
        elif hg<ag:
            sa['wins']+=1; sa['points']+=3; sh['losses']+=1
        else:
            sh['draws']+=1; sa['draws']+=1; sh['points']+=1; sa['points']+=1
    rows=[]
    for s in stats.values():
        diff=s['goals_for']-s['goals_against']
        rows.append({
            'team':s['team'],'played':s['played'],'wins':s['wins'],'draws':s['draws'],'losses':s['losses'],
            'goals':f"{s['goals_for']}:{s['goals_against']}",
            'diff':f"{diff:+d}" if diff else '0',
            'points':s['points'],
            '_gf':s['goals_for'], '_gd':diff,
        })
    rows.sort(key=lambda r:(-r['points'], -r['_gd'], -r['_gf'], r['team'].casefold()))
    for i,r in enumerate(rows,1):
        r['position']=i
        del r['_gf']; del r['_gd']
    return rows


def refresh_tables_from_rounds():
    """Recompute league tables from all finished round-pairing results."""
    rounds=load_round_pairings()
    tables=load_json(DATA/'tables.json') if (DATA/'tables.json').exists() else {}
    changed=False
    for team_key in ('regionalliga','u23','u21','u19'):
        league_matches=[]
        rounds_with_results=set()
        for grp in rounds.get(team_key) or []:
            if grp.get('kind')!='league':
                continue
            for m in grp.get('matches') or []:
                league_matches.append(m)
                if parse_score(m.get('result')) and grp.get('round'):
                    rounds_with_results.add(int(grp['round']))
        if not league_matches:
            continue
        rows=compute_standings(league_matches)
        if not rows:
            continue
        comp=competition_label(league_matches[0].get('competition','')) if league_matches else ''
        comp=re.sub(r'\s+\d{4}/\d{2}$', '', comp).strip()
        finished=max(rounds_with_results) if rounds_with_results else None
        played=sum(1 for m in league_matches if parse_score(m.get('result')))
        if finished:
            updated_at=f'Aktueller Stand (bis {finished}. Spieltag)'
        else:
            updated_at=f'Aktueller Stand ({played} Spiele)'
        entry={'competition':comp,'updated_at':updated_at,'rows':rows}
        if tables.get(team_key)!=entry:
            tables[team_key]=entry
            changed=True
    if changed:
        save_json(DATA/'tables.json', tables)
        print(f"Tabellen aktualisiert ({sum(1 for k in ('regionalliga','u23','u21','u19') if tables.get(k))} Mannschaften).")
    return tables


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

def youtube_search_url(game):
    query = f"{game.get('home','')} {game.get('away','')} OSTSPORT.TV"
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


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
    if str(url).startswith('/assets/clubs/') or str(url).startswith('/assets/'):
        return str(url)
    folder=DOCS/'assets'/'clubs'
    folder.mkdir(parents=True,exist_ok=True)
    filename=_safe_logo_filename(team,str(url))
    target=folder/filename
    if target.exists() and target.stat().st_size>200:
        return '/assets/clubs/'+filename
    # Offline rebuilds must still resolve already cached crests even when the
    # configured source URL is external (favicon CDN, Netlify, …).
    slug=Path(filename).stem
    for existing in sorted(folder.glob(slug+'.*')):
        if existing.is_file() and existing.stat().st_size>200:
            return '/assets/clubs/'+existing.name
    if os.environ.get('RSV_OFFLINE') == '1':
        return ''
    try:
        r=requests.get(str(url),headers={'User-Agent':UA,'Accept':'image/*'},timeout=20)
        r.raise_for_status()
        ctype=(r.headers.get('content-type') or '').lower()
        min_size=40 if ('favicon' in str(url) or 'gstatic.com' in str(url)) else 200
        if not r.content or len(r.content)<min_size or ('image' not in ctype and 'octet-stream' not in ctype and not str(url).lower().endswith(('.svg','.png','.ico','.jpg','.jpeg','.webp'))):
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

def resolve_logo(team, explicit_url='', clubs=None, discovered=None):
    """Prefer a same-origin crest; fall back to configured/discovered sources."""
    clubs=clubs if clubs is not None else load_clubs()
    discovered=discovered or {}
    canonical=canonical_club_name(team)
    for candidate in (
        explicit_url,
        discovered.get(canonical),
        discovered.get(team),
        (clubs.get(canonical) or clubs.get(team) or {}).get('logo_url'),
    ):
        cached=cache_logo(canonical, candidate)
        if cached:
            return cached
    parent=re.sub(r'\s+(?:U19|U21|U23|I|II|III|1)$','',canonical).strip()
    if parent and parent != canonical:
        return cache_logo(parent, (clubs.get(parent) or {}).get('logo_url')) or ''
    return ''


def club_logo_url(team, clubs, discovered=None):
    return resolve_logo(team, '', clubs, discovered)


def enrich_team_stats(meta, games, standings=None):
    """Add cumulative RSV points and table position after completed league games."""
    team = meta.get('team_name', '')
    positions={canonical_club_name(str(r.get('team','')).strip()): r.get('position') for r in (standings or {}).get('rows') or [] if r.get('team')}
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
            pos=positions.get(canonical_club_name(team))
            if pos not in (None, ''):
                g['table_position']=pos
        enriched.append(g)
    return enriched


def ics_uid(game):
    """UID changes when kickoff moves so Google/Apple pick up reschedules reliably."""
    gid=str(game.get('id') or 'game')
    date=str(game.get('date') or '').replace('-', '')
    time=str(game.get('time') or '14:00').replace(':', '')
    return f'{gid}-{date}T{time}@rsv-kalender'


def make_ics(meta, games, calendar_key=''):
    now=datetime.now(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//RSV Eintracht Kalender//DE','CALSCALE:GREGORIAN','METHOD:PUBLISH',f"X-WR-CALNAME:{esc(meta['calendar_name'])}",'X-PUBLISHED-TTL:PT6H']
    venues = load_venues()
    venue_cache = load_venue_cache()
    clubs = load_clubs()
    is_first_team = bool(meta.get('first_team')) or 'Regionalliga' in meta.get('calendar_name','')
    games = enrich_team_stats(meta, assign_matchdays(games))
    for g in games:
        kickoff=g.get('time') or '14:00'
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
        home_logo=club_logo_url(g.get('home',''), clubs)
        away_logo=club_logo_url(g.get('away',''), clubs)

        # Keep ICS text Apple-Calendar-safe: no emoji (folding/ZWJ breaks subscriptions).
        desc=[first_line, comp, pairing, status_line, '']
        if g.get('result'):
            if g.get('table_position') not in (None, ''):
                desc.append(f"Tabellenplatz: {g['table_position']}.")
            if g.get('points') not in (None, ''):
                desc.append(f"Punkte: {g['points']}")
            if g.get('scorers'):
                desc.extend(['', 'Tore RSV'])
                if isinstance(g['scorers'], list):
                    desc.extend(str(x) for x in g['scorers'])
                else:
                    desc.append(str(g['scorers']))
            if g.get('referee'):
                desc.extend(['', f"Schiedsrichter: {g['referee']}"])
            if g.get('attendance') not in (None, ''):
                desc.append(f"Zuschauer: {g['attendance']}")
        if location:
            desc.extend(['', f"Spielort: {location}"])
            if map_link:
                desc.append(f"Google Maps: {map_link}")
        else:
            desc.extend(['', 'Spielort: noch nicht hinterlegt'])

        if is_first_team and g.get('result'):
            video=g.get('youtube_url') or youtube_search_url(g)
            label='OSTSPORT.TV-Beitrag' if g.get('youtube_url') else 'OSTSPORT.TV-Beitrag suchen'
            desc.extend(['', f"{label}: {video}"])

        if g.get('report_url'):
            desc.extend(['', f"Spielbericht: {g['report_url']}"])
        if g.get('source_url'):
            desc.extend(['', f"Quelle: {g['source_url']}"])

        event_lines = [
            'BEGIN:VEVENT',
            f"UID:{ics_uid(g)}",
            f'DTSTAMP:{now}',
            f"DTSTART:{start.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
            'SEQUENCE:1',
            f'SUMMARY:{esc(ics_plain(summary))}',
            f'DESCRIPTION:{esc(ics_plain(chr(10).join(desc)))}',
        ]
        if location:
            event_lines.append(f'LOCATION:{esc(ics_plain(location))}')
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
    """Load live round pairings and merge curated cup rounds as fallback.

    Curated entries in ``data/cup-rounds.json`` fill gaps when FUSSBALL.DE has not
    published a full cup bracket yet. Live groups with more pairings always win.
    """
    path=DATA/'rounds.json'
    payload=load_json(path) if path.exists() else {}
    cup_path=DATA/'cup-rounds.json'
    if not cup_path.exists():
        return payload
    curated=load_json(cup_path)
    if not isinstance(curated, dict):
        return payload
    for key, groups in curated.items():
        if not isinstance(groups, list):
            continue
        existing=payload.get(key, [])
        by_id={str(x.get('id')):x for x in existing if x.get('id')}
        for group in groups:
            gid=str(group.get('id') or '')
            if not gid:
                continue
            current=by_id.get(gid)
            if current and len(current.get('matches') or []) >= len(group.get('matches') or []):
                continue
            by_id[gid]=group
        # Keep non-id items, then merged by id.
        rest=[x for x in existing if not x.get('id')]
        payload[key]=rest+list(by_id.values())
    return payload


def parse_dfb_matchday(html, matchday, competition='Regionalliga Nordost'):
    """Parse all fixtures of one DFB Datencenter matchday page."""
    soup=BeautifulSoup(html,'html.parser')
    out=[]
    for desc in soup.select('.c-MatchTable-description'):
        node=desc
        for _ in range(6):
            node=node.parent
            if not node: break
            if node.select_one('.c-MatchTable-team--home') and node.select_one('.c-MatchTable-team--away'):
                break
        if not node: continue
        home_tag=node.select_one('.c-MatchTable-team--home a')
        away_tag=node.select_one('.c-MatchTable-team--away a')
        score_tag=node.select_one('.c-MatchTable-score')
        home=_clean_team_name(home_tag.get_text(' ',strip=True) if home_tag else '')
        away=_clean_team_name(away_tag.get_text(' ',strip=True) if away_tag else '')
        if not home or not away: continue
        date_text=desc.get_text(' ',strip=True)
        dm=re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', date_text)
        score_text=re.sub(r'\s','', score_tag.get_text(' ',strip=True) if score_tag else '')
        result=score_text if re.fullmatch(r'\d+:\d+', score_text or '') else None
        date=datetime.strptime(dm.group(1),'%d.%m.%Y').strftime('%Y-%m-%d') if dm else ''
        time=dm.group(2) if dm else ''
        mid=hashlib.sha1(f'{date}|{home}|{away}|{matchday}'.encode()).hexdigest()[:12]
        out.append({
            'id':f'rl-md{matchday}-{mid}',
            'date':date,'time':time,'home':home,'away':away,
            'result':result,'halftime_result':None,'location':'',
            'matchday':int(matchday),'competition':f'{competition} 2026/27',
        })
    return out


def fetch_regionalliga_rounds(expected_matchdays=34):
    """Refresh full matchday pairings for Regionalliga Nordost from DFB."""
    if os.environ.get('RSV_OFFLINE') == '1':
        return load_round_pairings()
    competition='Regionalliga Nordost'
    groups=[]
    for md in range(1, int(expected_matchdays)+1):
        url=f'https://datencenter.dfb.de/competitions/regionalliga-nordost/seasons/2026-2027/matchday/{md}'
        try:
            matches=parse_dfb_matchday(fetch(url), md, competition)
        except Exception as exc:
            warnings.warn(f'Spieltag {md} konnte nicht geladen werden: {exc}')
            continue
        if not matches:
            continue
        groups.append({
            'id':f'league:{competition}:{md}',
            'kind':'league',
            'title':f'{md}. Spieltag {competition}',
            'competition':competition,
            'round':str(md),
            'matches':matches,
        })
    if not groups:
        return load_round_pairings()
    payload=load_round_pairings()
    # Keep previously fetched Landespokal/cup pairings for the same team key.
    cups=[x for x in payload.get('regionalliga', []) if x.get('kind') == 'cup']
    payload['regionalliga']=groups+cups
    fussball_url=regionalliga_fussball_url()
    if fussball_url:
        try:
            fussball_games=dedupe(parse_fussball(fetch(fussball_url), 'RSV Eintracht 1949', fussball_url))
            payload=overlay_fussball_round_pairings(payload, fussball_games)
        except Exception as exc:
            warnings.warn(f'FUSSBALL.DE Spieltags-Termine konnten nicht übernommen werden: {exc}')
    save_json(DATA/'rounds.json', payload)
    print(f'Regionalliga: {len(groups)} Spieltage mit Gesamtpaarungen übernommen')
    return payload


def round_label_from_spieltag_url(url):
    """Derive a human round label from a FUSSBALL.DE /spieltag/ slug."""
    slug=(url or '').split('/spieltag/',1)[-1].split('/',1)[0].casefold()
    if not slug:
        return ''
    patterns=(
        (r'(\d+)-runde', lambda m: f'{int(m.group(1))}. Runde'),
        (r'(\d+)-hauptrunde', lambda m: f'{int(m.group(1))}. Hauptrunde'),
        (r'achtelfinale', lambda _m: 'Achtelfinale'),
        (r'viertelfinale', lambda _m: 'Viertelfinale'),
        (r'halbfinale', lambda _m: 'Halbfinale'),
        (r'(?:endspiel|finale)\b', lambda _m: 'Finale'),
        (r'qualifikation', lambda _m: 'Qualifikation'),
    )
    for pat, fmt in patterns:
        m=re.search(pat, slug)
        if m:
            return fmt(m)
    return ''


def extract_cup_meta_from_match_html(html):
    """Read cup round label + round overview URL from a match detail page."""
    soup=BeautifulSoup(html,'html.parser')
    for a in soup.find_all('a', href=True):
        href=_absolute_fussball_url(a.get('href',''))
        if '/spieltag/' not in href:
            continue
        label=round_label_from_spieltag_url(href)
        if label:
            return {'round':label,'round_url':href.split('#',1)[0]}
    return {}


def parse_fussball_round_fixtures(html, competition=''):
    """Parse every pairing from a FUSSBALL.DE cup/league round page."""
    soup=BeautifulSoup(html,'html.parser')
    out=[]; current_date=''
    for row in soup.select('table tr'):
        classes=set(row.get('class') or [])
        row_text=' '.join(row.get_text(' ',strip=True).split())
        if 'row-headline' in classes or (
            'visible-small' in classes and not row.select_one('td.column-score')
        ):
            dm=re.search(r'(\d{2}\.\d{2}\.\d{4})', row_text)
            if dm:
                current_date=datetime.strptime(dm.group(1),'%d.%m.%Y').strftime('%Y-%m-%d')
            continue
        score_cell=row.select_one('td.column-score')
        clubs=row.select('td.column-club')
        if not score_cell or len(clubs)<2:
            continue
        date_cell=row.select_one('td.column-date')
        date_text=' '.join(date_cell.get_text(' ',strip=True).split()) if date_cell else ''
        time=''
        dm=re.search(
            r'(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?[,]?\s*(\d{2}\.\d{2}\.(?:\d{2}|\d{4}))\s*\|\s*(\d{2}:\d{2})',
            date_text, re.I,
        )
        if dm:
            raw=dm.group(1)
            fmt='%d.%m.%Y' if len(raw.rsplit('.',1)[-1])==4 else '%d.%m.%y'
            current_date=datetime.strptime(raw,fmt).strftime('%Y-%m-%d')
            time=dm.group(2)
        else:
            tm=re.search(r'(\d{2}:\d{2})', date_text)
            time=tm.group(1) if tm else ''
        home,home_logo=_extract_team_cell(clubs[0])
        away,away_logo=_extract_team_cell(clubs[1])
        home=PUA_RE.sub('', home).strip()
        away=PUA_RE.sub('', away).strip()
        if not home or not away or not current_date:
            continue
        link=score_cell.find('a', href=True) or row.find('a', href=re.compile(r'/spiel/'))
        detail=_absolute_fussball_url(link.get('href','') if link else '')
        number=_match_number_from_link(detail) or hashlib.sha1(
            f'{current_date}|{home}|{away}|{competition}'.encode()
        ).hexdigest()[:12]
        out.append({
            'id':f'cup-{number}',
            'date':current_date,'time':time,
            'home':home,'away':away,
            'result':_plain_score(score_cell),'halftime_result':None,'location':'',
            'matchday':None,'competition':competition,
            'home_logo':home_logo,'away_logo':away_logo,
            'source_url':detail,
        })
    return out


def _cup_detail_url(game, team_page_urls=None):
    url=str(game.get('source_url') or '')
    if '/spiel/' in url:
        return url.split('#',1)[0]
    # Print pages often omit the match deep-link; recover it from the team page.
    home=normalize_match_name(game.get('home',''))
    away=normalize_match_name(game.get('away',''))
    date=game.get('date','')
    for page_url in team_page_urls or []:
        if 'fussball.de' not in page_url or 'druck' in page_url:
            continue
        try:
            soup=BeautifulSoup(deobfuscate_fussball_html(fetch(page_url)),'html.parser')
        except Exception:
            continue
        for a in soup.find_all('a', href=True):
            href=_absolute_fussball_url(a.get('href',''))
            if '/spiel/' not in href:
                continue
            ctx=' '.join((a.find_parent(['tr','li','div','article']) or a).get_text(' ',strip=True).split())
            ctx_key=normalize_match_name(ctx)
            if home and home not in ctx_key:
                continue
            if away and away not in ctx_key:
                continue
            if date:
                # Accept either ISO or German date fragments near the fixture.
                y,m,d=date.split('-')
                if f'{d}.{m}.{y}' not in ctx and f'{d}.{m}.{y[2:]}' not in ctx and date not in ctx:
                    # Slug match is still useful when the date is elsewhere in the row.
                    slug=href.casefold()
                    if normalize_match_name(game.get('home','')).split()[0] not in slug and 'eintracht' not in slug:
                        continue
            return href.split('#',1)[0]
    return ''


def fetch_cup_rounds(team_key, games, team_page_urls=None):
    """Attach cup round labels and full round pairings from FUSSBALL.DE.

    Returns ``(games, payload, changed)`` so callers can persist updated round fields.
    Falls back to curated ``data/cup-rounds.json`` via ``load_round_pairings``.
    """
    payload=load_round_pairings()
    if os.environ.get('RSV_OFFLINE') == '1':
        # Still apply curated round labels onto games when offline.
        changed=_apply_cup_labels_from_payload(team_key, games, payload)
        return games, payload, changed
    cup_games=[g for g in games if 'pokal' in competition_label(g.get('competition','')).casefold()]
    if not cup_games:
        return games, payload, False

    cup_groups={}
    changed=False
    fetched_rounds=set()
    for game in cup_games:
        detail=_cup_detail_url(game, team_page_urls)
        round_url=str(game.get('round_url') or '')
        label=str(game.get('round') or game.get('cup_round') or '').strip()
        meta={}
        if detail:
            try:
                match_html=deobfuscate_fussball_html(fetch(detail))
                meta=extract_cup_meta_from_match_html(match_html)
            except Exception as exc:
                warnings.warn(f'Pokal-Detailseite nicht lesbar ({detail}): {exc}')
            if meta.get('round'):
                label=meta['round']
            if meta.get('round_url'):
                round_url=meta['round_url']
            if detail and game.get('source_url') != detail and '/spiel/' in detail:
                game['source_url']=detail
                changed=True
        if label and game.get('round') != label:
            game['round']=label
            changed=True
        if round_url and game.get('round_url') != round_url:
            game['round_url']=round_url
            changed=True
        if not label or not round_url or round_url in fetched_rounds:
            continue
        fetched_rounds.add(round_url)
        comp=competition_label(game.get('competition',''))
        try:
            matches=parse_fussball_round_fixtures(
                deobfuscate_fussball_html(fetch(round_url)),
                competition=f'{comp} 2026/27' if comp else '',
            )
        except Exception as exc:
            warnings.warn(f'Pokalrunde nicht lesbar ({round_url}): {exc}')
            continue
        if not matches:
            continue
        gid=f'cup:{comp}:{label}'
        cup_groups[gid]={
            'id':gid,
            'kind':'cup',
            'title':f'{label} – {comp}',
            'competition':comp,
            'round':label,
            'matches':matches,
        }

    if cup_groups:
        existing=[x for x in payload.get(team_key, []) if x.get('kind') != 'cup']
        old_cups={x['id']:x for x in payload.get(team_key, []) if x.get('kind') == 'cup' and x.get('id')}
        old_cups.update(cup_groups)
        payload[team_key]=existing+list(old_cups.values())
        save_json(DATA/'rounds.json', payload)
        print(f'{team_key}: {len(cup_groups)} Pokalrunde(n) mit Gesamtpaarungen übernommen')
    # Ensure curated labels/groups remain available when live fetch finds nothing.
    payload=load_round_pairings()
    changed=_apply_cup_labels_from_payload(team_key, games, payload) or changed
    return games, payload, changed or bool(cup_groups)


def _apply_cup_labels_from_payload(team_key, games, payload):
    """Copy round labels from stored cup groups onto matching team fixtures."""
    changed=False
    groups=[g for g in payload.get(team_key, []) if g.get('kind') == 'cup']
    for game in games:
        if 'pokal' not in competition_label(game.get('competition','')).casefold():
            continue
        if game.get('round') and game.get('round') != 'Pokalrunde':
            continue
        for group in groups:
            matches=group.get('matches') or []
            hit=any(
                (x.get('id') and x.get('id') == game.get('id'))
                or (
                    x.get('date') == game.get('date')
                    and normalize_match_name(x.get('home','')) == normalize_match_name(game.get('home',''))
                    and normalize_match_name(x.get('away','')) == normalize_match_name(game.get('away',''))
                )
                or (
                    x.get('date') == game.get('date')
                    and (
                        normalize_match_name(x.get('away','')) == normalize_match_name(game.get('away',''))
                        or normalize_match_name(x.get('home','')) == normalize_match_name(game.get('home',''))
                    )
                    and (
                        'eintracht' in normalize_match_name(x.get('home','') + ' ' + x.get('away',''))
                    )
                )
                for x in matches
            )
            if hit and group.get('round'):
                game['round']=group['round']
                changed=True
                break
    return changed


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
            m['home_logo']=resolve_logo(m.get('home',''), m.get('home_logo',''), clubs, discovered_logos)
            m['away_logo']=resolve_logo(m.get('away',''), m.get('away_logo',''), clubs, discovered_logos)
        grp['matches'].sort(key=lambda x:(x.get('date') or '',x.get('time') or '00:00',x.get('home') or ''))
        dates=[m.get('date') for m in grp['matches'] if m.get('date')]
        grp['date']=min(dates) if dates else ''
        out.append(grp)
    return sorted(out,key=lambda x:(x.get('date') or '',x.get('title') or ''))

def overlay_fussball_schedule(dfb_games, fussball_games):
    """Apply FUSSBALL.DE kickoff dates onto DFB fixtures matched by home/away."""
    fb_by_pair=_fussball_schedule_index(fussball_games)
    out=[]
    updated=0
    for original in dfb_games:
        g=deepcopy(original)
        if not is_league_game(g):
            out.append(g)
            continue
        fb=fb_by_pair.get((normalize_match_name(g['home']), normalize_match_name(g['away'])))
        if not fb:
            out.append(g)
            continue
        if fb.get('date') and fb.get('date') != g.get('date'):
            g['date']=fb['date']
            updated += 1
        if fb.get('time'):
            g['time']=fb['time']
        if fb.get('match_number'):
            g['match_number']=fb['match_number']
        fb_url=str(fb.get('source_url') or '')
        if fb_url and '/spiel/' in fb_url:
            g['source_url']=fb_url
        out.append(g)
    if updated:
        print(f'FUSSBALL.DE: {updated} Regionalliga-Termin(e) auf aktuelle Anstoßzeit gelegt')
    return sorted(out, key=lambda x:(x['date'], x.get('time','00:00')))


def _fussball_schedule_index(fussball_games):
    fb_by_pair={}
    for g in fussball_games:
        if not is_league_game(g):
            continue
        comp=competition_label(g.get('competition','')).casefold()
        if 'regionalliga' not in comp:
            continue
        fb_by_pair[(normalize_match_name(g['home']), normalize_match_name(g['away']))]=g
    return fb_by_pair


def overlay_fussball_round_pairings(payload, fussball_games):
    """Sync Spieltags-Paarungen in rounds.json with FUSSBALL.DE kickoff times."""
    fb_by_pair=_fussball_schedule_index(fussball_games)
    if not fb_by_pair:
        return payload
    updated=0
    for group in payload.get('regionalliga', []):
        if group.get('kind') != 'league':
            continue
        for match in group.get('matches', []):
            fb=fb_by_pair.get((normalize_match_name(match.get('home','')), normalize_match_name(match.get('away',''))))
            if not fb:
                continue
            if fb.get('date') and fb.get('date') != match.get('date'):
                match['date']=fb['date']
                updated += 1
            if fb.get('time'):
                match['time']=fb['time']
    if updated:
        print(f'FUSSBALL.DE: {updated} Spieltags-Termin(e) in rounds.json aktualisiert')
    return payload


def regionalliga_fussball_url():
    meta=load_json(DATA/'regionalliga.json')
    for url in meta.get('source_urls') or []:
        if 'fussball.de' in url:
            return url
    return ''


def filter_official_fussball_fixtures(games, meta=None):
    """Drop historical/noise rows from FUSSBALL.DE team pages (text fallback junk)."""
    meta=meta or {}
    if not meta.get('require_numeric_match_number'):
        return games
    kept=[g for g in games if re.fullmatch(r'\d{6,}', str(g.get('match_number') or ''))]
    dropped=len(games)-len(kept)
    if dropped:
        print(f"{meta.get('team_name','Team')}: {dropped} veraltete/ungültige Termine aus FUSSBALL.DE ausgefiltert")
    return kept


def build_site_data(team_configs, ticket_events=None):
    """Create the JSON used by the results, upcoming matches and table view."""
    payload={'generated_at': datetime.now(TZ).isoformat(), 'teams':{}, 'calendar_teams':{}, 'tables': load_json(DATA/'tables.json') if (DATA/'tables.json').exists() else {}, 'club_websites': {name: info.get('website','') for name, info in load_clubs().items() if isinstance(info, dict) and info.get('website')}, 'club_aliases': load_club_aliases()}
    venues = load_venues()
    venue_cache = load_venue_cache()
    clubs = load_clubs()
    all_games=[g for _key,_meta,gs in team_configs for g in gs]
    discovered_logos=game_logo_candidates(all_games)
    ticket_events = ticket_events or []
    today = datetime.now(TZ).date()

    for key, meta, games in team_configs:
        calendar_only=bool(meta.get('calendar_only'))
        standings=payload.get('tables', {}).get(key) or {}
        enriched=enrich_team_stats(meta, assign_matchdays(games), standings)
        completed=[]
        future=[]
        fixtures=[]
        team_name=meta.get('team_name','')

        for g in enriched:
            comp=competition_label(g.get('competition',''))
            is_non_league=any(x in comp.lower() for x in ('pokal','freundschaft','testspiel'))
            location=venue_for_game(g, venues, venue_cache)
            # Alle Wettbewerbe gehören in die vollständige Terminliste.
            home=_clean_team_name(g.get('home','')); away=_clean_team_name(g.get('away',''))
            home_logo=resolve_logo(home, g.get('home_logo',''), clubs, discovered_logos)
            away_logo=resolve_logo(away, g.get('away_logo',''), clubs, discovered_logos)
            fixtures.append({
                    'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                    'competition':comp, 'home':home, 'away':away,
                    'home_logo':home_logo, 'away_logo':away_logo,
                    'result':g.get('result') or '', 'location':location, 'maps_url':maps_url(location),
                    'is_home':home == team_name,
                    'round':g.get('round') or g.get('cup_round') or '',
                    'ticket_url':ticket_url_for_game(g, team_name, ticket_events) if key=='regionalliga' and not calendar_only and not g.get('result') and str(g.get('date','')) >= today.isoformat() else ''
            })

            if calendar_only:
                continue

            if g.get('result'):
                completed.append({
                    'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                    'competition':comp, 'home':home, 'away':away,
                    'home_logo':home_logo, 'away_logo':away_logo,
                    'result':g.get('result'), 'halftime_result':g.get('halftime_result') or g.get('halftime') or '', 'scorers':g.get('scorers') or [],
                    'attendance':g.get('attendance'), 'referee':g.get('referee'),
                    'location':location,
                    'maps_url':maps_url(location),
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

            future.append({
                'id':g.get('id'), 'matchday':g.get('matchday'), 'date':g.get('date'), 'time':g.get('time'),
                'competition':comp, 'home':home, 'away':away,
                'home_logo':home_logo, 'away_logo':away_logo,
                'location':location, 'maps_url':maps_url(location),
                'is_home':g.get('home') == team_name,
                'round':g.get('round') or g.get('cup_round') or '',
                'ticket_url':ticket_url_for_game(g, team_name, ticket_events) if key=='regionalliga' else ''
            })

        completed.sort(key=lambda x: (x.get('date') or '', x.get('time') or '00:00'))
        fixtures.sort(key=lambda x: (x.get('date') or '', x.get('time') or '00:00'))
        future.sort(key=lambda x: (x.get('date') or '', x.get('time') or '00:00'))
        next_game=future[0] if future else None
        if calendar_only:
            upcoming=[f for f in fixtures if not f.get('result') and str(f.get('date') or '') >= today.isoformat()]
            payload['calendar_teams'][key]={
                'name':meta.get('calendar_name',''),
                'team_name':team_name,
                'competition':competition_label(meta.get('games',[{}])[0].get('competition','')) if meta.get('games') else '',
                'ics_file':'hertha-bsc.ics',
                'fixtures':fixtures,
                'next_game':upcoming[0] if upcoming else None,
            }
            continue
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
        if meta.get('calendar_only'):
            continue
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
        if meta.get('calendar_only'):
            continue
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
    write_site_data(payload)

def site_data_fingerprint(payload):
    clone=deepcopy(payload)
    clone.pop('generated_at', None)
    return json.dumps(clone, ensure_ascii=False, sort_keys=True)

def write_site_data(payload):
    path=DOCS/'site-data.json'
    fingerprint=site_data_fingerprint(payload)
    if path.exists():
        try:
            existing=json.loads(path.read_text(encoding='utf-8'))
            if site_data_fingerprint(existing)==fingerprint:
                return False
        except Exception:
            pass
    payload=deepcopy(payload)
    payload['generated_at']=datetime.now(TZ).isoformat()
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return True

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
    # Ignore inflated local counts from stale duplicate rows above the season size.
    reference = max(expected, existing_league if not expected or existing_league <= expected else expected)
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
            dfb_urls=[u for u in urls if 'datencenter.dfb.de' in u]
            fussball_urls=[u for u in urls if 'fussball.de' in u]
            other_urls=[u for u in urls if u not in dfb_urls and u not in fussball_urls]
            parsed=[]
            dfb_parsed=[]
            fussball_parsed=[]
            source_errors=[]
            expected=int(meta.get('expected_league_games') or 0)
            for url in dfb_urls + other_urls:
                try:
                    html=fetch(url)
                    batch=parse_dfb(html,meta['team_name']) if 'datencenter.dfb.de' in url else parse_fussball(html,meta['team_name'],url)
                    parsed += batch
                    if 'datencenter.dfb.de' in url:
                        dfb_parsed += batch
                except Exception as source_exc:
                    source_errors.append(f'{url}: {source_exc}')
            for url in fussball_urls:
                try:
                    html=fetch(url)
                    batch=parse_fussball(html,meta['team_name'],url)
                    parsed += batch
                    fussball_parsed += batch
                    if expected and (
                        'vereinsspielplan.druck' in url or 'mode/PRINT' in url.upper()
                    ) and league_game_count(dedupe(parsed)) >= expected:
                        break
                except Exception as source_exc:
                    source_errors.append(f'{url}: {source_exc}')
            schedule_source=dedupe(dfb_parsed) if dfb_parsed else dedupe(parsed)
            if dfb_parsed and fussball_parsed:
                schedule_source=overlay_fussball_schedule(schedule_source, dedupe(fussball_parsed))
            remote=schedule_source if dfb_parsed else dedupe(parsed)
            validate_schedule_completeness(key, meta, games, schedule_source if dfb_parsed else remote, source_errors)
        except Exception as e: err=str(e); remote=[]
    venue_cache=load_venue_cache()
    merged=merge(games,remote)
    merged=apply_overrides(key,merged,load_json(DATA/'overrides.json'))
    merged=filter_official_fussball_fixtures(merged, meta)
    if key=='regionalliga':
        merged=enrich_dfb_match_details(merged, offline=offline)
    else:
        merged=enrich_scores_from_detail_pages(merged, offline=offline)
    merged=apply_venue_cache(merged,venue_cache)
    merged=enrich_locations_from_detail_pages(merged, offline=offline)
    merged=enrich_locations_from_known_venues(merged, venue_cache)
    merged=drop_incomplete_locations(merged)
    update_venue_cache(merged,venue_cache)
    save_json(DATA/'venue-cache.json',venue_cache)
    validate_merged_schedule(key, meta, merged)
    # Persist only when remote passed validation; baseline remains source of truth.
    if remote or meta.get('calendar_only'):
        meta['games']=merged; save_json(path,meta)
    DOCS.mkdir(exist_ok=True)
    out_names={'regionalliga':'rsv-regionalliga.ics','u23':'rsv-u23.ics','u21':'rsv-u21.ics','u19':'rsv-u19.ics','hertha-bsc':'hertha-bsc.ics'}
    out=DOCS/out_names[key]
    # newline='' needs Python 3.10+; write bytes for broader compatibility.
    out.write_bytes(make_ics(meta,merged,key).encode('utf-8'))
    print(f'{key}: {len(merged)} Termine erzeugt'+(f' (Online-Update übersprungen: {err})' if err else ''))
    return err is None or bool(merged)

def restore_live_state() -> None:
    if not os.environ.get('NETLIFY_SITE_ID') or not os.environ.get('NETLIFY_AUTH_TOKEN'):
        return
    import subprocess
    subprocess.run(['node', 'scripts/restore-live-state.mjs'], cwd=ROOT, check=False)


def ci_should_update() -> bool:
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return True
    if os.environ.get('RSV_FORCE_UPDATE') == '1':
        return True
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'should-update.py'), '--exit-code'],
        cwd=ROOT,
    )
    return result.returncode == 0


def publish_live_data() -> None:
    site_id = os.environ.get('NETLIFY_SITE_ID')
    token = os.environ.get('NETLIFY_AUTH_TOKEN')
    if not site_id or not token:
        print('Netlify Blobs: Keine Credentials gesetzt – Live-Daten kommen beim nächsten Deploy in Blobs.')
        return
    import subprocess
    subprocess.run(['npm', 'install', '--silent'], cwd=ROOT, check=False)
    result = subprocess.run(['node', 'scripts/publish-live-data.mjs'], cwd=ROOT, env=os.environ)
    if result.returncode:
        print('Netlify Blobs: Veröffentlichung fehlgeschlagen', file=sys.stderr)
        raise SystemExit(result.returncode)
    print('Netlify Blobs: Live-Daten veröffentlicht.')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); args=ap.parse_args()
    if args.offline:
        os.environ['RSV_OFFLINE']='1'
    if not ci_should_update():
        print('Aktualisierung übersprungen (kein fälliger Auslöser).')
        return 0
    restore_live_state()
    ok=True; configs=[]
    ticket_events=fetch_ticket_events()
    for key in ('regionalliga','u23','u21','u19'):
        try:
            ok=process(key,args.offline) and ok
            meta=load_json(DATA/f'{key}.json')
            games=apply_overrides(key,meta.get('games',[]),load_json(DATA/'overrides.json'))
            team_pages=meta.get('source_urls') or ([meta.get('source_url','')] if meta.get('source_url') else [])
            games,_,cup_changed=fetch_cup_rounds(key, games, team_pages)
            if cup_changed:
                meta['games']=games
                save_json(DATA/f'{key}.json', meta)
            configs.append((key,meta,games))
        except Exception as e:
            print(f'{key}: FEHLER: {e}',file=sys.stderr); ok=False
    for key in ('hertha-bsc',):
        try:
            ok=process(key,args.offline) and ok
            meta=load_json(DATA/f'{key}.json')
            games=apply_overrides(key,meta.get('games',[]),load_json(DATA/'overrides.json'))
            configs.append((key,meta,games))
        except Exception as e:
            print(f'{key}: FEHLER: {e}',file=sys.stderr); ok=False
    try:
        meta=load_json(DATA/'regionalliga.json')
        fetch_regionalliga_rounds(int(meta.get('expected_league_games') or 34))
    except Exception as exc:
        warnings.warn(f'Regionalliga-Spieltage konnten nicht aktualisiert werden: {exc}')
    refresh_tables_from_rounds()
    build_site_data(configs, ticket_events)
    required=('rsv-regionalliga.ics','rsv-u23.ics','rsv-u21.ics','rsv-u19.ics','hertha-bsc.ics')
    if not ok:
        print('Mindestens eine Mannschaft konnte nicht vollständig aktualisiert werden; Veröffentlichung wird abgebrochen.', file=sys.stderr)
        return 1
    publish_live_data()
    return 0
if __name__=='__main__': raise SystemExit(main())
