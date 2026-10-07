import { test, expect, Locator, Page } from '@playwright/test';
import {
  BARK_EXPECTED, EXPECTED, LIMIT, MW_EXPECTED, MW_TEXT, NIQ, OK, SCORE_NOTE, TAGLINE,
  STREAM, choose, chip, cspWatch, dotParts, ddButton, go, goFails, holdStream, maskedKey, ready, stubTranslate, typeKey,
} from './helpers';

// The clipboard needs a secure context, and http://localhost is one. The browser maps localhost to
// the web container, and the copy test (below) loads the page by that name.
const BASE = new URL(process.env.BASE_URL || 'http://web:8080');
const LOCALHOST = 'http://localhost' + (BASE.port ? ':' + BASE.port : '');
test.use({
  colorScheme: 'light',
  launchOptions: { args: ['--host-resolver-rules=MAP localhost ' + BASE.hostname] },
});

const STORM = '\u05e1\u05b0\u05e2\u05b8\u05e8\u05b8\u05d4';
const EYEBROW = '\u05d2\u05b7\u05bc\u05d1\u05b8\u05bc\u05d4';
const HAIR = '\u05e9\u05b7\u05c2\u05e2\u05b2\u05e8\u05b8\u05d4';
const SHAARA = '\u05e9\u05e2\u05e8\u05d4';
const KEY_A = 'placeholder-key-A-000000';
const KEY_B = 'placeholder-key-B-000000';
const SEED = 'hair-eyebrow-storm-boat';
const TIP = 'mordecai is designed to help small, fast models translate words with several meanings correctly.';
const INFO_NAME = 'What mordecai is designed for';
const DISCLAIMER = 'This is a demo of mordecai, an unfinished research prototype, running on an example frame set. It is not the full mordecai.';
const CONTACT_LEAD = ' For the full project, contact the author at ';
const LOW5 = ['low', 'medium', 'high', 'xhigh', 'max'];
const GEMINI4 = ['minimal', 'low', 'medium', 'high'];
// The curated lists of docker-compose.yml: model id, its effort levels (lowest first), default first.
const MODELS: Record<string, Array<[string, string[]]>> = {
  anthropic: [['claude-haiku-5-5', LOW5], ['claude-sonnet-5-5', LOW5], ['claude-opus-5-5', LOW5]],
  xai: [['grok-4.20-0309-non-reasoning', []], ['grok-4.20-0309-reasoning', []], ['grok-4.3', []], ['grok-4.7', []]],
  gemini: [['gemini-3.5-flash', GEMINI4], ['gemini-3.1-flash-lite', GEMINI4], ['gemini-3-flash-preview', GEMINI4],
    ['gemini-3.6-flash', GEMINI4], ['gemini-3.5-flash-lite', GEMINI4]],
  openai: [['gpt-6-luna', ['none', ...LOW5]], ['gpt-6.1-sol', LOW5]],
};
// The registry's vowel-mark labels and ranges (api/mordecai/langs.py), each label a word in its own script.
const HE_MARKS = '\u05e0\u05d9\u05e7\u05d5\u05d3';
const AR_MARKS = '\u062a\u0634\u0643\u064a\u0644';
const UR_MARKS = '\u0627\u0639\u0631\u0627\u0628';
const HE_RANGES = [[0x0591, 0x05BD], [0x05BF, 0x05BF], [0x05C1, 0x05C2], [0x05C4, 0x05C5], [0x05C7, 0x05C7]];
const ARAB_RANGES = [[0x064B, 0x0652], [0x0656, 0x0658], [0x0670, 0x0670]];
// A stub Arabic render: tanween, fatha, damma, kasra, shadda, sukun and superscript alef go with the toggle;
// the hamza above written as its own mark (U+0654) belongs to the letter and stays.
const AR_MARKED = '\u0623\u064e\u0646\u064e\u0627 \u0645\u064f\u062f\u064e\u0631\u0650\u0651\u0633\u064c \u0645\u0650\u0646\u0652 \u0647\u0670\u0630\u064e\u0627 \u0633\u064f\u0648\u0654\u064e\u0627\u0644\u064b\u0627';
const AR_BARE = '\u0623\u0646\u0627 \u0645\u062f\u0631\u0633 \u0645\u0646 \u0647\u0630\u0627 \u0633\u0648\u0654\u0627\u0644\u0627';
const AR_GLOSS = '\u0645\u064f\u062f\u064e\u0631\u0650\u0651\u0633\u064c';
const AR_GLOSS_BARE = '\u0645\u062f\u0631\u0633';
// Every code point U+0590-U+06FF, and the sweep without a language's ranges.
const SWEEP = Array.from({ length: 0x0170 }, (_, i) => String.fromCharCode(0x0590 + i)).join('');
const keep = (ranges: number[][]) => Array.from(SWEEP).filter((c) => !ranges.some(([a, b]) => c.charCodeAt(0) >= a && c.charCodeAt(0) <= b)).join('');

test('the page loads the page shell with an h1 brand and the tagline', async ({ page }) => {
  const csp = await cspWatch(page);
  await ready(page);
  await expect(page.locator('h1 #home')).toBeVisible();
  await expect(page.locator('h1 #home')).toContainText('mordecai');
  await expect(page.locator('.tagline')).toBeVisible();
  await expect(page.locator('.tagline')).toHaveText(TAGLINE);
  await expect(page.locator('footer')).toContainText(
    'whose readings the golden itself attributes to a native-speaker reviewer');
  await page.click('#about-open');
  await expect(page.locator('#about')).toBeVisible();
  await page.click('#about [data-close]');
  await expect(page.locator('#about')).toBeHidden();
  for (const id of ['source', 'target', 'provider']) {
    await ddButton(page, id).click();
    await expect(page.locator(`#${id}-list`)).toBeVisible();
    await ddButton(page, id).click();
    await expect(page.locator(`#${id}-list`)).toBeHidden();
  }
  await csp();
});

