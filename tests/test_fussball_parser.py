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


def test_round_label_from_spieltag_url():
    assert mod.round_label_from_spieltag_url(
        'https://www.fussball.de/spieltag/runde-1-brandenburg-brandenburg-pokal-herren-saison2627-brandenburg/-/spieldatum/2026-08-22/staffel/031B3AU'
    ) == '1. Runde'
    assert mod.round_label_from_spieltag_url(
        'https://www.fussball.de/spieltag/1-runde-kreispokal-kreis-havelland-kreispokal-herren-saison2627-brandenburg/-/staffel/x'
    ) == '1. Runde'


def test_fussball_source_urls_ignore_dfb_and_prefer_print():
    urls=mod.fussball_source_urls({
        'source_url':'https://datencenter.dfb.de/competitions/regionalliga-nordost/seasons/2026-2027/teams/rsv-eintracht-1949',
        'source_urls':[
            'https://datencenter.dfb.de/competitions/regionalliga-nordost/seasons/2026-2027/teams/rsv-eintracht-1949',
            'https://www.fussball.de/mannschaft/rsv-eintracht-1949/-/team-id/1',
            'https://www.fussball.de/vereinsspielplan.druck/-/mode/PRINT/team-id/1',
        ],
    })
    assert urls[0].endswith('mode/PRINT/team-id/1')
    assert all('fussball.de' in u for u in urls)
    assert all('datencenter.dfb.de' not in u for u in urls)
    assert len(urls)==2


def test_placeholder_team_detection():
    assert mod.is_placeholder_team('Sieger aus einem Spiel')
    assert mod.is_placeholder_team('Sieger Spremberger SV / BSC Preußen 07 Blankenfelde-Mahlow')
    assert mod.is_placeholder_team('Sieger aus Spiel 710006071')
    assert not mod.is_placeholder_team('BSC Preußen 07')
    assert not mod.is_placeholder_team('RSV Eintracht 1949')


def test_merge_resolves_cup_placeholder():
    base=[{
        'id':'lp-01','date':'2026-08-22','time':'15:00',
        'home':'Sieger Spremberger SV / BSC Preußen 07 Blankenfelde-Mahlow',
        'away':'RSV Eintracht 1949','competition':'Landespokal Brandenburg 2026/27',
        'result':None,'location':'','source_url':'https://www.flb.de/',
    }]
    remote=[{
        'id':'u21-710006071','date':'2026-08-22','time':'15:00',
        'home':'BSC Preußen 07','away':'RSV Eintracht 1949',
        'competition':'Brandenburg-Pokal 2026/27','result':'0:2',
        'location':'Sportplatz Blankenfelde, Triftstr. 13-15, 15827 Blankenfelde-Mahlow',
        'source_url':'https://www.fussball.de/spiel/bsc-preussen-07-rsv-eintracht-1949/-/spiel/031DOF9STC000000VS5489BUVUR5FS5A',
        'match_number':'710006071',
    }]
    merged=mod.merge(base, remote)
    assert len(merged)==1
    game=merged[0]
    assert game['id']=='lp-01'
    assert game['home']=='BSC Preußen 07'
    assert game['away']=='RSV Eintracht 1949'
    assert game['result']=='0:2'
    assert game['competition']=='Landespokal Brandenburg 2026/27'
    assert '/spiel/' in game['source_url']
    assert 'Blankenfelde' in game['location']


def test_merge_keeps_resolved_name_over_placeholder():
    base=[{
        'id':'lp-01','date':'2026-08-22','time':'15:00',
        'home':'BSC Preußen 07','away':'RSV Eintracht 1949',
        'competition':'Landespokal Brandenburg 2026/27','result':'0:2','location':'',
        'source_url':'https://www.fussball.de/spiel/x',
    }]
    remote=[{
        'id':'u21-1','date':'2026-08-22','time':'15:00',
        'home':'Sieger aus einem Spiel','away':'RSV Eintracht 1949',
        'competition':'Landespokal Brandenburg 2026/27','result':None,'location':'','source_url':'',
    }]
    game=mod.merge(base, remote)[0]
    assert game['home']=='BSC Preußen 07'
    assert game['result']=='0:2'


def test_append_non_league_fussball_games():
    dfb=[{
        'id':'rl-05','date':'2026-08-14','time':'19:00',
        'home':'SV Babelsberg 03','away':'RSV Eintracht 1949',
        'competition':'Regionalliga Nordost 2026/27','result':'3:3',
    }]
    fussball=dfb+[{
        'id':'u21-710006071','date':'2026-08-22','time':'15:00',
        'home':'BSC Preußen 07','away':'RSV Eintracht 1949',
        'competition':'Brandenburg-Pokal 2026/27','result':'0:2',
    }]
    out=mod.append_non_league_fussball_games(dfb, fussball)
    assert len(out)==2
    cup=[g for g in out if g['date']=='2026-08-22'][0]
    assert cup['competition']=='Landespokal Brandenburg 2026/27'
    assert cup['result']=='0:2'


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
    test_round_label_from_spieltag_url()
    test_fussball_source_urls_ignore_dfb_and_prefer_print()
    test_placeholder_team_detection()
    test_merge_resolves_cup_placeholder()
    test_merge_keeps_resolved_name_over_placeholder()
    test_append_non_league_fussball_games()
    test_dedupe_prefers_numeric_match_id()
    print('OK')
