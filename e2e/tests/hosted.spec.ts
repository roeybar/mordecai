import { test, expect } from '@playwright/test';
import {
  ATTEMPTS, BANNER_DEMO, BANNER_HOSTED, GOOGLE, HOSTED, LIMIT, MW_TEXT, OK, QUOTA, REGION,
  bannerKeyed, choose, chip, ddButton, dotParts, go, ready, stubHosted, stubTranslate, typeKey,
} from './helpers';

test.use({ colorScheme: 'light' });

const KEY_A = 'placeholder-key-A-000000';
const KEY_B = 'placeholder-key-B-000000';
const HOSTED_LABEL = 'gemini (hosted)';

test('a fresh clone offers no hosted provider and shows no banner', async ({ page }) => {
  await ready(page);
  await expect(page.locator('#hosted')).toBeHidden();
  await expect(page.locator('#provider-cur')).toHaveText('demo');
  await ddButton(page, 'provider').click();
  const options = page.locator('#provider-list [role=option]');
  await expect(options.locator('.dd-name')).toHaveText(['demo', 'anthropic', 'xai', 'gemini', 'openai']);
  await expect(options.locator('.dd-tag')).toHaveText(
    ['Examples only', 'Your key', 'Your key', 'Your key', 'Your key']);
  const resp = await page.request.get('/api/providers');
  const list = await resp.json();
  expect(list.map((p: { name: string }) => p.name)).toEqual(['demo', 'anthropic', 'xai', 'gemini', 'openai']);
  expect(list.every((p: { hosted: boolean }) => p.hosted === false)).toBe(true);
});

test("the hosted provider shows Google's terms, the attempts line and the region line, all visible, in order", async ({ page }) => {
  await stubHosted(page);
  await ready(page);
  await expect(page.locator('#hosted')).toBeVisible();
  await expect(page.locator('#hosted-head')).toHaveText(BANNER_HOSTED);
  await expect(page.locator('#hosted-terms')).toBeVisible();
  await expect(page.locator('#hosted-terms')).toHaveText(GOOGLE);
  await expect(page.locator('#hosted-attempts')).toBeVisible();
  await expect(page.locator('#hosted-attempts')).toHaveText(ATTEMPTS);
  await expect(page.locator('#hosted-region')).toBeVisible();
  await expect(page.locator('#hosted-region')).toHaveText(REGION);
  const ys: number[] = [];
  for (const id of ['hosted-head', 'hosted-terms', 'hosted-attempts', 'hosted-region']) {
    ys.push((await page.locator(`#${id}`).boundingBox())!.y);
  }
  expect([...ys].sort((a, b) => a - b)).toEqual(ys);
  expect(new Set(ys).size).toBe(4);
  await expect(page.locator('#hosted details')).toHaveCount(0);
  await expect(page.locator('#provider')).toHaveValue('hosted');
  await expect(page.locator('#provider-cur')).toHaveText(HOSTED_LABEL);
  await expect(page.locator('#key-row')).toBeHidden();
  await expect(page.locator('#demo-note')).toBeVisible();
  await expect(page.locator('#provider-notice')).toHaveText(HOSTED.notice);
});

test('the banner follows the selected provider', async ({ page }) => {
  await stubHosted(page);
  await ready(page);
  for (const [name, vendor] of [['anthropic', 'Anthropic'], ['xai', 'xAI'], ['gemini', 'Google Gemini'], ['openai', 'OpenAI']]) {
    await choose(page, 'provider', name);
    await expect(page.locator('#hosted-head')).toHaveText(bannerKeyed(vendor));
    await expect(page.locator('#hosted-terms')).toBeHidden();
    await expect(page.locator('#hosted-attempts')).toBeVisible();
    await expect(page.locator('#hosted-region')).toBeVisible();
    const text = await page.locator('#hosted').innerText();
    expect(text).not.toContain("Google's Gemini API");
    expect(text).not.toContain('Unpaid Services');
  }
  await choose(page, 'provider', 'demo');
  await expect(page.locator('#hosted-head')).toHaveText(BANNER_DEMO);
  await expect(page.locator('#hosted-terms')).toBeHidden();
  await choose(page, 'provider', HOSTED_LABEL);
  await expect(page.locator('#hosted-head')).toHaveText(BANNER_HOSTED);
  await expect(page.locator('#hosted-terms')).toBeVisible();
});

