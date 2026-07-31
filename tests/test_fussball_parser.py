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


def test_full_table():
    games=mod.parse_fussball(fixture_html(), 'RSV Eintracht 1949 U23','https://example.test')
    assert len(games)==30, len(games)
    assert games[0]['location'].startswith('Sportplatz')
    assert games[0]['home_logo'].startswith('https://')
    assert games[-1]['match_number'].startswith('ABC')


def test_result_and_short_date():
    html='''<table>
<tr class="visible-small"><td>So, 30.08.26 | 14:00 Kreisoberliga ME</td></tr>
<tr><td class="column-club-left"><span class="club-name">RSV Eintracht 1949 U23</span></td><td class="column-score"><a href="/spiel/X12345678">2 : 1</a></td><td class="column-club-right"><span class="club-name">Test FC</span></td></tr>
</table>'''
    games=mod.parse_fussball(html,'RSV Eintracht 1949 U23','https://example.test')
    assert len(games)==1
    assert games[0]['date']=='2026-08-30'
    assert games[0]['result']=='2:1'

if __name__=='__main__':
    test_full_table(); test_result_and_short_date(); print('OK')