test('demo example resolves with the toy solver in the merged readings list', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await ready(page);
  await expect(page.locator('#provider-cur')).toHaveText('demo');
  await chip(page, SEED).click();
  await expect(page.locator('#text')).not.toHaveValue('');
  await expect(chip(page, SEED)).toHaveClass(/active/);
  const resp = await go(page);
  expect(resp.status()).toBe(200);
  await expect(page.locator('#output')).toHaveText(EXPECTED);
  await expect(page.locator('#notice')).toContainText('Demo provider');
  await expect(page.locator('#notice')).toContainText('(source: VERIFIED, target: VERIFIED)');
  await expect(page.locator('#readings')).toContainText(STORM);
  await expect(page.locator('#readings')).toContainText(EYEBROW);
  const differing = page.locator('li.reading.differs [data-row="baseline"]', { hasText: HAIR }).first();
  await expect(differing).toContainText(HAIR);
  await expect(differing).toContainText('differs');
  const withOptions = page.locator('li.reading').filter({ has: page.locator('[data-row="options"]') });
  expect(await withOptions.count()).toBeGreaterThan(0);
  const picked = await withOptions.evaluateAll((lis) => lis.map((li) => li.querySelectorAll('.cand.picked').length));
  expect(picked.every((n) => n === 1)).toBe(true);
  const sl = await dotParts(page.locator('#solver-line'));
  expect(sl).toHaveLength(4);
  expect(sl[0]).toMatch(/^\d+ words with candidates$/);
  expect(sl[1]).toMatch(/^baseline differs on [1-9]\d*$/);
  expect(sl[2]).toBe('toy solver score 3 ' + SCORE_NOTE);
  expect(sl[3]).toMatch(/^\d+ option pairs scored between neighbouring words \(a word without candidates counts as one option\)$/);
  expect(await page.locator('#solver-line').textContent()).toMatch(
    /^\d+ words with candidates {2}baseline differs on [1-9]\d* {2}toy solver score 3 \(slot matches minus unmet required slots, between neighbouring words that both have readings; not an accuracy measure\) {2}\d+ option pairs scored between neighbouring words \(a word without candidates counts as one option\)$/);
  await expect(page.locator('#solver-line svg.ico-dot')).toHaveCount(3);
  await expect(page.locator('#history-count')).toHaveText('1');
  expect(errors).toEqual([]);
});

test('status strings are the registry strings on chips and on every language in the lists', async ({ page }) => {
  await ready(page);
  await expect(page.locator('#source-status')).toHaveText('VERIFIED');
  await expect(page.locator('#target-status')).toHaveText('VERIFIED');
  await choose(page, 'target', 'Hindi');
  await expect(page.locator('#target-status')).toHaveText('MACHINE-MADE, UNVERIFIED');
  await expect(page.locator('#target-status')).toHaveClass(/unverified/);
  await ddButton(page, 'target').click();
  const options = page.locator('#target-list [role=option]');
  await expect(options).toHaveCount(16);
  const statuses = ['VERIFIED', 'MACHINE-MADE, UNVERIFIED'];
  const tagsPerOption = await options.evaluateAll((lis) =>
    lis.map((li) => Array.from(li.querySelectorAll('.dd-tag')).map((t) => t.textContent || '')));
  for (const tags of tagsPerOption) {
    expect(tags.filter((t) => statuses.includes(t))).toHaveLength(1);
  }
  const tagsOf = (name: string) =>
    options.filter({ has: page.locator('.dd-name', { hasText: new RegExp('^' + name + '$') }) }).locator('.dd-tag');
  await expect(tagsOf('Hebrew')).toHaveText(['RTL', 'VERIFIED']);
  await expect(tagsOf('English')).toHaveText(['VERIFIED']);
  await expect(tagsOf('Standard Arabic')).toHaveText(['RTL', 'MACHINE-MADE, UNVERIFIED']);
});

test('text direction follows the source language', async ({ page }) => {
  await ready(page);
  await expect(page.locator('#text')).toHaveAttribute('dir', 'rtl');
  await choose(page, 'source', 'English');
  await expect(page.locator('#text')).toHaveAttribute('dir', 'ltr');
  await expect(page.locator('#target')).toHaveValue('he');
});

test('Go explains why it is disabled, including at the length boundary', async ({ page }) => {
  await ready(page);
  await expect(page.locator('#key-row')).toBeHidden();
  await page.fill('#text', 'Good morning.');
  await expect(page.locator('#go-reason')).toHaveText(
    'The demo accepts only the example sentences. Pick one, or switch to a keyed provider.');
  await expect(page.locator('#go')).toBeDisabled();
  await choose(page, 'provider', 'anthropic');
  await expect(page.locator('#key-row')).toBeVisible();
  await expect(page.locator('#go-reason')).toHaveText('Enter your anthropic API key to translate.');
  await typeKey(page, '0'.repeat(24));
  await expect(page.locator('#go-reason')).toHaveText('');
  await expect(page.locator('#go')).toBeEnabled();
  await page.fill('#text', 'a'.repeat(4000));
  await expect(page.locator('#go-reason')).toHaveText('');
  await expect(page.locator('#count')).toHaveText('4,000 / 4,000');
  await expect(page.locator('#count')).not.toHaveClass(/over/);
  await page.fill('#text', 'a'.repeat(4001));
  await expect(page.locator('#go-reason')).toHaveText('The text is over the 4,000-character default limit.');
  await expect(page.locator('#count')).toHaveClass(/over/);
  await expect(page.locator('#go')).toBeDisabled();
});

test('the key is cleared on every provider change, including a history restore', async ({ page }) => {
  const rec = await stubTranslate(page, [{ status: 200, json: OK('anthropic') }]);
  await ready(page);
  await choose(page, 'provider', 'anthropic');
  await typeKey(page, KEY_A);
  await chip(page, 'mw-attention').click();
  await go(page);
  await expect(page.locator('#output')).toHaveText('stub render');
  await choose(page, 'provider', 'xai');
  await expect(page.locator('#key')).toHaveValue('');
  await typeKey(page, KEY_B);
  await page.click('#history-open');
  await page.locator('.h-item').first().click();
  await expect(page.locator('#provider')).toHaveValue('anthropic');
  await expect(page.locator('#key')).toHaveValue('');
  expect(rec).toEqual([{ provider: 'anthropic', key: KEY_A }]);
  await expect(page.locator('#readings-empty')).toBeVisible();
  await expect(page.locator('#readings-empty')).toHaveText(
    'No word in this text has candidates in the frame store. The shipped frames cover the example sentences.');
  await expect(page.locator('#solver-line')).toHaveText('');
});