test('refusal copy: hosted texts for the hosted provider, generic sentences elsewhere', async ({ page }) => {
  await stubHosted(page);
  const rec = await stubTranslate(page, [
    { status: 429, json: { error: 'demo_limit', attempts: 3 } },
    { status: 503, json: { error: 'quota_exhausted' } },
    { status: 429, json: { error: 'demo_limit', attempts: 3 } },
    { status: 503, json: { error: 'quota_exhausted' } },
    { status: 429, json: { error: 'demo_limit', attempts: 3 } },
  ]);
  await ready(page);
  await chip(page, 'hair-eyebrow-storm-boat').click();
  await go(page);
  await expect(page.locator('#error-text')).toHaveText(LIMIT);
  await expect.poll(() => dotParts(page.locator('#error-code'))).toEqual(['HTTP 429', 'demo_limit']);
  await go(page);
  await expect(page.locator('#error-text')).toHaveText(QUOTA);
  await expect.poll(() => dotParts(page.locator('#error-code'))).toEqual(['HTTP 503', 'quota_exhausted']);
  await choose(page, 'provider', 'openai');
  await typeKey(page, KEY_A);
  await go(page);
  await expect(page.locator('#error-text')).toHaveText(LIMIT);
  await go(page);
  await expect(page.locator('#error-text')).toHaveText("Your openai key was refused for quota or rate (the provider answered 429).");
  await choose(page, 'provider', 'demo');
  await go(page);
  await expect(page.locator('#error-text')).toHaveText(LIMIT);
  expect(rec.map((r) => r.provider)).toEqual(['hosted', 'hosted', 'openai', 'openai', 'demo']);
});

test('a key typed for one vendor never reaches another', async ({ page }) => {
  await stubHosted(page);
  const rec = await stubTranslate(page, [{ status: 200, json: OK('stub') }]);
  await ready(page);
  await choose(page, 'provider', 'anthropic');
  await typeKey(page, KEY_A);
  await choose(page, 'provider', 'openai');
  await expect(page.locator('#key')).toHaveValue('');
  await typeKey(page, KEY_B);
  await chip(page, 'mw-attention').click();
  await go(page);
  await choose(page, 'provider', HOSTED_LABEL);
  await go(page);
  expect(rec).toEqual([{ provider: 'openai', key: KEY_B }, { provider: 'hosted', key: null }]);
});

test('the hosted provider shows its one model and effort read-only and sends them', async ({ page }) => {
  await stubHosted(page);
  const bodies: any[] = [];
  await stubTranslate(page, [{ status: 200, json: OK('hosted') }], bodies);
  await ready(page);
  await expect(page.locator('#provider-cur')).toHaveText(HOSTED_LABEL);
  await expect(page.locator('#model-cur')).toHaveText('gemini-3.5-flash');
  await expect(page.locator('#effort-cur')).toHaveText('minimal');
  await expect(ddButton(page, 'model')).toBeDisabled();
  await expect(ddButton(page, 'effort')).toBeDisabled();
  await choose(page, 'provider', 'gemini');
  await expect(ddButton(page, 'model')).toBeEnabled();
  await expect(ddButton(page, 'effort')).toBeEnabled();
  await choose(page, 'provider', HOSTED_LABEL);
  await expect(ddButton(page, 'model')).toBeDisabled();
  await expect(ddButton(page, 'effort')).toBeDisabled();
  await expect(page.locator('#model-cur')).toHaveText('gemini-3.5-flash');
  await expect(page.locator('#effort-cur')).toHaveText('minimal');
  await chip(page, 'mw-attention').click();
  await go(page);
  await expect(page.locator('#output')).toHaveText('stub render');
  expect(bodies).toEqual([{ text: MW_TEXT, source: 'he', target: 'en', provider: 'hosted', model: 'gemini-3.5-flash', effort: 'minimal' }]);
});
