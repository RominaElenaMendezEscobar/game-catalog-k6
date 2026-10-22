// k6 load test for the game-catalog search API.
// The test is configured in scenarios/<SCENARIO>.json: no code changes needed.
//
// Usage:
//   k6 run -e API_URL=<api-url> -e SCENARIO=smoke search.js
//
// Authentication (AUTH_MODE):
//   iam  (default) signs every request with AWS Signature V4, using the credentials in
//        AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and AWS_SESSION_TOKEN.
//   none sends unsigned requests (only for APIs without authorization).
//
// To create a new scenario, copy any file in scenarios/, change it and run it with -e SCENARIO=<file name>.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter } from 'k6/metrics';
import { signRequest } from './sigv4.js';

const API_URL = (__ENV.API_URL || '').replace(/\/$/, '');
const SCENARIO = __ENV.SCENARIO || 'smoke';
const AUTH_MODE = (__ENV.AUTH_MODE || 'iam').toLowerCase();
const AWS_REGION = __ENV.AWS_REGION || 'us-east-1';

if (!API_URL) {
  throw new Error('API_URL is required: k6 run -e API_URL=<api-url> -e SCENARIO=smoke search.js');
}

if (AUTH_MODE === 'iam' && (!__ENV.AWS_ACCESS_KEY_ID || !__ENV.AWS_SECRET_ACCESS_KEY)) {
  throw new Error('AUTH_MODE=iam requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (and AWS_SESSION_TOKEN for temporary credentials)');
}

// ---------- configuration (read once, in the init context) ----------

const config = JSON.parse(open(`./scenarios/${SCENARIO}.json`));
const queries = new SharedArray('queries', () => JSON.parse(open(`./${config.queries_file || 'queries.json'}`)));

const ENDPOINT = config.endpoint || '/search';
const THINK_TIME = config.think_time_seconds ?? 1;
const TIMEOUT = config.request_timeout || '30s';

const decisions = new Counter('decisions');

// k6 only includes tagged sub-metrics in the summary when they have a threshold.
// These always-true thresholds add the breakdown by language and by decision.
const LANGS = ['en', 'es'];
const DECISIONS = ['duplicate', 'variant', 'new', 'out_of_scope'];
const breakdown = {};
LANGS.forEach((l) => {
  breakdown[`http_req_duration{lang:${l}}`] = ['max>=0'];
  breakdown[`http_req_failed{lang:${l}}`] = ['rate>=0'];
});
DECISIONS.forEach((d) => {
  breakdown[`decisions{decision:${d}}`] = ['count>=0'];
});

export const options = {
  scenarios: { [config.name || SCENARIO]: config.executor },
  thresholds: { ...breakdown, ...(config.thresholds || {}) },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// ---------- test ----------

export function setup() {
  return { startedAt: new Date().toISOString() };
}

export default function () {
  const q = queries[Math.floor(Math.random() * queries.length)];

  const url = `${API_URL}${ENDPOINT}`;
  const payload = JSON.stringify({ query: q.query });
  let headers = { 'Content-Type': 'application/json' };

  if (AUTH_MODE === 'iam') {
    headers = signRequest({
      method: 'POST',
      url: url,
      body: payload,
      headers: headers,
      region: AWS_REGION,
      service: 'execute-api',
      accessKeyId: __ENV.AWS_ACCESS_KEY_ID,
      secretAccessKey: __ENV.AWS_SECRET_ACCESS_KEY,
      sessionToken: __ENV.AWS_SESSION_TOKEN,
    });
  }

  const res = http.post(url, payload, {
    headers: headers,
    tags: { lang: q.lang || 'unknown' },
    timeout: TIMEOUT,
  });

  let body = null;
  try {
    body = res.json();
  } catch (e) {
    body = null;
  }

  check(res, {
    'status is 200': (r) => r.status === 200,
    'not forbidden (auth ok)': (r) => r.status !== 403,
    'has decision': () => body !== null && typeof body.decision === 'string',
  });

  if (body && body.decision) {
    decisions.add(1, { decision: body.decision });
  }

  sleep(THINK_TIME);
}

// ---------- summary ----------

export function handleSummary(data) {
  const m = data.metrics;
  const summary = {
    scenario: config.name || SCENARIO,
    description: config.description || '',
    auth_mode: AUTH_MODE,
    config: config,
    started_at: data.setup_data ? data.setup_data.startedAt : null,
    finished_at: new Date().toISOString(),
    metrics: m,
  };

  const p95 = m.http_req_duration ? m.http_req_duration.values['p(95)'] : 0;
  const failed = m.http_req_failed ? m.http_req_failed.values.rate * 100 : 0;
  const requests = m.http_reqs ? m.http_reqs.values.count : 0;

  return {
    'k6-summary.json': JSON.stringify(summary, null, 2),
    stdout:
      `\nScenario: ${summary.scenario}\n` +
      `Requests: ${requests}\n` +
      `Failed:   ${failed.toFixed(2)}%\n` +
      `p95:      ${p95.toFixed(0)} ms\n` +
      `Summary written to k6-summary.json\n`,
  };
}