test('the key field is a plain text field that masks after four characters', async ({ page }) => {
  test.setTimeout(90_000);
  const rec = await stubTranslate(page, [{ status: 200, json: OK('anthropic') }]);
  await ready(page);
  await choose(page, 'provider', 'anthropic');
  const key = page.locator('#key');
  await expect(key).toBeVisible();
  for (const [name, value] of [
    ['type', 'text'], ['autocomplete', 'off'], ['spellcheck', 'false'], ['autocapitalize', 'off'],
    ['autocorrect', 'off'], ['data-1p-ignore', ''], ['data-lpignore', 'true'], ['data-form-type', 'other'],
    ['placeholder', 'Paste your key'],
  ]) await expect(key, name).toHaveAttribute(name, value);
  expect(await key.getAttribute('name')).toBeNull();
  expect(await key.evaluate((n) => (n as HTMLInputElement).form === null && n.closest('form') === null)).toBe(true);
  await expect(page.locator('form')).toHaveCount(0);
  await expect(page.locator('input[type=password]')).toHaveCount(0);
  await expect(page.locator('input:not(#key):not(.dd-search)')).toHaveCount(0);
  await expect(key).toHaveCSS('min-height', '46px');
  await expect(key).toHaveCSS('font-family', /monospace/);

  await chip(page, 'mw-attention').click();
  await typeKey(page, KEY_A);
  expect(await key.getAttribute('value')).toBeNull();
  await go(page);
  await expect(page.locator('#output')).toHaveText('stub render');
  expect(rec).toEqual([{ provider: 'anthropic', key: KEY_A }]);

  await key.press('End');
  await page.keyboard.type('XYZ');
  await expect(key).toHaveValue('plac' + '*'.repeat(KEY_A.length - 4 + 3));
  await go(page);
  expect(rec[1]).toEqual({ provider: 'anthropic', key: KEY_A + 'XYZ' });

  await key.press('End');
  await key.press('Backspace');
  await expect(key).toHaveValue(maskedKey(KEY_A + 'XY'));
  await go(page);
  expect(rec[2]).toEqual({ provider: 'anthropic', key: KEY_A + 'XY' });

  await key.press('Home');
  for (let i = 0; i < 6; i++) await key.press('ArrowRight');
  await key.press('Backspace');
  const mid = KEY_A.slice(0, 5) + KEY_A.slice(6) + 'XY';
  await expect(key).toHaveValue(maskedKey(mid));
  expect(await key.evaluate((n) => [(n as HTMLInputElement).selectionStart, (n as HTMLInputElement).selectionEnd])).toEqual([5, 5]);
  await go(page);
  expect(rec[3]).toEqual({ provider: 'anthropic', key: mid });

  await key.press('Control+A');
  await page.keyboard.type('vwxyz');
  await expect(key).toHaveValue('vwxy*');
  await go(page);
  expect(rec[4]).toEqual({ provider: 'anthropic', key: 'vwxyz' });

  for (const k of ['abc', 'abcd', 'abcde']) await typeKey(page, k);
  await typeKey(page, '');
  await expect(page.locator('#go-reason')).toHaveText('Enter your anthropic API key to translate.');
  await expect(page.locator('#go')).toBeDisabled();
  const long = Array.from({ length: 512 }, (_, i) => String.fromCharCode(33 + (i % 94))).join('');
  await typeKey(page, long);
  await go(page);
  expect(rec[5]).toEqual({ provider: 'anthropic', key: long });

  await typeKey(page, KEY_B);
  const res = await key.evaluate((n, start) => {
    const input = n as HTMLInputElement;
    const mask = (k: string) => k.slice(0, 4) + '*'.repeat(Math.max(0, k.length - 4));
    const ABC = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_';
    let seed = 7, real = start;
    const rnd = (m: number) => { seed = (seed * 48271) % 2147483647; return seed % m; };
    const bad: string[] = [];
    for (let i = 0; i < 300; i++) {
      const shown = input.value;
      const a = rnd(shown.length + 1), b = a + rnd(Math.min(2, shown.length - a) + 1);
      let t = ''; const len = rnd(4); for (let j = 0; j < len; j++) t += ABC[rnd(ABC.length)];
      if (a === b && !t) t = ABC[rnd(ABC.length)];
      input.value = shown.slice(0, a) + t + shown.slice(b);
      input.setSelectionRange(a + t.length, a + t.length);
      input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: t ? 'insertText' : 'deleteContentBackward', data: t || null }));
      real = real.slice(0, a) + t + real.slice(b);
      if (input.value !== mask(real)) bad.push(i + ': ' + JSON.stringify(input.value));
      if (input.selectionStart !== a + t.length || input.selectionEnd !== a + t.length) bad.push(i + ': caret');
    }
    return { real, bad };
  }, KEY_B);
  expect(res.bad).toEqual([]);
  expect(res.real.length).toBeGreaterThan(0);
  await go(page);
  expect(rec[6]).toEqual({ provider: 'anthropic', key: res.real });

  await choose(page, 'provider', 'xai');
  await expect(key).toHaveValue('');
  await expect(page.locator('#go-reason')).toHaveText('Enter your xai API key to translate.');
  expect(rec).toHaveLength(7);
});

test('the Hebrew challenge sentence resolves to the intended senses', async ({ page }) => {
  await ready(page);
  await chip(page, 'mw-attention').click();
  await expect(page.locator('#text')).toHaveValue(MW_TEXT);
  await go(page);
  await expect(page.locator('#output')).toHaveText(MW_EXPECTED);
  const baselines = page.locator('li.reading.differs [data-row="baseline"]');
  const joined = (await baselines.allTextContents()).join(' | ');
  expect(joined).toContain('there');
  expect(joined).toContain('heart');
  await expect(page.locator('#readings')).toContainText('notice');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'report/screenshot.png', fullPage: true });
});

test('the rendered text is ASCII outside language data', async ({ page }) => {
  await ready(page);
  await chip(page, 'mw-attention').click();
  const resp = await go(page);
  expect(resp.status()).toBe(200);
  await expect(page.locator('#output')).toHaveText(MW_EXPECTED);
  await page.click('#about-open');
  await expect(page.locator('#about')).toBeVisible();
  await page.click('#about [data-close]');
  await expect(page.locator('#about')).toBeHidden();
  await page.click('#history-open');
  await expect(page.locator('#history')).toBeVisible();
  await expect(page.locator('#history-list .h-meta b')).toHaveCount(1);
  expect(await page.locator('#history-list .h-meta b').textContent()).toBe('HE to EN');
  await expect(page.locator('#history-list .h-meta b svg.ico-arrow')).toHaveCount(1);
  await page.click('#history [data-close]');
  await expect(page.locator('#history')).toBeHidden();

  const offenders = await page.evaluate(() => {
    const skip = '#text, #output, #readings, #examples .chip, .h-item';
    const out: string[] = [];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const p = n.parentElement;
      if (!p || p.closest(skip)) continue;
      const l = p.closest('[lang]');
      if (l && l.getAttribute('lang') !== 'en') continue;
      if (!/^[\x00-\x7F]*$/.test(n.nodeValue || '')) out.push((p.id || p.className || p.tagName) + ': ' + JSON.stringify(n.nodeValue));
    }
    return out;
  });
  expect(offenders).toEqual([]);

  await expect(page.locator('#solver-line svg.ico')).toHaveCount(3);
  expect(await page.locator('#examples svg.ico').count()).toBeGreaterThan(0);
  await expect(page.locator('.close svg.ico')).toHaveCount(2);
  await expect(page.locator('#load-state svg.ico-more')).toHaveCount(1);
  const pair = chip(page, 'mw-attention').locator('.chip-pair');
  expect(await pair.textContent()).toBe('HE to EN');
  await expect(pair.locator('svg.ico-arrow')).toHaveCount(1);
  expect(await page.locator('#readings .r-arrow svg.ico-arrow').count()).toBeGreaterThan(0);
  const tos = await page.locator('#readings .r-arrow .sr-only').allTextContents();
  expect(tos.length).toBeGreaterThan(0);
  expect(tos.every((t) => t === ' to ')).toBe(true);
  expect(await page.evaluate(() => Array.from(document.querySelectorAll('svg.ico use'))
    .map((u) => u.getAttribute('href') || '')
    .filter((h) => !(document.querySelector(h) instanceof SVGSymbolElement)))).toEqual([]);
  const box = await page.locator('#solver-line svg.ico-dot').first().boundingBox();
  expect(box!.width).toBeGreaterThan(0);
  expect(box!.height).toBeGreaterThan(0);
});

