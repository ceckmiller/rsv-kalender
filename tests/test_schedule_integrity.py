import importlib.util
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('calendars', ROOT / 'update_calendars.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 16, 15, 0, tzinfo=mod.TZ).astimezone(tz)


def fixture(number, date, competition, result=None):
    return {'id': f'u23-{number}', 'match_number': str(number), 'date': date,
            'time': '14:00', 'home': 'RSV Eintracht 1949 U23',
            'away': 'Fortuna Babelsberg II', 'competition': competition,
            'result': result, 'location': ''}


def table_html():
    # Points can include association decisions; preserve the published values.
    return '''<table><tbody>
      <tr><td class="column-icon"></td><td class="column-rank">1.</td>
        <td class="column-club"><span class="club-name">Fortuna Babelsberg II</span></td>
        <td>6</td><td>3</td><td>2</td><td>1</td><td>14 : 9</td><td>5</td><td class="column-points">10</td></tr>
      <tr class="own"><td class="column-icon"></td><td class="column-rank">2.</td>
        <td class="column-club"><span class="club-name">RSV Eintracht 1949 U23</span></td>
        <td>6</td><td>1</td><td>3</td><td>2</td><td>11 : 14</td><td>-3</td><td class="column-points">6</td></tr>
    </tbody></table>'''


class ScheduleIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(mod, 'datetime', FixedDateTime)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.league = fixture(610138036, '2026-09-27', 'Kreisoberliga 2026/27', '3:3')
        self.cup = fixture(710089095, '2026-11-15', 'Kreispokal 2026/27')

    def test_league_and_cup_against_same_opponent_stay_separate(self):
        merged = mod.merge([self.league], [self.league, self.cup])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]['result'], '3:3')
        self.assertFalse(merged[1].get('result'))
        self.assertFalse(mod.fixtures_are_same_slot(self.league, self.cup))

    def test_repairs_already_corrupted_live_fixture(self):
        corrupt = {**self.cup, 'id': self.league['id'], 'result': '3:3',
                   'halftime_result': '2:1', 'scorers': ['Inherited scorer']}
        merged = mod.merge([corrupt], [self.league, self.cup])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]['id'], self.league['id'])
        self.assertEqual(merged[0]['date'], '2026-09-27')
        self.assertEqual(merged[1]['id'], self.cup['id'])
        self.assertNotIn('scorers', merged[1])
        self.assertNotIn('result', merged[1])

    def test_distinct_official_numbers_in_same_competition_stay_separate(self):
        second = {**self.cup, 'competition': self.league['competition']}
        self.assertEqual(len(mod.merge([self.league], [second])), 2)

    def test_official_number_deduplicates_old_manual_entry(self):
        old = {**self.league, 'id': 'u23-liga-20260927', 'date': '2026-09-28'}
        merged = mod.merge([old, self.league], [self.league])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['id'], self.league['id'])

    def test_reschedule_same_official_game_keeps_identity(self):
        moved = {**self.league, 'date': '2026-09-28'}
        merged = mod.merge([self.league], [moved])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['date'], '2026-09-28')

    def test_manual_date_id_remains_stable_and_keeps_details(self):
        manual = {**self.league, 'id': 'u23-liga-20260927', 'scorers': ['Published scorer']}
        merged = mod.merge([manual], [self.league])
        self.assertEqual(merged[0]['id'], manual['id'])
        self.assertEqual(merged[0]['scorers'], manual['scorers'])

    def test_dfb_and_fussball_regionalliga_labels_match(self):
        dfb = {**self.league, 'id': 'rl-05', 'competition': 'Regionalliga Nordost 2026/27'}
        dfb.pop('match_number')
        official = {**self.league, 'competition': 'Regionalliga 2026/27'}
        merged = mod.merge([dfb], [official])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['id'], 'rl-05')

    def test_round_sync_does_not_move_cup_to_league_date(self):
        groups = [{'kind': 'league', 'competition': 'Kreisoberliga', 'matches': [deepcopy(self.league)]},
                  {'kind': 'cup', 'competition': 'Kreispokal', 'matches': [deepcopy(self.cup)]}]
        synced = mod.sync_round_matches_with_team_schedule(groups, [self.league, self.cup])
        self.assertEqual(synced[0]['matches'][0]['date'], '2026-09-27')
        self.assertEqual(synced[1]['matches'][0]['date'], '2026-11-15')
        self.assertFalse(synced[1]['matches'][0].get('result'))

    def test_future_score_never_counts_in_standings(self):
        future = {**self.cup, 'result': '9:0'}
        rows = mod.compute_standings([self.league, future])
        self.assertTrue(all(row['played'] == 1 and row['points'] == 1 for row in rows))
        clean = mod.sanitize_game_results([{**future, 'halftime_result': '2:1', 'scorers': ['Wrong']}])
        self.assertNotIn('result', clean[0])
        self.assertNotIn('scorers', clean[0])

    def test_future_score_never_published_as_last_game_or_ics_result(self):
        games = [self.league, {**self.cup, 'result': '3:3', 'halftime_result': '2:1'}]
        meta = {'calendar_name': 'U23', 'team_name': self.league['home'], 'games': games}
        captured = []
        with patch.object(mod, 'write_site_data', captured.append), \
             patch.object(mod, 'resolve_logo', return_value=''), \
             patch.object(mod, 'club_logo_url', return_value=''), \
             patch.object(mod, 'load_round_pairings', return_value={}):
            mod.build_site_data([('u23', meta, games)])
        team = captured[0]['teams']['u23']
        self.assertEqual([g['date'] for g in team['matches']], ['2026-09-27'])
        self.assertEqual(team['next_game']['date'], '2026-11-15')
        self.assertFalse(team['fixtures'][1]['result'])
        ics = mod.make_ics(meta, games, 'u23').replace('\r\n ', '')
        future_event = ics.split('BEGIN:VEVENT')[2]
        self.assertNotIn('Endstand', future_event)
        self.assertIn('Anstoß: 14:00 Uhr', future_event)

    def test_reads_published_rank_and_points(self):
        rows = mod.parse_fussball_standings(table_html(), self.league['home'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['points'], 10)
        self.assertEqual(rows[1]['goals'], '11:14')
        self.assertEqual(rows[1]['diff'], '-3')
        self.assertEqual(rows[1]['position'], 2)

    def test_rejects_missing_or_broken_table(self):
        for html in ('<html>blocked</html>', table_html().replace('<td>6</td>', '<td>?</td>', 1)):
            with self.assertRaises(ValueError):
                mod.parse_fussball_standings(html, self.league['home'])

    def test_refresh_keeps_last_table_when_response_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            existing = {'u23': {'source': 'fussball.de', 'rows': [{'played': 6}], 'updated_at': 'previous'}}
            mod.save_json(data / 'tables.json', existing)
            meta = {'team_name': self.league['home'], 'expected_league_games': 30,
                    'source_url': 'https://www.fussball.de/mannschaft/example'}
            with patch.object(mod, 'DATA', data), patch.object(mod, 'fetch', return_value=table_html()), \
                 self.assertWarns(UserWarning):
                mod.refresh_official_tables([('u23', meta, [self.league])])
            self.assertEqual(mod.load_json(data / 'tables.json'), existing)


if __name__ == '__main__':
    unittest.main()
