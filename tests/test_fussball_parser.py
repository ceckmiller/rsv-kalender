import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('update_calendars',ROOT/'update_calendars.py')
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def fixture_html(count=30):
    rows=[]
    for i in range(1,count+1):
        day=((i-1)%28)+1
        home='RSV Eintracht 1949 U23' if i%2 else f'Gegner {i}'
        away=f'Gegner {i}' if i%2 else 'RSV Eintracht 1949 U23'
        rows.append(f'''<tr class="visible-small"><td>Samstag, {day:02d}.08.2026 - 14:00 Uhr | Herren | Kreisoberliga</td></tr>
<tr><td class="column-club-left"><span data-responsive-image="//img/{i}h.png"></span><span class="club-name">{home}</span></td>
<td class="column-score"><a href="/spiel/ABC{i:06d}">- : -</a></td>
<td class="column-club-right"><span data-responsive-image="//img/{i}a.png"></span><span class="club-name">{away}</span></td></tr>
<tr><td colspan="3"><a class="location">Sportplatz {i}, Musterweg {i}, 14532 Stahnsdorf</a></td></tr>''')
    return '<table>'+''.join(rows)+'</table>'


def print_layout_html():
    return '''<table>
<tr class="row-headline visible-small"><td colspan="6">Sonntag, 30.08.2026 - 14:00 Uhr | Herren | Kreisliga</td></tr>
<tr class="row-competition hidden-small">
  <td class="column-date">So, 30.08.26 | 14:00</td>
  <td class="column-team" colspan="3"><a>Herren | Kreisliga</a></td>
  <td colspan="2"><a>ME | 610480004</a></td>
</tr>
<tr>
  <td class="column-club"><span class="club-name">RSV Eintracht 1949 U21</span></td>
  <td class="column-colon">:</td>
  <td class="column-club no-border"><span class="club-name">FV Turbine Potsdam 55 I</span></td>
  <td class="column-score"><a href="/spiel/rsv-eintracht-1949-u21-fv-turbine/-/spiel/031D5U7IOO000000VS5489BTVUS470OH">- : -</a></td>
</tr>
<tr class="hidden-small row-venue"><td colspan="6">Spielstätte:Sportplatz Heinrich-Zille-Str., KR | Heinrich-Zille-Str. 32 | 14532 Stahnsdorf</td></tr>
<tr class="row-headline visible-small"><td colspan="6">Sonntag, 16.08.2026 - 10:30 Uhr | Herren | Kreispokal</td></tr>
<tr class="row-competition hidden-small">
  <td class="column-date">So, 16.08.26 | 10:30</td>
  <td class="column-team" colspan="3"><a>Herren | Kreispokal</a></td>
  <td colspan="2"><a>PO | 710089011</a></td>
</tr>
<tr>
  <td class="column-club"><span class="club-name">Rot-Weiß Groß Glienicke II</span></td>
  <td class="column-colon">:</td>
  <td class="column-club no-border"><span class="club-name">RSV Eintracht 1949 U21</span></td>
  <td class="column-score"><a href="/spiel/example/-/spiel/031F066OOS000000VS5489BTVUS470OH">- : -</a></td>
</tr>
<tr class="hidden-small row-venue"><td colspan="6">Spielstätte:Sportplatz Groß Glienicke | An der Sporthalle | 14476 Potsdam</td></tr>
</table>'''


def test_full_table():
    games=mod.parse_fussball(fixture_html(), 'RSV Eintracht 1949 U23','https://example.test')
    assert len(games)==30, len(games)
    assert games[0]['location'].startswith('Sportplatz')
    assert games[0]['home_logo'].startswith('https://')
    assert games[-1]['match_number'].startswith('ABC')
    assert games[0]['competition'].startswith('Kreisoberliga')


def test_result_and_short_date():
    html='''<table>
<tr class="visible-small"><td>So, 30.08.26 | 14:00 Kreisoberliga ME</td></tr>
<tr><td class="column-club-left"><span class="club-name">RSV Eintracht 1949 U23</span></td><td class="column-score"><a href="/spiel/X12345678">2 : 1</a></td><td class="column-club-right"><span class="club-name">Test FC</span></td></tr>
</table>'''
    games=mod.parse_fussball(html,'RSV Eintracht 1949 U23','https://example.test')
    assert len(games)==1
    assert games[0]['date']=='2026-08-30'
    assert games[0]['result']=='2:1'


def test_print_layout_match_ids_and_competitions():
    games=mod.parse_fussball(print_layout_html(), 'RSV Eintracht 1949 U21', 'https://example.test/print')
    assert len(games)==2, games
    by_id={g['id']:g for g in games}
    assert 'u21-610480004' in by_id
    assert 'u21-710089011' in by_id
    assert by_id['u21-610480004']['competition'].startswith('Kreisliga')
    assert by_id['u21-710089011']['competition'].startswith('Kreispokal')
    assert by_id['u21-610480004']['location'].startswith('Sportplatz Heinrich-Zille')
    assert mod.league_game_count(games)==1


def test_dedupe_prefers_numeric_match_id():
    games=mod.dedupe([
        {
            'id':'u21-slug','date':'2026-08-30','time':'14:00',
            'home':'RSV Eintracht 1949 U21','away':'FV Turbine Potsdam 55 I',
            'competition':'Kreisliga 2026/27','result':None,'location':'',
            'source_url':'','match_number':'slug','home_logo':'','away_logo':''
        },
        {
            'id':'u21-610480004','date':'2026-08-30','time':'14:00',
            'home':'RSV Eintracht 1949 U21','away':'FV Turbine Potsdam 55 I',
            'competition':'Kreisliga 2026/27','result':None,'location':'Sportplatz',
            'source_url':'','match_number':'610480004','home_logo':'','away_logo':''
        },
    ])
    assert len(games)==1
    assert games[0]['match_number']=='610480004'
    assert games[0]['location']=='Sportplatz'


if __name__=='__main__':
    test_full_table()
    test_result_and_short_date()
    test_print_layout_match_ids_and_competitions()
    test_dedupe_prefers_numeric_match_id()
    print('OK')