test.describe('copy in a secure context', () => {
  test.use({ baseURL: LOCALHOST });

  test('the English challenge renders right-to-left Hebrew; niqqud and copy', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await ready(page);
    await chip(page, 'llm-bark').click();
    await expect(page.locator('#source')).toHaveValue('en');
    await expect(page.locator('#target')).toHaveValue('he');
    await expect(page.locator('#text')).toHaveAttribute('dir', 'ltr');
    await go(page);
    await expect(page.locator('#output')).toHaveText(BARK_EXPECTED);
    await expect(page.locator('#output')).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('#output')).toHaveAttribute('lang', 'he');
    await expect(page.locator('#niqqud')).toBeVisible();
    await expect(page.locator('#niqqud')).toHaveAttribute('aria-pressed', 'true');
    const label = page.locator('#niqqud .marks-label');
    await expect(label).toHaveText(HE_MARKS);
    await expect(label).toHaveAttribute('lang', 'he');
    await expect(label).toHaveAttribute('dir', 'rtl');
    await expect(page.locator('#niqqud')).toHaveAccessibleName('Vowel marks ' + HE_MARKS);
    expect(((await page.locator('#readings').textContent()) || '').match(NIQ)).not.toBeNull();
    await page.click('#niqqud');
    await expect(page.locator('#niqqud')).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('#output')).toHaveText(BARK_EXPECTED.replace(NIQ, ''));
    expect(((await page.locator('#readings').textContent()) || '').match(NIQ)).toBeNull();
    await page.click('#copy');
    await expect(page.locator('#copy')).toHaveText('Copied');
    const shown = await page.locator('#output').textContent();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(shown);
    await page.waitForTimeout(1600);
    await expect(page.locator('#copy')).toHaveText('Copy');
  });
});

test('the Niqqud toggle keeps an error and the stale output', async ({ page }) => {
  await ready(page);
  await chip(page, 'llm-bark').click();
  await go(page);
  await expect(page.locator('#output')).toHaveText(BARK_EXPECTED);
  await stubTranslate(page, [{ status: 502, json: { error: 'upstream_failed' } }]);
  await go(page);
  await expect(page.locator('#error-text')).toBeVisible();
  await expect(page.locator('#out-pane')).toHaveClass(/stale/);
  await page.click('#niqqud');
  await expect(page.locator('#niqqud')).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('#error-text')).toBeVisible();
  await expect(page.locator('#error-code')).toBeVisible();
  await expect(page.locator('#out-pane')).toHaveClass(/stale/);
  await expect(page.locator('#output')).toHaveCSS('opacity', '0.4');
});

test('the vowel-mark toggle follows the target language: Arabic tashkeel, exact ranges, none for English', async ({ page }) => {
  test.setTimeout(90_000);
  const reg = await (await page.request.get('/api/languages')).json();
  const withMarks = reg.filter((l: any) => l.marks);
  expect(withMarks.map((l: any) => [l.code, l.marks.label])).toEqual([['ar', AR_MARKS], ['ur', UR_MARKS], ['arz', AR_MARKS], ['he', HE_MARKS]]);
  for (const l of withMarks) expect(l.marks.ranges).toEqual(l.code === 'he' ? HE_RANGES : ARAB_RANGES);
  const reading = { index: 0, token: 'teacher', prefix: '', reading: 'teacher', gloss: AR_GLOSS, choice: 0,
    candidates: [{ reading: 'teacher', gloss: AR_GLOSS }] };
  const rec = await stubTranslate(page, [
    { status: 200, json: { ...OK('anthropic'), text: AR_MARKED, source: 'en', target: 'ar', readings: [reading] } },
    { status: 200, json: { ...OK('anthropic'), text: SWEEP, source: 'en', target: 'ar' } },
    { status: 200, json: { ...OK('anthropic'), text: SWEEP, source: 'en', target: 'he' } },
  ]);
  await ready(page);
  await choose(page, 'provider', 'anthropic');
  await typeKey(page, KEY_A);
  await choose(page, 'source', 'English');
  await choose(page, 'target', 'Standard Arabic');
  await page.fill('#text', 'I am a teacher.');
  await go(page);
  const out = page.locator('#output'), toggle = page.locator('#niqqud'), label = toggle.locator('.marks-label');
  const gloss = page.locator('#readings .r-pick .r-gloss');
  await expect(out).toHaveText(AR_MARKED);
  await expect(out).toHaveAttribute('lang', 'ar');
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(label).toHaveText(AR_MARKS);
  await expect(label).toHaveAttribute('lang', 'ar');
  await expect(label).toHaveAttribute('dir', 'rtl');
  await expect(gloss).toHaveText(AR_GLOSS);
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect(out).toHaveText(AR_BARE);
  await expect(gloss).toHaveText(AR_GLOSS_BARE);
  await expect(page.locator('#readings .r-pick bdi').first()).toHaveText('teacher');
  await toggle.click();
  await expect(out).toHaveText(AR_MARKED);
  await toggle.click();

  expect(keep(ARAB_RANGES)).toHaveLength(0x0170 - 12);
  expect(keep(HE_RANGES)).toHaveLength(0x0170 - 51);
  await go(page);
  await expect.poll(() => out.textContent()).toBe(keep(ARAB_RANGES));
  await go(page);
  await expect.poll(() => out.textContent()).toBe(keep(HE_RANGES));
  await expect(label).toHaveText(HE_MARKS);
  await expect(label).toHaveAttribute('lang', 'he');
  await toggle.click();
  await expect.poll(() => out.textContent()).toBe(SWEEP);
  for (let i = 0; i < 10; i++) await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => out.textContent()).toBe(SWEEP);
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  expect(rec).toHaveLength(3);

  await page.unroute(STREAM);
  await choose(page, 'provider', 'demo');
  await chip(page, SEED).click();
  await go(page);
  await expect(out).toHaveText(EXPECTED);
  await expect(toggle).toBeHidden();
  await expect(page.locator('#readings')).toContainText(STORM);
});

