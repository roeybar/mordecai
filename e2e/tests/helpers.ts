import { expect, Locator, Page } from '@playwright/test';

// Shared helpers for the e2e specs. This file is not a spec: it holds no test().

export const TAGLINE = 'A research toolkit for resolving homographs with typed frames.';
export const GOOGLE = "From Google's Gemini API Additional Terms of Service (Unpaid Services, effective March 23, 2026): \"When you use Unpaid Services, including, for example, Google AI Studio and the unpaid quota on Gemini API, Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services and machine learning technologies, including Google's enterprise features, products, and services, consistent with our Privacy Policy.\" \"To help with quality and improve our products, human reviewers may read, annotate, and process your API input and output.\" \"Do not submit sensitive, confidential, or personal information to the Unpaid Services.\"";
export const ATTEMPTS = "Each visitor gets 3 attempts in 24 hours on this server, whichever provider; a request the content gate or the provider refuses counts too. 18+ only.";
export const REGION = "This demo is invite-only and is not available to residents of the European Economic Area, the United Kingdom or Switzerland.";

export const BANNER_HOSTED = "Hosted demo. Your text and its translation are sent to Google's Gemini API.";
export const BANNER_DEMO =
  'Hosted demo. With the demo provider your text does not leave this server: the translation is a word-by-word gloss built from the demo frames.';
export const bannerKeyed = (v: string) =>
  `Hosted demo. Your text and its translation are sent to ${v}'s API with your key, used for this request only, never stored or logged.`;

export const LIMIT = 'This demo allows 3 attempts per visitor in 24 hours. Run it on your own machine from the repository to continue.';
export const QUOTA = "The demo's quota is used up for now; try again later or run it on your own machine.";

// The text of a line split at its SVG separator dots, each part trimmed; the dots are not text.
export const dotParts = (loc: Locator) =>
  loc.evaluate((node) => {
    const out: string[] = [];
    let cur = '';
    node.childNodes.forEach((c) => {
      if (c instanceof SVGElement && c.classList.contains('ico-dot')) { out.push(cur.trim()); cur = ''; }
      else cur += c.textContent || '';
    });
    out.push(cur.trim());
    return out;
  });
export const SCORE_NOTE = '(slot matches minus unmet required slots, between neighbouring words that both have readings; not an accuracy measure)';

export const EXPECTED = 'was to me hair in-eyebrow while that-was storm that-rocked in-boat';
export const MW_TEXT = '\u05d4\u05d5\u05d0 \u05e9\u05dd \u05dc\u05d1 \u05e9\u05d4\u05d3\u05dc\u05ea \u05e4\u05ea\u05d5\u05d7\u05d4';
export const MW_EXPECTED = 'he took notice that-the-door open';
export const BARK_EXPECTED =
  '\u05d4\u05b7 \u05e7\u05b0\u05dc\u05b4\u05d9\u05e4\u05b8\u05bc\u05d4 \u05e9\u05b6\u05c1\u05dc ' +
  '\u05d4\u05b7 \u05d0\u05b7\u05dc\u05bc\u05d5\u05b9\u05df \u05d4\u05b8\u05d9\u05b0\u05ea\u05b8\u05d4 ' +
  '\u05de\u05b0\u05d7\u05bb\u05e1\u05b0\u05e4\u05b6\u05bc\u05e1\u05b6\u05ea';
export const NIQ = /[\u0591-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]/g;

export const HOSTED = {
  name: 'hosted',
  label: 'gemini (hosted)',
  needs_key: false,
  hosted: true,
  notice: "Rendered by the Gemini API on this demo's own key (hosted demo, free tier).",
  models: [{ id: 'gemini-3.5-flash', efforts: ['minimal'], default: true }],
};

// The page translates through the streaming route.
export const STREAM = '**/api/translate/stream';

export async function ready(page: Page) {
  await page.goto('/');
  await expect(page.locator('#app')).toBeVisible();
  await expect(page.locator('#load-state')).toBeHidden();
}

export const ddButton = (page: Page, id: string) => page.locator(`button[aria-controls="${id}-list"]`);

// An option's name matches exactly; regex metacharacters in the name become wildcards.
export async function choose(page: Page, id: string, name: string) {
  await ddButton(page, id).click();
  const list = page.locator(`#${id}-list`);
  await expect(list).toBeVisible();
  const exact = new RegExp('^' + name.replace(/[^A-Za-z0-9 ]/g, '.') + '$');
  await list.locator('[role=option]').filter({ has: page.locator('.dd-name', { hasText: exact }) }).first().click();
  await expect(list).toBeHidden();
}

export const chip = (page: Page, id: string) => page.locator(`#examples .chip[data-id="${id}"]`);

