/*
 * Refresh relay for the Design Studies Elective Finder (Cloudflare Worker).
 *
 * The finder page cannot start a GitHub workflow by itself, because that needs a secret token.
 * This small service holds the token. When a visitor presses "Refresh data", the page asks this
 * service to start the same workflow that runs every morning. A cooldown keeps many visitors
 * from sending repeated requests to NC State.
 *
 * Settings: the three lines below, plus one secret named GITHUB_TOKEN (set in Cloudflare, never in this file).
 */
const REPO = 'atb1982/design-studies-electives';          // GitHub account/repository
const ALLOWED_ORIGIN = 'https://atb1982.github.io';        // the site allowed to call this service
const COOLDOWN_MINUTES = 15;                               // no new collection if one finished this recently
const WORKFLOW_FILE = 'refresh.yml';

const json = (body, status, origin) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Cache-Control': 'no-store',
      Vary: 'Origin',
    },
  });

function gh(env, path, init = {}) {
  return fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'design-studies-elective-finder-relay',
      ...(init.headers || {}),
    },
  });
}

export default {
  async fetch(request, env, ctx, now = Date.now()) {
    const origin = request.headers.get('Origin') || '';
    if (request.method === 'OPTIONS') return json({}, 204, ALLOWED_ORIGIN);
    if (request.method !== 'POST') return json({ status: 'error', message: 'Use POST.' }, 405, ALLOWED_ORIGIN);
    if (origin !== ALLOWED_ORIGIN) return json({ status: 'error', message: 'Origin not allowed.' }, 403, ALLOWED_ORIGIN);
    if (!env.GITHUB_TOKEN) return json({ status: 'error', message: 'The relay has no GitHub token yet.' }, 500, ALLOWED_ORIGIN);

    // Look at recent runs of the collection workflow. Runs started by an upload (push) do not collect data, so skip them.
    const runsResp = await gh(env, `/actions/workflows/${WORKFLOW_FILE}/runs?per_page=10`);
    if (!runsResp.ok) return json({ status: 'error', message: `GitHub answered ${runsResp.status} when listing runs.` }, 502, ALLOWED_ORIGIN);
    const runs = (await runsResp.json()).workflow_runs || [];
    const last = runs.find((r) => r.event !== 'push');

    if (last && (last.status === 'queued' || last.status === 'in_progress')) {
      return json({ status: 'running', since: last.created_at }, 200, ALLOWED_ORIGIN);
    }
    if (last && last.conclusion === 'success') {
      const ageMinutes = (now - Date.parse(last.updated_at)) / 60000;
      if (ageMinutes < COOLDOWN_MINUTES) {
        return json({ status: 'cooldown', since: last.updated_at, minutesLeft: Math.ceil(COOLDOWN_MINUTES - ageMinutes) }, 200, ALLOWED_ORIGIN);
      }
    }

    const start = await gh(env, `/actions/workflows/${WORKFLOW_FILE}/dispatches`, {
      method: 'POST',
      body: JSON.stringify({ ref: 'main' }),
    });
    if (start.status !== 204) return json({ status: 'error', message: `GitHub answered ${start.status} when starting the run.` }, 502, ALLOWED_ORIGIN);
    return json({ status: 'started', at: new Date(now).toISOString() }, 200, ALLOWED_ORIGIN);
  },
};
