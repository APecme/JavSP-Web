// Manual real-browser check for the comments client credential policy.
// Runs the shipped community.js in Chromium against local origins:
//   site     = the app origin; the same-origin proxy answers 401 without the session cookie
//   omission = same host, another port (different origin); proves the client really omits
//              credentials instead of relying on the cookie being host-scoped
//   legacy   = an absolute comments host with CORS, the pre-proxy deployment shape
//
// Not part of the automated suite (it needs a Chromium build, so it stays out of
// `node --test tests/*.cjs`). Run manually:
//   npm i --no-save playwright-core      # anywhere on NODE_PATH, or in this directory
//   PW_CHROME=/path/to/chrome TMPDIR=/writable/short/path \
//     node tests/manual/browser-comments-credentials.cjs
// A short writable TMPDIR matters: Chromium builds a Unix socket path under it.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright-core');

const asset = path.join(__dirname, '../../javsp_web/web/assets/community.js');
const profile = { username: 'tester', display_name: 'tester#AB12', avatar_id: '', identity_ready: true, comment_token: 'T'.repeat(43) };
const seen = { site: [], legacy: [] };

const page = `<!doctype html><meta charset="utf-8"><title>comments check</title>
<span id="current-user"></span><span id="current-avatar"></span>
<script>
  window.escapeHtml = value => String(value ?? '');
  window.api = async () => (${JSON.stringify(profile)});
</script>
<script src="/community.js"></script>`;

const verifyPage = `<!doctype html><meta charset="utf-8"><title>verify</title><script>
  const params = new URLSearchParams(location.hash.slice(1));
  parent.postMessage({ type: 'javsp-verification', nonce: params.get('nonce'), action: params.get('action'), token: 'browser-proof' }, '*');
</script>`;

function start(handler) {
  return new Promise(resolve => {
    const server = http.createServer(handler);
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

(async () => {
  const site = await start((req, res) => {
    const cookie = req.headers.cookie || '';
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname === '/') {
      res.writeHead(200, { 'Set-Cookie': 'javsp_session=s3cret; Path=/; HttpOnly', 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(page);
    }
    if (url.pathname === '/community.js') {
      res.writeHead(200, { 'Content-Type': 'application/javascript; charset=utf-8' });
      return res.end(fs.readFileSync(asset));
    }
    if (url.pathname === '/verify') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(verifyPage);
    }
    if (url.pathname.startsWith('/api/proxy/')) {
      seen.site.push({ path: url.pathname, cookie });
      // This mirrors the proxy router: authenticated only by the site session cookie.
      if (!cookie.split(/;\s*/).some(part => part.startsWith('javsp_session='))) {
        res.writeHead(401, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify({ detail: '未登录或会话已过期。' }));
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify(profile));
    }
    res.writeHead(404).end();
  });
  const omissionCheck = await start((req, res) => {
    seen.omissionCheck = seen.omissionCheck || [];
    seen.omissionCheck.push({ path: req.url, method: req.method, cookie: req.headers.cookie || '' });
    if (req.method === 'OPTIONS') {
      res.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'x-user-token, accept', 'Access-Control-Allow-Methods': 'GET, POST, DELETE' });
      return res.end();
    }
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify(profile));
  });
  const legacy = await start((req, res) => {
    seen.legacy.push({ path: req.url, method: req.method, cookie: req.headers.cookie || '' });
    if (req.method === 'OPTIONS') {
      res.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'x-user-token, accept', 'Access-Control-Allow-Methods': 'GET, POST, DELETE' });
      return res.end();
    }
    if (req.url === '/verify') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(verifyPage);
    }
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify(profile));
  });
  const siteOrigin = `http://127.0.0.1:${site.port}`;
  const legacyOrigin = `http://127.0.0.1:${legacy.port}`;
  const omissionOrigin = `http://127.0.0.1:${omissionCheck.port}`;

  const browser = await chromium.launch({
    executablePath: process.env.PW_CHROME || path.join(os.homedir(), '.cache/ms-playwright/chromium-1248/chrome-linux64/chrome'),
    args: ['--no-sandbox'],
  });
  const result = {};
  try {
    const context = await browser.newContext();
    const tab = await context.newPage();
    const errors = [];
    tab.on('pageerror', error => errors.push(String(error)));
    await tab.goto(siteOrigin + '/');
    result.cookieInBrowser = (await context.cookies(siteOrigin)).map(item => item.name);

    // 1. The old hard-coded policy: credentials 'omit' means the proxy answers 401.
    result.legacyBehavior = await tab.evaluate(async () => {
      const response = await fetch('/api/proxy/api/me/profile', { credentials: 'omit', referrerPolicy: 'no-referrer' });
      return { status: response.status, cookieSent: null };
    });

    // 2. The shipped client against the same-origin proxy.
    result.sameOrigin = await tab.evaluate(async () => {
      await window.JavspCommunity.init();
      window.JavspCommunity.configure('/api/proxy', location.origin);
      await window.JavspCommunity.requireIdentity();
      return { base: '/api/proxy' };
    });

    // 3. Real browser verification round trip (relative data base, separate verify origin).
    result.verification = await tab.evaluate(async () => {
      const token = await window.JavspCommunity.verify('comment');
      return { token };
    });

    // 3b. The production shape: data through the site proxy, Turnstile on the upstream origin.
    result.crossOriginVerification = await tab.evaluate(async origin => {
      window.JavspCommunity.configure('/api/proxy', origin);
      const token = await window.JavspCommunity.verify('comment');
      return { token };
    }, legacyOrigin);

    // 3c. A base switch without a verification argument drops the old origin.
    result.verificationAfterBaseSwitch = await tab.evaluate(async () => {
      window.JavspCommunity.configure('/api/other-proxy');
      try { await window.JavspCommunity.verify('comment'); return 'resolved'; }
      catch (error) { return String(error.message); }
    });
    result.verificationAfterSameBaseReconfigure = await tab.evaluate(async origin => {
      window.JavspCommunity.configure('/api/proxy', origin);
      window.JavspCommunity.configure('/api/proxy');
      return await window.JavspCommunity.verify('comment');
    }, legacyOrigin);

    // 4. A legacy absolute comments host keeps the cookie away.
    result.legacy = await tab.evaluate(async origin => {
      window.JavspCommunity.configure(origin, origin);
      await window.JavspCommunity.requireIdentity();
      return { base: origin };
    }, legacyOrigin);

    // 5. The same host on another port would receive the cookie unless the client omits it.
    result.omission = await tab.evaluate(async origin => {
      window.JavspCommunity.configure(origin, origin);
      await window.JavspCommunity.requireIdentity();
      return { base: origin };
    }, omissionOrigin);

    result.pageErrors = errors;
    result.seenOmission = seen.omissionCheck || [];
    result.seenSite = seen.site.map(item => ({ path: item.path, cookie: item.cookie }));
    result.seenLegacy = seen.legacy.map(item => ({ path: item.path, cookie: item.cookie }));
  } finally {
    await browser.close();
    site.server.close();
    legacy.server.close();
    omissionCheck.server.close();
  }
  console.log(JSON.stringify(result, null, 2));
})().catch(error => {
  console.error('browser check failed:', error);
  process.exit(1);
});