test('an English target shows no vowel-mark toggle', async ({ page }) => {
  await ready(page);
  for (const [id, want] of [[SEED, EXPECTED], ['mw-attention', MW_EXPECTED]]) {
    await chip(page, id).click();
    await go(page);
    await expect(page.locator('#output')).toHaveText(want);
    await expect(page.locator('#niqqud')).toBeHidden();
    await expect(page.locator('#niqqud')).toHaveAttribute('hidden', '');
  }
  await chip(page, 'llm-bark').click();
  await go(page);
  await expect(page.locator('#niqqud')).toBeVisible();
  await chip(page, SEED).click();
  await go(page);
  await expect(page.locator('#niqqud')).toBeHidden();
});

async function emphasis(page: Page) {
  const e = await page.evaluate(() => {
    const out = document.getElementById('out-pane') as HTMLElement;
    const before = getComputedStyle(out, '::before');
    const head = getComputedStyle(out.querySelector('.pane-head') as Element);
    const inHead = getComputedStyle(document.querySelector('.pane-in .pane-head') as Element);
    return {
      height: before.height, bg: before.backgroundImage, anim: before.animationName,
      width: parseFloat(before.width), client: out.clientWidth,
      headBg: head.backgroundImage, inHeadBg: inHead.backgroundImage,
      outLang: getComputedStyle(document.getElementById('out-lang') as Element).color,
      inLang: getComputedStyle(document.getElementById('in-lang') as Element).color,
    };
  });
  expect(e.height).toBe('3px');
  expect(e.bg).toContain('rgb(13, 196, 179)');
  expect(e.anim).toBe('none');
  expect(Math.abs(e.width - e.client)).toBeLessThanOrEqual(1);
  expect(e.headBg).toContain('rgb(244, 253, 252)');
  expect(e.inHeadBg).toBe('none');
  expect(e.outLang).toBe('rgb(7, 122, 112)');
  expect(e.inLang).toBe('rgb(91, 112, 109)');
}

test('the output pane keeps its emphasis in every state', async ({ page }) => {
  await ready(page);
  await expect(page.locator('#placeholder')).toBeVisible();
  await expect(page.locator('#placeholder')).toHaveText('The translation appears here.');
  await emphasis(page);

  await chip(page, SEED).click();
  await go(page);
  await expect(page.locator('#output')).toHaveText(EXPECTED);

  let release!: () => void;
  const held = new Promise<void>((r) => { release = r; });
  await page.route(STREAM, async (route) => { await held; await route.continue(); });
  const done = page.waitForResponse((r) => r.url().includes('/api/translate'));
  await page.click('#go');
  await expect(page.locator('#out-pane')).toHaveClass(/loading/);
  await expect(page.locator('#output')).toHaveCSS('animation-name', 'pulse');
  await expect(page.locator('#out-pane')).toHaveCSS('animation-name', 'none');
  await expect(page.locator('#go')).toHaveClass(/busy/);
  await expect(page.locator('#go .spinner')).toBeVisible();
  await expect(page.locator('#progress')).toBeVisible();
  await expect(page.locator('#progress li[data-state=running]')).toHaveText('Checking your text');
  await emphasis(page);
  release();
  await done;
  await expect(page.locator('#out-pane')).not.toHaveClass(/loading/);
  await expect(page.locator('#progress')).toBeHidden();
  await page.unroute(STREAM);

  await stubTranslate(page, [{ status: 502, json: { error: 'upstream_failed' } }]);
  await go(page);
  await expect(page.locator('#error')).toBeVisible();
  await expect(page.locator('#out-pane #error')).toHaveCount(1);
  const errTop = (await page.locator('#error').boundingBox())!.y;
  const headBottom = await page.locator('#out-pane .pane-head').evaluate((h) => h.getBoundingClientRect().bottom);
  expect(errTop).toBeGreaterThanOrEqual(headBottom);
  await expect(page.locator('#out-pane')).toHaveClass(/stale/);
  await expect(page.locator('#output')).toHaveCSS('opacity', '0.4');
  await expect(page.locator('#notice')).toHaveCSS('opacity', '1');
  await expect(page.locator('#out-pane .pane-head')).toHaveCSS('opacity', '1');
  await emphasis(page);
  await page.unroute(STREAM);

  await chip(page, 'llm-bark').click();
  await go(page);
  await expect(page.locator('#output')).toHaveAttribute('dir', 'rtl');
  await expect(page.locator('#out-pane .pane-head')).toHaveCSS('direction', 'ltr');
  await expect(page.locator('#copy')).toBeVisible();
  await expect(page.locator('#niqqud')).toBeVisible();
  await emphasis(page);

  await page.focus('#text');
  await expect(page.locator('.pane-in')).toHaveCSS('border-top-color', 'rgb(13, 196, 179)');
  await page.focus('#copy');
  await expect(page.locator('#out-pane')).not.toHaveCSS('border-top-color', 'rgb(13, 196, 179)');
});

test('a language change after a result marks it stale and keeps its label', async ({ page }) => {
  test.setTimeout(90_000);
  await ready(page);
  await expect(page.locator('#out-lang')).toHaveText('English');
  await choose(page, 'target', 'Hindi');
  await expect(page.locator('#out-lang')).toHaveText('Hindi');
  await expect(page.locator('#out-pane')).not.toHaveClass(/stale/);
  await chip(page, 'llm-bark').click();
  await expect(page.locator('#out-lang')).toHaveText('Hebrew');
  expect((await go(page)).status()).toBe(200);
  await expect(page.locator('#output')).toHaveText(BARK_EXPECTED);
  await expect(page.locator('#out-lang')).toHaveText('Hebrew');
  await expect(page.locator('#out-pane')).not.toHaveClass(/stale/);

  await choose(page, 'target', 'Hindi');
  await expect(page.locator('#target')).toHaveValue('hi');
  await expect(page.locator('#out-pane')).toHaveClass(/stale/);
  await expect(page.locator('#out-lang')).toHaveText('Hebrew');
  await expect(page.locator('#output')).toHaveText(BARK_EXPECTED);
  await expect(page.locator('#output')).toHaveCSS('opacity', '0.4');
  await emphasis(page);
  for (const name of ['Standard Arabic', 'Hindi', 'Standard Arabic', 'Hindi']) {
    await choose(page, 'target', name);
    await expect(page.locator('#out-pane'), name).toHaveClass(/stale/);
    await expect(page.locator('#out-lang'), name).toHaveText('Hebrew');
  }
  await expect(page.locator('#target')).toHaveValue('hi');

  const rec = await stubTranslate(page, [{ status: 200, json: { ...OK('anthropic'), source: 'en', target: 'hi' } }]);
  await choose(page, 'provider', 'anthropic');
  await typeKey(page, KEY_A);
  await go(page);
  await expect(page.locator('#output')).toHaveText('stub render');
  await expect(page.locator('#out-lang')).toHaveText('Hindi');
  await expect(page.locator('#out-pane')).not.toHaveClass(/stale/);
  expect(rec).toEqual([{ provider: 'anthropic', key: KEY_A }]);

  await chip(page, 'mw-attention').click();
  await expect(page.locator('#out-pane')).toHaveClass(/stale/);
  await expect(page.locator('#out-lang')).toHaveText('Hindi');

  await choose(page, 'source', 'English');
  await expect(page.locator('#target')).toHaveValue('he');
  await expect(page.locator('#out-pane')).toHaveClass(/stale/);
  await expect(page.locator('#out-lang')).toHaveText('Hindi');
  await expect(page.locator('#output')).toHaveText('stub render');

  await page.click('#home');
  await expect(page.locator('#placeholder')).toBeVisible();
  await expect(page.locator('#out-pane')).not.toHaveClass(/stale/);
  await expect(page.locator('#out-lang')).toHaveText('Hebrew');
});