// The key field shows the first four characters of the key, then one ASCII asterisk per further character.
export const maskedKey = (key: string) => key.slice(0, 4) + '*'.repeat(Math.max(0, key.length - 4));

// Fills the key field (one input event carrying the whole key, as a paste does) and checks it shows only the mask.
export async function typeKey(page: Page, key: string) {
  await page.fill('#key', key);
  await expect(page.locator('#key')).toHaveValue(maskedKey(key));
}

export async function go(page: Page) {
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/translate')),
    page.click('#go'),
  ]);
  return resp;
}

// A request that never gets a response: the page sees a network failure.
export async function goFails(page: Page) {
  await Promise.all([
    page.waitForEvent('requestfailed', (r) => r.url().includes('/api/translate')),
    page.click('#go'),
  ]);
}

export async function stubHosted(page: Page) {
  await page.route('**/api/providers', async (route) => {
    const resp = await route.fetch();
    const list = await resp.json();
    await route.fulfill({ response: resp, json: [...list, HOSTED] });
  });
}

export type Answer = { status: number; json?: unknown; body?: string; frames?: number };

const STAGE_NAMES = ['input', 'translate', 'output'];
const lines = (objs: unknown[]) => objs.map((o) => JSON.stringify(o) + '\n').join('');

// Answers each POST with answers[i] (the last one repeats) and records provider and key per POST; the parsed
// request bodies go to `bodies` when given. A 200 is the three stage lines, then the body. A refusal is a
// plain status, unless `frames` is set: then it is that many stage lines and a line carrying its status.
export async function stubTranslate(page: Page, answers: Answer[], bodies?: any[]) {
  const rec: Array<{ provider: string; key: string | null }> = [];
  await page.route(STREAM, async (route) => {
    const req = route.request();
    const sent = req.postDataJSON();
    rec.push({ provider: sent.provider, key: req.headers()['x-provider-key'] ?? null });
    if (bodies) bodies.push(sent);
    const a = answers[Math.min(rec.length - 1, answers.length - 1)];
    const ndjson = (objs: unknown[]) =>
      route.fulfill({ status: 200, contentType: 'application/x-ndjson', body: lines(objs) });
    if (a.body !== undefined) await route.fulfill({ status: a.status, contentType: 'text/plain', body: a.body });
    else if (a.status === 200) await ndjson([...STAGE_NAMES.map((stage) => ({ stage })), a.json]);
    else if (a.frames !== undefined) {
      const { error, ...rest } = a.json as any;
      await ndjson([...STAGE_NAMES.slice(0, a.frames).map((stage) => ({ stage })), { error, status: a.status, ...rest }]);
    } else await route.fulfill({ status: a.status, json: a.json });
  });
  return rec;
}

// Replaces fetch for the stream route with a response the test feeds line by line; other URLs go through.
// The parsed request bodies are kept in the page.
export async function holdStream(page: Page) {
  await page.addInitScript(() => {
    const w = window as any;
    w.__streamBodies = [];
    const real = window.fetch.bind(window);
    window.fetch = (input: any, init?: any) => {
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : String(input);
      if (!url.endsWith('/api/translate/stream')) return real(input, init);
      w.__streamBodies.push(JSON.parse(init.body));
      const enc = new TextEncoder();
      const stream = new ReadableStream({
        start(c) { w.__push = (line: string | null) => { if (line === null) c.close(); else c.enqueue(enc.encode(line)); }; },
      });
      return Promise.resolve(new Response(stream, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } }));
    };
  });
  return {
    push: (obj: unknown) => page.evaluate((line) => (window as any).__push(line), JSON.stringify(obj) + '\n'),
    end: () => page.evaluate(() => (window as any).__push(null)),
    bodies: () => page.evaluate(() => (window as any).__streamBodies),
  };
}

export const OK = (provider: string) => ({
  text: 'stub render',
  provider,
  notice: 'stub notice',
  source: 'he',
  target: 'en',
  source_status: 'VERIFIED',
  target_status: 'VERIFIED',
  readings: [],
  greedy: [],
  solver: { score: 0, evaluated: 0 },
  verify: { ok: true, notes: [] },
  notes: [],
});

// Collects CSP violations (events and console messages); call the returned function to assert none.
export async function cspWatch(page: Page) {
  const logs: string[] = [];
  page.on('console', (m) => {
    if (/Content Security Policy/.test(m.text())) logs.push(m.text());
  });
  await page.addInitScript(() => {
    (window as any).__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => (window as any).__csp.push(e.violatedDirective));
  });
  return async () => {
    expect(await page.evaluate(() => (window as any).__csp)).toEqual([]);
    expect(logs).toEqual([]);
  };
}
