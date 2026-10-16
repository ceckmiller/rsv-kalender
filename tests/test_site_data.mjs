import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../docs/index.html', import.meta.url), 'utf8');
const source = html.slice(html.indexOf('function prepareSiteData('), html.indexOf('const fd=d=>'));
const context = vm.createContext({ Intl, Date });
vm.runInContext(source, context);

test('future results disappear from last game, fixtures and round pairings', () => {
  const played = { date: '2026-09-27', time: '14:00', result: '3:3' };
  const future = { date: '2026-11-15', time: '14:00', result: '3:3', halftime_result: '2:1', scorers: ['Wrong'] };
  const data = { teams: { u23: { matches: [played, future], fixtures: [played, future], round_groups: [{ matches: [future] }] } } };
  context.prepareSiteData(data, new Date('2026-10-16T13:00:00Z'));
  assert.equal(data.teams.u23.matches.length, 1);
  assert.equal(data.teams.u23.matches[0].date, '2026-09-27');
  assert.equal(data.teams.u23.fixtures[1].result, undefined);
  assert.equal(data.teams.u23.round_groups[0].matches[0].scorers, undefined);
});

test('same-day results use Berlin time regardless of browser timezone', () => {
  const match = { date: '2026-10-16', time: '14:00', result: '1:0' };
  const makeData = () => ({ teams: { u23: { matches: [match], fixtures: [match] } } });
  assert.equal(context.prepareSiteData(makeData(), new Date('2026-10-16T11:59:00Z')).teams.u23.matches.length, 0);
  assert.equal(context.prepareSiteData(makeData(), new Date('2026-10-16T12:01:00Z')).teams.u23.matches.length, 1);
});

test('invalid results are removed from additional calendar teams', () => {
  const data = { calendar_teams: { extra: { fixtures: [{ date: '2026-09-27', result: 'scheduled' }] } } };
  context.prepareSiteData(data, new Date('2026-10-16T13:00:00Z'));
  assert.equal(data.calendar_teams.extra.fixtures[0].result, undefined);
});