type Row = [string, { status: number; json?: unknown; body?: string }, string, string[]];

const ERRORS: Row[] = [
  ['bad_request', { status: 422, json: { error: 'bad_request' } },
    'The server refused the request. The text may be empty or longer than its limit (4,000 characters by default).',
    ['HTTP 422', 'bad_request']],
  ['unknown_language', { status: 400, json: { error: 'unknown_language' } },
    "That language isn't available on this server.", ['HTTP 400', 'unknown_language']],
  ['same_language', { status: 400, json: { error: 'same_language' } },
    'Pick two different languages.', ['HTTP 400', 'same_language']],
  ['unknown_provider', { status: 400, json: { error: 'unknown_provider' } },
    "That provider isn't available on this server.", ['HTTP 400', 'unknown_provider']],
  ['unknown_model', { status: 400, json: { error: 'unknown_model' } },
    "This server doesn't offer that model for this provider.", ['HTTP 400', 'unknown_model']],
  ['unknown_effort', { status: 400, json: { error: 'unknown_effort' } },
    "That model doesn't take this effort level.", ['HTTP 400', 'unknown_effort']],
  ['bad_key', { status: 400, json: { error: 'bad_key' } },
    "That key doesn't look right. A key is 16 to 512 printable ASCII characters with no spaces.",
    ['HTTP 400', 'bad_key']],
  ['key_required', { status: 400, json: { error: 'key_required' } },
    'This provider needs your API key.', ['HTTP 400', 'key_required']],
  ['provider_not_configured', { status: 503, json: { error: 'provider_not_configured' } },
    "This server isn't set up for that provider.", ['HTTP 503', 'provider_not_configured']],
  ['demo_examples_only', { status: 422, json: { error: 'demo_examples_only' } },
    'The demo provider accepts only the example sentences, each with its own language pair. Pick an example, or use a provider with your own key.',
    ['HTTP 422', 'demo_examples_only']],
  ['blocked input', { status: 422, json: { error: 'blocked_content', category: 'weapons', stage: 'input' } },
    'The content gate refused this text (weapons).', ['HTTP 422', 'blocked_content']],
  ['blocked output', { status: 422, json: { error: 'blocked_content', category: 'sexual', stage: 'output' } },
    'The content gate refused the translation (sexual content).', ['HTTP 422', 'blocked_content']],
  ['gate_unavailable', { status: 502, json: { error: 'gate_unavailable', stage: 'input' } },
    "The content check couldn't give a verdict, so the request was refused. If you're using your own key, check that it is valid and has quota.",
    ['HTTP 502', 'gate_unavailable', 'stage: input']],
  ['upstream_failed', { status: 502, json: { error: 'upstream_failed' } },
    'The provider failed while rendering the translation. Try again.', ['HTTP 502', 'upstream_failed']],
  ['quota_exhausted', { status: 503, json: { error: 'quota_exhausted' } },
    "Your openai key was refused for quota or rate (the provider answered 429).", ['HTTP 503', 'quota_exhausted']],
  ['demo_limit', { status: 429, json: { error: 'demo_limit', attempts: 3 } }, LIMIT, ['HTTP 429', 'demo_limit']],
  ['a non-JSON 504', { status: 504, body: 'gateway' },
    'Something went wrong on the server.', ['HTTP 504', 'request failed']],
];

test('every error code shows its sentence and its own code line', async ({ page }) => {
  await stubTranslate(page, ERRORS.map(([, answer]) => answer));
  await ready(page);
  await choose(page, 'provider', 'openai');
  await typeKey(page, KEY_A);
  await chip(page, 'mw-attention').click();
  for (const [name, answer, sentence, code] of ERRORS) {
    const resp = await go(page);
    expect(resp.status(), name).toBe(answer.status);
    await expect(page.locator('#error-text'), name).toHaveText(sentence);
    await expect.poll(() => dotParts(page.locator('#error-code')), { message: name }).toEqual(code);
    await expect(page.locator('#error-code svg.ico-dot'), name).toHaveCount(code.length - 1);
  }
  await page.unroute(STREAM);
  await page.route(STREAM, (route) => route.abort());
  await goFails(page);
  await expect(page.locator('#error-text')).toHaveText("Couldn't reach the server, or it didn't answer in time.");
  await expect.poll(() => dotParts(page.locator('#error-code'))).toEqual(['network', 'request failed']);
  await expect(page.locator('#go')).not.toHaveClass(/busy/);
  await expect(page.locator('#go')).toBeEnabled();
  await page.unroute(STREAM);
  await stubTranslate(page, [{
    status: 200,
    json: {
      ...OK('openai'), notes: ['script_mismatch'], verify: { ok: false, notes: [{ token: 'x', expected: 'y' }] },
      readings: [{ index: 0, token: 'x', prefix: '', reading: 'x', gloss: '', candidates: [{ reading: 'x', gloss: '' }], choice: 0 }],
      greedy: [{ index: 0, reading: 'x', gloss: '' }],
    },
  }]);
  await go(page);
  await expect(page.locator('#flags li')).toHaveText([
    "Repair note: the output's script did not match English (script_mismatch).",
    'Verify (a substring check): one chosen sense was not found in the output: x to y',
  ]);
  await expect(page.locator('#flags li .flag-arrow svg.ico-arrow')).toHaveCount(1);
  await expect(page.locator('#readings .r-none svg.ico-dash')).toHaveCount(2);
  expect(await page.locator('#readings .r-none .sr-only').allTextContents()).toEqual(['no gloss', 'no gloss']);
  expect(await dotParts(page.locator('#solver-line'))).toEqual([
    '1 word with candidates', 'baseline differs on 0', 'toy solver score 0 ' + SCORE_NOTE, '0 option pairs scored between neighbouring words (a word without candidates counts as one option)',
  ]);
});

