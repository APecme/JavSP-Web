const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(root, 'javsp_web/web/assets/app.js'), 'utf8');

function slice(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

function harness() {
  const context = vm.createContext({
    $: () => null,
    escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'),
    state: { crawlerSources: [], disabledBuiltInCrawlers: [] },
  });
  vm.runInContext(slice(appSource, 'let crawlerStatsCache', 'function crawlerSkeletonMarkup'), context);
  return context;
}

test('formatStatTime renders YYYY-MM-DD HH:MM without T and without truncation', () => {
  const context = harness();
  assert.equal(context.formatStatTime('2026-10-24T12:34:56'), '2026-10-24 12:34');
  assert.equal(context.formatStatTime('2026-10-24 09:07:11'), '2026-10-24 09:07');
  assert.equal(context.formatStatTime('2026-10-24T12:34'), '2026-10-24 12:34');
  assert.equal(context.formatStatTime('2026-10-24'), '2026-10-24');
});

test('usage line shows 成功 X · 失败 Y plus 最近失败, no scrape/task counts', () => {
  const context = harness();
  const text = context.crawlerUsageText({ success_count: 120, failure_count: 8, scrape_count: 300, task_count: 5, last_failure_at: '2026-10-24T12:34:56' });
  assert.match(text, /^成功 120 · 失败 8 · 最近失败 2026-10-24 12:34$/);
  assert.doesNotMatch(text, /刮削/);
  assert.doesNotMatch(text, /任务/);
  assert.doesNotMatch(text, /T\d{2}/, 'no ISO T separator');
  // alternate field names from the stats endpoint
  const alt = context.crawlerUsageText({ success: 12, failure: 1, scrapes: 20, tasks: 3 });
  assert.equal(alt, '成功 12 · 失败 1');
  assert.equal(context.crawlerUsageText(null), '');
});

test('health dot colors: degraded yellow outranks rate tiers, then 0.9/0.7 thresholds, gray for no data', () => {
  const context = harness();
  // degraded: success>0 and last_failure_at newer than last_success_at, even at 0.95 rate
  assert.match(context.crawlerHealthDot({ success_rate: 0.95, success_count: 20, failure_count: 1, last_failure_at: '2026-10-24T10:00', last_success_at: '2026-10-20T10:00' }), /crawler-health-degraded/);
  // failure older than last success: not degraded, falls back to rate tier
  assert.match(context.crawlerHealthDot({ success_rate: 0.95, success_count: 20, failure_count: 1, last_failure_at: '2026-10-01T10:00', last_success_at: '2026-10-24T10:00' }), /crawler-health-ok/);
  // degraded requires success > 0
  assert.match(context.crawlerHealthDot({ success_rate: 0, success_count: 0, failure_count: 5, last_failure_at: '2026-10-24T10:00' }), /crawler-health-danger/);
  assert.match(context.crawlerHealthDot({ success_rate: 0.92 }), /crawler-health-ok/);
  assert.match(context.crawlerHealthDot({ success_rate: 0.75 }), /crawler-health-warn/);
  assert.match(context.crawlerHealthDot({ success_rate: 0.5 }), /crawler-health-danger/);
  assert.match(context.crawlerHealthDot(null), /crawler-health-unknown/);
  assert.match(context.crawlerHealthDot({}), /crawler-health-unknown/);
  // label carries counts
  assert.match(context.crawlerHealthDot({ success_rate: 0.93, success_count: 120, failure_count: 8 }), /成功率 93%，成功 120 \/ 失败 8/);
});