test('swap, history, theme, home and About', async ({ page }) => {
  await ready(page);
  await chip(page, 'llm-bark').click();
  await go(page);
  await expect(page.locator('#output')).toHaveText(BARK_EXPECTED);
  await page.click('#swap');
  await expect(page.locator('#source')).toHaveValue('he');
  await expect(page.locator('#target')).toHaveValue('en');
  await expect(page.locator('#text')).toHaveValue(BARK_EXPECTED);
  await expect(page.locator('#placeholder')).toBeVisible();
  await expect(page.locator('#readings-sec')).toBeHidden();
  await expect(page.locator('#history-count')).toHaveText('1');
  await page.click('#theme');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('#theme')).toHaveAttribute('aria-label', 'Switch to light mode');
  await page.reload();
  await expect(page.locator('#app')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const note = 'The demo provider needs no key and accepts only the example sentences. With a keyed provider, two content classifier calls on your key check your text and then its translation in context.';
  await expect(page.locator('#demo-note')).toBeVisible();
  await expect(page.locator('#demo-note')).toHaveText(note);
  await choose(page, 'provider', 'anthropic');
  await expect(page.locator('#demo-note')).toBeVisible();
  await expect(page.locator('#demo-note')).toHaveText(note);
  await page.fill('#text', 'something to clear');
  await page.click('#home');
  await expect(page.locator('#text')).toHaveValue('');
  await page.click('#about-open');
  await expect(page.locator('#about')).toBeVisible();
  await expect(page.locator('#about-keyed')).toHaveText('anthropic, xai, gemini, openai');
  await expect(page.locator('#about-keyed-row')).toHaveText('anthropic, xai, gemini, openai: your own key, sent with each request only, never stored or logged. Two content classifier calls on your key check the text and then its translation.');
  await expect(page.locator('#about')).toContainText('never stored or logged');
  await expect(page.locator('#about')).toContainText(SHAARA);
  await page.click('#about [data-close]');
  await expect(page.locator('#about')).toBeHidden();
});

test('rapid clicks send one request; history caps at 30', async ({ page }) => {
  test.setTimeout(180_000);
  let posts = 0;
  page.on('request', (r) => { if (r.url().includes('/api/translate') && r.method() === 'POST') posts++; });
  await ready(page);
  await chip(page, SEED).click();
  await page.evaluate(() => {
    for (let i = 0; i < 3; i++) (document.getElementById('go') as HTMLButtonElement).click();
  });
  await expect(page.locator('#output')).toHaveText(EXPECTED);
  expect(posts).toBe(1);
  for (let i = 0; i < 31; i++) {
    await chip(page, SEED).click();
    await go(page);
  }
  await expect(page.locator('#history-count')).toHaveText('9+');
  await expect(page.locator('#solver-line svg.ico-dot')).toHaveCount(3);
  await page.click('#history-open');
  await expect(page.locator('#history-list .h-item')).toHaveCount(30);
  await expect(page.locator('#history-list .h-meta b svg.ico-arrow')).toHaveCount(30);
});

test('the pickers follow /api/providers: models, efforts, defaults and the request body', async ({ page }) => {
  test.setTimeout(180_000);
  const list = await (await page.request.get('/api/providers')).json();
  expect(list.find((p: any) => p.name === 'demo').models).toEqual([]);
  for (const [name, rows] of Object.entries(MODELS)) {
    expect(list.find((p: any) => p.name === name).models, name).toEqual(
      rows.map(([id, efforts], i) => ({ id, efforts, default: i === 0 })));
  }
  const bodies: any[] = [];
  await stubTranslate(page, [{ status: 200, json: OK('stub') }], bodies);
  await ready(page);
  await expect(page.locator('#model-field')).toBeHidden();
  await expect(page.locator('#effort-field')).toBeHidden();
  const names = (id: string) => page.locator(`#${id}-list [role=option] .dd-name`);
  const tagsOf = (id: string) => page.locator(`#${id}-list [role=option] .dd-tag`);
  for (const [name, rows] of Object.entries(MODELS)) {
    await choose(page, 'provider', name);
    await expect(page.locator('#model-field'), name).toBeVisible();
    await expect(page.locator('#model-cur'), name).toHaveText(rows[0][0]);
    await ddButton(page, 'model').click();
    await expect(names('model')).toHaveText(rows.map(([id]) => id));
    await expect(tagsOf('model')).toHaveText(['Default']);
    await ddButton(page, 'model').click();
    await expect(page.locator('#model-list')).toBeHidden();
    for (const [id, efforts] of rows) {
      await choose(page, 'model', id);
      await expect(page.locator('#model-cur'), id).toHaveText(id);
      if (!efforts.length) { await expect(page.locator('#effort-field'), id).toBeHidden(); continue; }
      await expect(page.locator('#effort-field'), id).toBeVisible();
      await expect(page.locator('#effort-cur'), id).toHaveText(efforts[0]);
      await ddButton(page, 'effort').click();
      await expect(names('effort'), id).toHaveText(efforts);
      await expect(tagsOf('effort'), id).toHaveText(['Default']);
      await ddButton(page, 'effort').click();
      await expect(page.locator('#effort-list')).toBeHidden();
    }
  }

  await choose(page, 'provider', 'anthropic');
  await typeKey(page, KEY_A);
  await chip(page, 'mw-attention').click();
  await choose(page, 'model', 'claude-opus-5-5');
  await expect(page.locator('#effort-cur')).toHaveText('low');
  await choose(page, 'effort', 'high');
  await page.click('#go');
  await expect.poll(() => bodies.length).toBe(1);
  await expect(page.locator('#output')).toHaveText('stub render');
  await choose(page, 'provider', 'xai');
  await typeKey(page, KEY_A);
  await page.click('#go');
  await expect.poll(() => bodies.length).toBe(2);
  await choose(page, 'provider', 'openai');
  await typeKey(page, KEY_A);
  await page.click('#go');
  await expect.poll(() => bodies.length).toBe(3);
  await choose(page, 'provider', 'demo');
  await expect(page.locator('#model-field')).toBeHidden();
  await expect(page.locator('#effort-field')).toBeHidden();
  await page.click('#go');
  await expect.poll(() => bodies.length).toBe(4);
  const base = { text: MW_TEXT, source: 'he', target: 'en' };
  expect(bodies).toEqual([
    { ...base, provider: 'anthropic', model: 'claude-opus-5-5', effort: 'high' },
    { ...base, provider: 'xai', model: 'grok-4.20-0309-non-reasoning' },
    { ...base, provider: 'openai', model: 'gpt-6-luna', effort: 'none' },
    { ...base, provider: 'demo' },
  ]);

  await page.click('#history-open');
  await page.locator('.h-item').filter({ hasText: 'anthropic' }).click();
  await expect(page.locator('#provider-cur')).toHaveText('anthropic');
  await expect(page.locator('#model-cur')).toHaveText('claude-opus-5-5');
  await expect(page.locator('#effort-cur')).toHaveText('high');
});

test('the steps follow the stream, an in-stream refusal and a stream cut short', async ({ page }) => {
  test.setTimeout(90_000);
  const stream = await holdStream(page);
  await ready(page);
  await choose(page, 'provider', 'openai');
  await typeKey(page, KEY_A);
  await chip(page, 'mw-attention').click();
  const li = page.locator('#progress li');
  const states = () => li.evaluateAll((ls) => ls.map((l) => (l as HTMLElement).dataset.state));
  const current = () => li.evaluateAll((ls) => ls.map((l) => l.getAttribute('aria-current')));
  await expect(page.locator('#progress')).toBeHidden();

  await page.click('#go');
  await expect(page.locator('#progress')).toBeVisible();
  await expect(li).toHaveText(['Checking your text', 'Translating', 'Checking the translation']);
  await expect.poll(states).toEqual(['running', 'pending', 'pending']);
  expect(await current()).toEqual(['step', null, null]);
  await stream.push({ stage: 'input' });
  await expect.poll(states).toEqual(['running', 'pending', 'pending']);
  await stream.push({ stage: 'translate' });
  await expect.poll(states).toEqual(['done', 'running', 'pending']);
  expect(await current()).toEqual([null, 'step', null]);
  await stream.push({ stage: 'output' });
  await expect.poll(states).toEqual(['done', 'done', 'running']);
  expect(await current()).toEqual([null, null, 'step']);
  await stream.push(OK('openai'));
  await stream.end();
  await expect(page.locator('#output')).toHaveText('stub render');
  await expect(page.locator('#progress')).toBeHidden();

  await page.click('#go');
  await expect(page.locator('#progress')).toBeVisible();
  await stream.push({ stage: 'input' });
  await stream.push({ error: 'blocked_content', status: 422, category: 'weapons', stage: 'input' });
  await stream.end();
  await expect(page.locator('#error-text')).toHaveText('The content gate refused this text (weapons).');
  await expect.poll(() => dotParts(page.locator('#error-code'))).toEqual(['HTTP 422', 'blocked_content']);
  await expect(page.locator('#progress')).toBeHidden();

  await page.click('#go');
  await expect(page.locator('#progress')).toBeVisible();
  await stream.push({ stage: 'input' });
  await stream.push({ stage: 'translate' });
  await stream.end();
  await expect(page.locator('#error-text')).toHaveText("Couldn't reach the server, or it didn't answer in time.");
  await expect.poll(() => dotParts(page.locator('#error-code'))).toEqual(['network', 'request failed']);
  await expect(page.locator('#progress')).toBeHidden();
  await expect(page.locator('#go')).toBeEnabled();

  const sent = { text: MW_TEXT, source: 'he', target: 'en', provider: 'openai', model: 'gpt-6-luna', effort: 'none' };
  expect(await stream.bodies()).toEqual([sent, sent, sent]);
});

test('the info icon names itself, shows its line on focus, hover and click, and fits at 390 px', async ({ page }) => {
  test.setTimeout(90_000);
  const info = page.locator('#info'), tip = page.locator('#info-tip');
  await ready(page);
  await expect(info).toHaveAccessibleName(INFO_NAME);
  await expect(info).toHaveAccessibleDescription(TIP);
  await expect(tip).toBeHidden();
  await ddButton(page, 'provider').focus();
  await page.keyboard.press('Tab');
  await expect(info).toBeFocused();
  await expect(tip).toBeVisible();
  await expect(tip).toHaveText(TIP);
  await page.keyboard.press('Escape');
  await expect(tip).toBeHidden();
  await page.locator('#text').focus();
  await page.mouse.move(2, 2);
  await info.hover();
  await expect(tip).toBeVisible();
  await page.mouse.move(2, 2);
  await expect(tip).toBeHidden();
  await info.click();
  await page.mouse.move(2, 2);
  await expect(tip).toBeVisible();
  await page.click('#text');
  await expect(tip).toBeHidden();

  await page.setViewportSize({ width: 390, height: 844 });
  await choose(page, 'provider', 'openai');
  const box = async (loc: Locator) => (await loc.boundingBox())!;
  const [p, m, e, i] = [await box(ddButton(page, 'provider')), await box(ddButton(page, 'model')),
    await box(ddButton(page, 'effort')), await box(info)];
  for (const b of [p, m, e, i]) {
    expect(b.x).toBeGreaterThanOrEqual(0);
    expect(b.x + b.width).toBeLessThanOrEqual(390);
  }
  expect(Math.abs(m.y - e.y)).toBeLessThanOrEqual(1);
  expect(m.y).toBeGreaterThanOrEqual(p.y + p.height);
  expect(m.x + m.width).toBeLessThanOrEqual(e.x);
  expect(i.x).toBeGreaterThanOrEqual(p.x + p.width);
  await info.click();
  await expect(tip).toBeVisible();
  const t = await box(tip);
  expect(t.x).toBeGreaterThanOrEqual(0);
  expect(t.x + t.width).toBeLessThanOrEqual(390);
});

test('the disclaimer sits under the tagline, shows the address from /api/health only when there is one, and stays through a load failure', async ({ page }) => {
  const health = await (await page.request.get('/api/health')).json();
  const shown = /^[^\s@<>"]+@[^\s@<>"]+$/.test(health.contact);
  await ready(page);
  const order = await page.evaluate(() => {
    const t = document.querySelector('.tagline') as Element, d = document.getElementById('disclaimer') as Element;
    return t.nextElementSibling === d;
  });
  expect(order).toBe(true);
  await expect(page.locator('#disclaimer')).toBeVisible();
  await expect(page.locator('#disclaimer')).toHaveText(shown ? DISCLAIMER + CONTACT_LEAD + health.contact + '.' : DISCLAIMER, { useInnerText: true });
  if (shown) await expect(page.locator('#contact')).toHaveAttribute('href', 'mailto:' + health.contact);
  else await expect(page.locator('#contact-line')).toBeHidden();

  const mocked = 'someone@example.com';
  await page.route('**/api/health', (route) => route.fulfill({ json: { ok: true, service: 'mordecai', contact: mocked } }));
  await page.reload();
  await expect(page.locator('#app')).toBeVisible();
  await expect(page.locator('#disclaimer')).toHaveText(DISCLAIMER + CONTACT_LEAD + mocked + '.', { useInnerText: true });
  await expect(page.locator('#contact')).toHaveAttribute('href', 'mailto:' + mocked);
  await page.unroute('**/api/health');

  for (const contact of ['', 'not an address']) {
    await page.route('**/api/health', (route) => route.fulfill({ json: { ok: true, service: 'mordecai', contact } }));
    await page.reload();
    await expect(page.locator('#app')).toBeVisible();
    await expect(page.locator('#disclaimer')).toHaveText(DISCLAIMER, { useInnerText: true });
    await expect(page.locator('#contact-line')).toBeHidden();
    await page.unroute('**/api/health');
  }

  await page.route('**/api/languages', (route) => route.abort());
  await page.reload();
  await expect(page.locator('#load-state.failed')).toBeVisible();
  await expect(page.locator('#disclaimer')).toBeVisible();
  await expect(page.locator('#disclaimer')).toContainText(DISCLAIMER);
});
