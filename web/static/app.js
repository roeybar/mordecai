(() => {
'use strict';
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const MAX = 4000;
const norm = (s) => (s || '').trim().normalize('NFC');
const SVGNS = 'http://www.w3.org/2000/svg';
const ico = (name) => { const s = document.createElementNS(SVGNS, 'svg'); s.setAttribute('class', 'ico ico-' + name); s.setAttribute('aria-hidden', 'true'); const u = document.createElementNS(SVGNS, 'use'); u.setAttribute('href', '#i-' + name); s.append(u); return s; };
const arrowTo = (cls) => { const a = el('span', cls); a.append(ico('arrow'), el('span', 'sr-only', ' to ')); return a; };
const dotted = (node, parts) => parts.forEach((t, i) => { if (i) node.append(' ', ico('dot'), ' '); node.append(t); });
const maskKey = (k) => k.slice(0, 4) + '*'.repeat(Math.max(0, k.length - 4));
const CAT = { child_safety: 'child safety', sexual: 'sexual content', weapons: 'weapons', illegal: 'illegal activity', fraud: 'fraud', self_harm: 'self-harm', hate: 'hate', violence: 'violence', profanity: 'profanity' };
const HOSTED_TEXT = {
  demo_limit: 'This demo allows 3 attempts per visitor in 24 hours. Run it on your own machine from the repository to continue.',
  quota_exhausted: "The demo's quota is used up for now; try again later or run it on your own machine.",
};
const VENDOR = { anthropic: 'Anthropic', xai: 'xAI', gemini: 'Google Gemini', openai: 'OpenAI' };
const BANNER_HOSTED = "Hosted demo. Your text and its translation are sent to Google's Gemini API.";
const BANNER_DEMO = 'Hosted demo. With the demo provider your text does not leave this server: the translation is a word-by-word gloss built from the demo frames.';
const STAGES = ['input', 'translate', 'output'];
const bannerKeyed = (v) => `Hosted demo. Your text and its translation are sent to ${v}'s API with your key, used for this request only, never stored or logged.`;
const S = { langs: [], by: {}, providers: [], examples: [], result: null, busy: false, niqqud: true, history: [], prevSrc: null, prevTgt: null, key: '', keyShown: '' };

const ui = {
  load: $('load-state'), app: $('app'), hosted: $('hosted'),
  source: $('source'), target: $('target'), srcStatus: $('source-status'), tgtStatus: $('target-status'), swap: $('swap'),
  provider: $('provider'), provNotice: $('provider-notice'), keyRow: $('key-row'), key: $('key'),
  text: $('text'), count: $('count'), inLang: $('in-lang'), outLang: $('out-lang'), examples: $('examples'), demoNote: $('demo-note'),
  go: $('go'), reason: $('go-reason'), outPane: $('out-pane'), output: $('output'), placeholder: $('placeholder'), error: $('error'),
  flags: $('flags'), notice: $('notice'), niqqud: $('niqqud'), marksLabel: document.querySelector('#niqqud .marks-label'), copy: $('copy'),
  rSec: $('readings-sec'), readings: $('readings'), rEmpty: $('readings-empty'), solver: $('solver-line'),
  home: $('home'), about: $('about'), history: $('history'), hList: $('history-list'), hEmpty: $('history-empty'), hCount: $('history-count'),
  hostedHead: $('hosted-head'), hostedTerms: $('hosted-terms'), aboutKeyed: $('about-keyed'), aboutKeyedRow: $('about-keyed-row'),
  model: $('model'), effort: $('effort'), modelField: $('model-field'), effortField: $('effort-field'), progress: $('progress'), infoWrap: $('info-wrap'), info: $('info'), contactLine: $('contact-line'), contact: $('contact'),
};

const lang = (code) => S.by[code] || { code, name: code, direction: 'ltr', status: '' };
const prov = () => S.providers.find((p) => p.name === ui.provider.value) || S.providers[0];
const models = () => prov().models || []; const curModel = () => models().find((m) => m.id === ui.model.value) || null;
const u4 = (cp) => '\\u' + cp.toString(16).padStart(4, '0');
// A language's optional marks as a RegExp built from its registry ranges, or null when it has no marks.
const marksRe = (code) => { const m = lang(code).marks; return m ? new RegExp('[' + m.ranges.map(([a, b]) => u4(a) + (b > a ? '-' + u4(b) : '')).join('') + ']', 'g') : null; };
// With the toggle off, text in a language with marks is shown without them.
const strip = (s, code) => { const re = S.niqqud ? null : marksRe(code); return re ? (s || '').replace(re, '') : s; };
const setDir = (node, code) => { const l = lang(code); node.dir = l.direction; node.lang = code; };
const bidi = (text, code, cls) => { const b = el('bdi', cls, S.result && code === S.result.target ? strip(text, code) : text); setDir(b, code); return b; };

function setStatus(node, code) {
  const l = lang(code); const ok = l.status === 'VERIFIED';
  node.textContent = l.status;
  node.className = 'status ' + (ok ? 'ok' : 'unverified');
  node.title = l.status;
}

function syncBanner(p) {
  if (ui.hosted.hidden) return;
  ui.hostedHead.textContent = p.hosted ? BANNER_HOSTED : p.needs_key ? bannerKeyed(VENDOR[p.name] || p.label) : BANNER_DEMO;
  ui.hostedTerms.hidden = !p.hosted;
}

function matchExample(text, s, t) {
  const n = norm(text);
  return S.examples.find((e) => norm(e.text) === n && e.source === s && e.target === t) || null;
}

function sync() {
  const s = ui.source.value, t = ui.target.value, p = prov();
  dds.forEach((d) => d.update());
  setDir(ui.text, s);
  ui.inLang.textContent = lang(s).name;
  ui.outLang.textContent = lang(S.result ? S.result.target : t).name;
  setStatus(ui.srcStatus, s); setStatus(ui.tgtStatus, t);
  ui.keyRow.hidden = !p.needs_key;
  ui.provNotice.textContent = p.notice;
  const cm = curModel(); ui.modelField.hidden = !models().length; ui.effortField.hidden = !(cm && cm.efforts.length); if (dds.length > 4) dds[3].btn.disabled = dds[4].btn.disabled = !!p.hosted;
  syncBanner(p);
  const isDemo = p.name === 'demo';
  const len = ui.text.value.length;
  ui.count.textContent = len ? `${len.toLocaleString()} / ${MAX.toLocaleString()}` : '';
  ui.count.classList.toggle('over', len > MAX);
  const ex = matchExample(ui.text.value, s, t);
  for (const c of ui.examples.children) c.classList.toggle('active', !!ex && c.dataset.id === ex.id);
  let reason = '';
  if (!ui.text.value.trim()) reason = '';
  else if (len > MAX) reason = 'The text is over the 4,000-character default limit.';
  else if (isDemo && !ex) reason = 'The demo accepts only the example sentences. Pick one, or switch to a keyed provider.';
  else if (p.needs_key && !S.key) reason = `Enter your ${p.label} API key to translate.`;
  ui.reason.textContent = reason;
  ui.go.disabled = S.busy || !ui.text.value.trim() || !!reason;
}

function fillSelect(sel, items, val, label) {
  sel.textContent = '';
  for (const it of items) { const o = el('option', null, label(it)); o.value = it.code || it.name; sel.append(o); }
  sel.value = val;
}

function fillModels(want, wantEffort) {
  const ms = models();
  ui.model.textContent = '';
  for (const m of ms) { const o = el('option', null, m.id); o.value = m.id; ui.model.append(o); }
  const pick = ms.find((m) => m.id === want) || ms.find((m) => m.default) || ms[0];
  ui.model.value = pick ? pick.id : '';
  fillEfforts(wantEffort);
}

function fillEfforts(want) {
  const cm = curModel(), es = cm ? cm.efforts : [];
  ui.effort.textContent = '';
  for (const e of es) { const o = el('option', null, e); o.value = e; ui.effort.append(o); }
  ui.effort.value = es.includes(want) ? want : (es[0] || '');
}

function showContact(c) {
  const ok = typeof c === 'string' && /^[^\s@<>"]+@[^\s@<>"]+$/.test(c);
  ui.contactLine.hidden = !ok;
  if (ok) { ui.contact.textContent = c; ui.contact.href = 'mailto:' + c; }
}

// Marks each step done, running or pending for the stage the server last announced; null hides the list.
function steps(stage) {
  const at = STAGES.indexOf(stage);
  ui.progress.hidden = at < 0;
  for (const li of ui.progress.children) {
    const i = STAGES.indexOf(li.dataset.stage);
    li.dataset.state = i < at ? 'done' : i === at ? 'running' : 'pending';
    if (i === at) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  }
}

// Reads the NDJSON body line by line: a line holding only "stage" goes to onStage, any other line is kept
// as the last object (the final body, or a refusal after the first stage). A bad line throws.
async function readStream(res, onStage) {
  const rd = res.body.getReader(), dec = new TextDecoder();
  let buf = '', last = null;
  const take = (line) => {
    if (!line.trim()) return;
    const o = JSON.parse(line), ks = Object.keys(o);
    if (ks.length === 1 && ks[0] === 'stage') onStage(o.stage); else last = o;
  };
  for (;;) {
    const { done, value } = await rd.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split('\n'); buf = parts.pop();
    parts.forEach(take);
  }
  buf += dec.decode();
  take(buf);
  return last;
}

function buildExamples() {
  ui.examples.textContent = '';
  for (const e of S.examples) {
    const b = el('button', 'chip'); b.type = 'button'; b.dataset.id = e.id;
    const pair = el('span', 'chip-pair', e.source.toUpperCase()); pair.append(arrowTo(), e.target.toUpperCase()); b.append(pair);
    const tx = el('span', 'chip-text', e.text); setDir(tx, e.source); b.append(tx);
    b.title = e.text;
    b.addEventListener('click', () => {
      if (S.result && (ui.source.value !== e.source || ui.target.value !== e.target)) ui.outPane.classList.add('stale');
      ui.source.value = e.source; ui.target.value = e.target; ui.text.value = e.text;
      S.prevSrc = e.source; S.prevTgt = e.target;
      sync(); ui.text.focus();
    });
    ui.examples.append(b);
  }
}

let openDD = null;
document.addEventListener('pointerdown', (e) => { if (openDD && !openDD.wrap.contains(e.target)) openDD.close(false); });
function makeDropdown(sel, meta) {
  const wrap = sel.parentElement; wrap.classList.add('dd');
  sel.hidden = true; sel.tabIndex = -1;
  const btn = el('button', 'dd-btn'); btn.type = 'button';
  btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
  const lbl = el('span', 'dd-label'); lbl.id = sel.id + '-cur';
  btn.append(lbl, el('span', 'dd-chev'));
  const pop = el('div', 'dd-pop'); pop.hidden = true;
  const search = el('input', 'dd-search'); search.type = 'search'; search.autocomplete = 'off'; search.spellcheck = false;
  search.placeholder = meta.searchLabel || 'Search'; search.setAttribute('aria-label', search.placeholder);
  const list = el('ul', 'dd-list'); list.id = sel.id + '-list'; list.setAttribute('role', 'listbox'); list.tabIndex = -1;
  const fl = wrap.parentElement.querySelector('.field-label');
  if (fl) { fl.id = fl.id || sel.id + '-fl'; btn.setAttribute('aria-labelledby', fl.id + ' ' + lbl.id); list.setAttribute('aria-labelledby', fl.id); }
  btn.setAttribute('aria-controls', list.id);
  pop.append(search, list); wrap.append(btn, pop);
  let items = [], active = -1, typed = '', typedT = 0;
  const api = { wrap, close, update, btn };
  function setActive(i, scroll) {
    active = i;
    const lis = list.querySelectorAll('.dd-opt');
    lis.forEach((li, j) => li.classList.toggle('active', j === i));
    const li = lis[i]; if (!li) return;
    list.setAttribute('aria-activedescendant', li.id); search.setAttribute('aria-activedescendant', li.id);
    if (scroll) { const t = li.offsetTop, b = t + li.offsetHeight; if (t < list.scrollTop) list.scrollTop = t - 4; else if (b > list.scrollTop + list.clientHeight) list.scrollTop = b - list.clientHeight + 4; }
  }
  function paint() {
    list.textContent = '';
    const q = search.value.trim().toLowerCase();
    items = Array.from(sel.options).filter((o) => !q || meta.match(o, q));
    items.forEach((o, i) => {
      const li = el('li', 'dd-opt'); li.id = sel.id + '-o-' + i; li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', String(o.value === sel.value));
      li.append(meta.item(o));
      li.addEventListener('pointermove', () => { if (active !== i) setActive(i, false); });
      li.addEventListener('click', (e) => { e.preventDefault(); choose(o.value); });
      list.append(li);
    });
    if (!items.length) list.append(el('li', 'dd-none', 'No matches'));
    setActive(Math.max(0, items.findIndex((o) => o.value === sel.value)), true);
  }
  function open() {
    if (openDD && openDD !== api) openDD.close(false);
    openDD = api; search.value = ''; search.hidden = sel.options.length <= 8;
    pop.hidden = false; pop.classList.remove('up', 'right');
    btn.setAttribute('aria-expanded', 'true'); wrap.classList.add('open');
    list.style.maxHeight = '';
    paint();
    const r = pop.getBoundingClientRect(), br = btn.getBoundingClientRect();
    const head = document.querySelector('.bar').getBoundingClientRect().bottom;
    const below = innerHeight - br.bottom - 14, above = br.top - head - 14;
    const up = r.height > below && above > below;
    if (up) pop.classList.add('up');
    const room = (up ? above : below) - (r.height - list.offsetHeight) - 6;
    if (room < list.offsetHeight) list.style.maxHeight = Math.max(140, room) + 'px';
    if (r.right > innerWidth - 8) pop.classList.add('right');
    (search.hidden ? list : search).focus({ preventScroll: true });
  }
  function close(refocus) {
    if (pop.hidden) return;
    pop.hidden = true; btn.setAttribute('aria-expanded', 'false'); wrap.classList.remove('open');
    if (openDD === api) openDD = null;
    if (refocus) btn.focus();
  }
  function choose(v) { const changed = sel.value !== v; sel.value = v; close(true); update(); if (changed) sel.dispatchEvent(new Event('change')); }
  function update() { const o = sel.options[sel.selectedIndex]; lbl.textContent = ''; if (o) lbl.append(meta.label ? meta.label(o) : o.textContent); }
  function keys(e) {
    const n = items.length;
    if (e.key === 'ArrowDown') { e.preventDefault(); if (n) setActive((active + 1) % n, true); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); if (n) setActive((active - 1 + n) % n, true); }
    else if (e.key === 'Enter') { e.preventDefault(); if (items[active]) choose(items[active].value); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); }
    else if (e.key === 'Tab') close(false);
    else if (e.target === list && e.key.length === 1 && /\S/.test(e.key)) {
      clearTimeout(typedT); typed += e.key.toLowerCase(); typedT = setTimeout(() => { typed = ''; }, 600);
      const i = items.findIndex((o) => o.textContent.toLowerCase().startsWith(typed)); if (i >= 0) setActive(i, true);
    }
  }
  btn.addEventListener('click', (e) => { e.preventDefault(); pop.hidden ? open() : close(true); });
  btn.addEventListener('keydown', (e) => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(); } });
  search.addEventListener('input', paint);
  search.addEventListener('keydown', keys); list.addEventListener('keydown', keys);
  pop.addEventListener('click', (e) => e.preventDefault());
  update();
  return api;
}
const tag = (text, cls) => el('span', 'dd-tag' + (cls ? ' ' + cls : ''), text);
const langMeta = {
  searchLabel: 'Search languages',
  match: (o, q) => { const l = lang(o.value); return l.name.toLowerCase().includes(q) || l.code.includes(q); },
  item: (o) => {
    const l = lang(o.value), f = document.createDocumentFragment(), tags = el('span', 'dd-tags');
    f.append(el('span', 'dd-name', l.name), el('span', 'dd-code', l.code));
    if (l.direction === 'rtl') tags.append(tag('RTL'));
    tags.append(tag(l.status, l.status === 'VERIFIED' ? 'ok' : ''));
    f.append(tags); return f;
  },
};
const provMeta = {
  match: (o, q) => o.textContent.toLowerCase().includes(q),
  item: (o) => {
    const p = S.providers.find((x) => x.name === o.value) || {}, f = document.createDocumentFragment(), tags = el('span', 'dd-tags');
    f.append(el('span', 'dd-name', o.textContent));
    if (p.hosted) tags.append(tag('Hosted', 'ok')); else if (p.needs_key) tags.append(tag('Your key')); else if (p.name === 'demo') tags.append(tag('Examples only'));
    f.append(tags); return f;
  },
};
const modelMeta = {
  match: (o, q) => o.value.toLowerCase().includes(q),
  item: (o) => {
    const m = models().find((x) => x.id === o.value) || {}, f = document.createDocumentFragment(), tags = el('span', 'dd-tags');
    f.append(el('span', 'dd-name', o.value));
    if (m.default) tags.append(tag('Default', 'ok'));
    f.append(tags); return f;
  },
};
const effortMeta = {
  match: (o, q) => o.value.toLowerCase().includes(q),
  item: (o) => {
    const f = document.createDocumentFragment(), tags = el('span', 'dd-tags');
    f.append(el('span', 'dd-name', o.value));
    if (o.index === 0) tags.append(tag('Default', 'ok'));
    f.append(tags); return f;
  },
};
let dds = [];

async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

async function init() {
  getJSON('/api/health').then((h) => showContact(h && h.contact)).catch(() => {});
  ui.load.className = 'card load-state'; ui.load.textContent = '';
  const lt = el('span', null, 'Loading languages and providers'); lt.append(ico('more')); ui.load.append(el('span', 'spinner'), lt);
  ui.load.hidden = false;
  try {
    const [langs, providers, examples] = await Promise.all([getJSON('/api/languages'), getJSON('/api/providers'), getJSON('/api/example')]);
    S.langs = langs; S.providers = providers; S.examples = examples;
    S.by = Object.fromEntries(langs.map((l) => [l.code, l]));
    const keyed = S.providers.filter((p) => p.needs_key).map((p) => p.label); ui.aboutKeyed.textContent = keyed.join(', '); ui.aboutKeyedRow.hidden = !keyed.length;
  } catch (e) {
    ui.load.className = 'card load-state failed'; ui.load.textContent = '';
    const btn = el('button', 'btn-ghost', 'Try again'); btn.type = 'button'; btn.addEventListener('click', init);
    ui.load.append(el('strong', null, "Couldn't reach the mordecai API."), el('span', 'fine', 'The languages, providers and examples could not be loaded. Check that the server is running.'), btn);
    return;
  }
  const hosted = S.providers.find((p) => p.hosted);
  ui.hosted.hidden = !hosted;
  fillSelect(ui.source, S.langs, S.by.he ? 'he' : S.langs[0].code, (l) => l.name);
  fillSelect(ui.target, S.langs, S.by.en ? 'en' : S.langs[1].code, (l) => l.name);
  S.prevSrc = ui.source.value; S.prevTgt = ui.target.value;
  ui.provider.textContent = '';
  for (const p of S.providers) { const o = el('option', null, p.label); o.value = p.name; ui.provider.append(o); }
  ui.provider.value = hosted ? hosted.name : 'demo';
  fillModels();
  buildExamples();
  if (!dds.length) { dds = [makeDropdown(ui.source, langMeta), makeDropdown(ui.target, langMeta), makeDropdown(ui.provider, provMeta), makeDropdown(ui.model, modelMeta), makeDropdown(ui.effort, effortMeta)]; dds[3].wrap.classList.add('dd-wide'); }
  ui.load.hidden = true; ui.app.hidden = false;
  sync();
}

function onLangChange(which) {
  const s = ui.source.value, t = ui.target.value;
  if (s === t) { if (which === 'source') ui.target.value = S.prevSrc; else ui.source.value = S.prevTgt; }
  S.prevSrc = ui.source.value; S.prevTgt = ui.target.value;
  if (S.result) ui.outPane.classList.add('stale');
  sync();
}

function swap() {
  const s = ui.source.value; ui.source.value = ui.target.value; ui.target.value = s;
  S.prevSrc = ui.source.value; S.prevTgt = ui.target.value;
  if (S.result && S.result.text) { ui.text.value = S.result.text; clearResult(); }
  else if (S.result) ui.outPane.classList.add('stale');
  sync();
}

function clearResult() {
  S.result = null;
  ui.output.textContent = ''; ui.notice.textContent = ''; ui.flags.hidden = true; ui.flags.textContent = '';
  ui.placeholder.hidden = false; ui.rSec.hidden = true; ui.niqqud.hidden = true; ui.copy.hidden = true;
  ui.error.hidden = true; ui.outPane.classList.remove('stale');
}

function clearKey() { S.key = ''; S.keyShown = ''; ui.key.value = ''; }

// The field shows maskKey(S.key); each edit of the shown string is applied to S.key. The edit ends at the
// caret: s = unchanged tail (no longer than the text after the caret), p = unchanged head, middle = typed text.
function onKeyInput(e) {
  if (e && e.isComposing) return;
  const now = ui.key.value, old = S.keyShown, real = S.key;
  if (now !== old) {
    const min = Math.min(now.length, old.length);
    const c = typeof ui.key.selectionEnd === 'number' ? ui.key.selectionEnd : now.length;
    let s = 0;
    while (s < min && s < now.length - c && now[now.length - 1 - s] === old[old.length - 1 - s]) s++;
    let p = 0;
    while (p < min - s && now[p] === old[p]) p++;
    const middle = now.slice(p, now.length - s);
    S.key = real.slice(0, p) + middle + real.slice(real.length - s);
    S.keyShown = maskKey(S.key);
    if (ui.key.value !== S.keyShown) ui.key.value = S.keyShown;
    ui.key.setSelectionRange(p + middle.length, p + middle.length);
  }
  sync();
}

function errorMessage(status, body, p) {
  const code = body && body.error;
  const hosted = p && p.hosted;
  switch (code) {
    case 'bad_request': return 'The server refused the request. The text may be empty or longer than its limit (4,000 characters by default).';
    case 'unknown_language': return "That language isn't available on this server.";
    case 'same_language': return 'Pick two different languages.';
    case 'unknown_provider': return "That provider isn't available on this server.";
    case 'unknown_model': return "This server doesn't offer that model for this provider.";
    case 'unknown_effort': return "That model doesn't take this effort level.";
    case 'bad_key': return "That key doesn't look right. A key is 16 to 512 printable ASCII characters with no spaces.";
    case 'key_required': return 'This provider needs your API key.';
    case 'demo_limit': return HOSTED_TEXT.demo_limit;
    case 'provider_not_configured': return "This server isn't set up for that provider.";
    case 'demo_examples_only': return 'The demo provider accepts only the example sentences, each with its own language pair. Pick an example, or use a provider with your own key.';
    case 'blocked_content': return `The content gate refused ${body.stage === 'output' ? 'the translation' : 'this text'} (${CAT[body.category] || body.category}).`;
    case 'gate_unavailable': return "The content check couldn't give a verdict, so the request was refused. If you're using your own key, check that it is valid and has quota.";
    case 'upstream_failed': return 'The provider failed while rendering the translation. Try again.';
    case 'quota_exhausted': return hosted ? HOSTED_TEXT.quota_exhausted : `Your ${p ? p.label : 'provider'} key was refused for quota or rate (the provider answered 429).`;
    default: return status === 0 ? "Couldn't reach the server, or it didn't answer in time." : 'Something went wrong on the server.';
  }
}

function fail(status, body, p) {
  ui.error.textContent = '';
  const code = body && body.error;
  const t = el('span', null, errorMessage(status, body, p)); t.id = 'error-text'; ui.error.append(t);
  const parts = [status ? `HTTP ${status}` : 'network', code || 'request failed'];
  if (body && body.stage && code !== 'blocked_content') parts.push(`stage: ${body.stage}`);
  const c = el('code'); c.id = 'error-code'; dotted(c, parts); ui.error.append(c);
  ui.error.hidden = false;
  if (S.result) ui.outPane.classList.add('stale');
  ui.placeholder.hidden = true;
}

function render(r) {
  S.result = r;
  ui.error.hidden = true; ui.outPane.classList.remove('stale'); ui.placeholder.hidden = true;
  ui.output.textContent = strip(r.text, r.target); setDir(ui.output, r.target);
  ui.outLang.textContent = lang(r.target).name;
  ui.notice.textContent = `${r.notice} (source: ${r.source_status}, target: ${r.target_status})`;
  ui.flags.textContent = '';
  if ((r.notes || []).includes('script_mismatch')) ui.flags.append(el('li', null, `Repair note: the output's script did not match ${lang(r.target).name} (script_mismatch).`));
  if (r.verify && !r.verify.ok && r.verify.notes.length) {
    const li = el('li', null, `Verify (a substring check): ${r.verify.notes.length === 1 ? 'one chosen sense was' : r.verify.notes.length + ' chosen senses were'} not found in the output: `);
    r.verify.notes.forEach((n, i) => { if (i) li.append(', '); li.append(bidi(n.token, r.source), arrowTo('flag-arrow'), bidi(n.expected, r.target)); });
    ui.flags.append(li);
  }
  ui.flags.hidden = !ui.flags.children.length;
  ui.copy.hidden = !r.text;
  const mk = lang(r.target).marks;
  ui.niqqud.hidden = !mk;
  ui.marksLabel.textContent = mk ? mk.label : ''; setDir(ui.marksLabel, r.target);
  renderReadings(r);
}

function renderReadings(r) {
  ui.readings.textContent = '';
  ui.rSec.hidden = false;
  ui.rEmpty.hidden = r.readings.length > 0;
  const greedy = Object.fromEntries((r.greedy || []).map((g) => [g.index, g]));
  let diffs = 0;
  for (const x of r.readings) {
    const g = greedy[x.index];
    const differs = g && (g.reading !== x.reading || g.gloss !== x.gloss);
    if (differs) diffs++;
    const li = el('li', 'reading' + (differs ? ' differs' : ''));
    const head = el('div', 'r-head');
    head.append(el('span', 'r-num', `#${x.index + 1}`), bidi(x.token, r.source, 'r-token'));
    if (x.prefix) { const pf = el('span', 'r-prefix', 'prefix '); pf.append(bidi(x.prefix, r.source)); head.append(pf); }
    li.append(head);
    const row = (label, rd, gl, cls) => {
      const d = el('div', 'r-row'); d.dataset.row = label.toLowerCase(); d.append(el('span', 'r-label', label));
      const v = el('span', cls); v.append(bidi(rd, r.source), arrowTo('r-arrow'));
      if (gl) v.append(bidi(gl, r.target, 'r-gloss'));
      else { const none = el('span', 'r-gloss r-none'); none.append(ico('dash'), el('span', 'sr-only', 'no gloss')); v.append(none); }
      d.append(v); return d;
    };
    li.append(row('Solver', x.reading, x.gloss, 'r-pick'));
    if (g) {
      const gr = row('Baseline', g.reading, g.gloss, '');
      gr.lastChild.append(el('span', 'r-tag' + (differs ? '' : ' same'), differs ? 'differs' : 'same'));
      li.append(gr);
    }
    if (x.candidates.length > 1) {
      const d = el('div', 'r-row'); d.dataset.row = 'options'; d.append(el('span', 'r-label', 'Options'));
      const cs = el('span', 'cands');
      x.candidates.forEach((c, j) => { const ch = el('span', 'cand' + (j === x.choice ? ' picked' : '')); ch.append(bidi(c.reading, r.source), ' ', bidi(c.gloss ? `(${c.gloss})` : '', r.target, 'r-gloss')); cs.append(ch); });
      d.append(cs); li.append(d);
    }
    ui.readings.append(li);
  }
  const s = r.solver || {};
  ui.solver.textContent = '';
  if (r.readings.length) {
    const n = r.readings.length;
    dotted(ui.solver, [
      `${n} word${n === 1 ? '' : 's'} with candidates`,
      `baseline differs on ${diffs}`,
      `toy solver score ${s.score} (slot matches minus unmet required slots, between neighbouring words that both have readings; not an accuracy measure)`,
      `${s.evaluated} option pairs scored between neighbouring words (a word without candidates counts as one option)`,
    ]);
  }
}

async function translate() {
  if (ui.go.disabled) return;
  const p = prov();
  const req = { text: ui.text.value, source: ui.source.value, target: ui.target.value, provider: p.name };
  const cm = curModel(); if (cm) { req.model = cm.id; if (cm.efforts.length) req.effort = ui.effort.value; }
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
  if (p.needs_key && S.key) headers['X-Provider-Key'] = S.key;
  S.busy = true; ui.go.classList.add('busy'); ui.go.querySelector('.btn-label').textContent = 'Translating'; sync();
  ui.outPane.classList.add('loading'); ui.error.hidden = true;
  if (S.result) ui.outPane.classList.add('stale');
  ui.placeholder.hidden = true; steps('input');
  const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 75000);
  let status = 0, body = null;
  try {
    const res = await fetch('/api/translate/stream', { method: 'POST', headers, body: JSON.stringify(req), signal: ctl.signal });
    status = res.status;
    if (status === 200) {
      body = await readStream(res, (s) => { if (STAGES.includes(s)) steps(s); });
      if (body && typeof body.error === 'string') status = typeof body.status === 'number' ? body.status : 0;
      else if (!body) status = 0;
    } else {
      try { body = await res.json(); } catch (e) { body = null; }
    }
  } catch (e) { status = 0; body = null; }
  clearTimeout(timer);
  S.busy = false; ui.go.classList.remove('busy'); ui.go.querySelector('.btn-label').textContent = 'Translate';
  ui.outPane.classList.remove('loading');
  steps(null);
  if (status === 200 && body && typeof body.text === 'string') {
    render(body);
    S.history.unshift({ at: new Date(), req, res: body, label: p.label });
    if (S.history.length > 30) S.history.pop();
    renderHistoryCount();
  } else fail(status, body, p);
  sync();
}

function renderHistoryCount() {
  ui.hCount.hidden = !S.history.length;
  ui.hCount.textContent = S.history.length > 9 ? '9+' : String(S.history.length);
}

function openHistory() {
  ui.hList.textContent = '';
  ui.hEmpty.hidden = S.history.length > 0;
  for (const h of S.history) {
    const li = el('li'); const b = el('button', 'h-item'); b.type = 'button';
    const meta = el('span', 'h-meta');
    const pair = el('b', null, h.req.source.toUpperCase()); pair.append(arrowTo(), h.req.target.toUpperCase());
    meta.append(pair, el('span', null, h.label), el('span', null, `${String(h.at.getHours()).padStart(2, '0')}:${String(h.at.getMinutes()).padStart(2, '0')}`));
    const src = el('span', 'h-src', h.req.text); setDir(src, h.req.source);
    const out = el('span', 'h-out', strip(h.res.text, h.req.target)); setDir(out, h.req.target);
    b.append(meta, src, out);
    b.addEventListener('click', () => {
      ui.source.value = h.req.source; ui.target.value = h.req.target; ui.text.value = h.req.text;
      if (S.providers.some((p) => p.name === h.req.provider) && ui.provider.value !== h.req.provider) { ui.provider.value = h.req.provider; clearKey(); }
      fillModels(h.req.model, h.req.effort);
      S.prevSrc = h.req.source; S.prevTgt = h.req.target;
      render(h.res); sync(); ui.history.close();
    });
    li.append(b); ui.hList.append(li);
  }
  ui.history.showModal();
}

function home() {
  const open = [ui.about, ui.history].filter((d) => d.open);
  if (open.length) { open.forEach((d) => d.close()); return; }
  if (ui.app.hidden) return;
  ui.text.value = ''; clearResult(); sync(); ui.text.focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

ui.source.addEventListener('change', () => onLangChange('source'));
ui.target.addEventListener('change', () => onLangChange('target'));
ui.swap.addEventListener('click', swap);
ui.provider.addEventListener('change', () => { clearKey(); sync(); });
ui.provider.addEventListener('change', () => { fillModels(); sync(); });
ui.model.addEventListener('change', () => { fillEfforts(); sync(); });
ui.effort.addEventListener('change', sync);
ui.key.addEventListener('input', onKeyInput);
ui.key.addEventListener('compositionend', onKeyInput);
ui.text.addEventListener('input', sync);
ui.text.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); translate(); } });
ui.go.addEventListener('click', translate);
ui.niqqud.addEventListener('click', () => {
  S.niqqud = !S.niqqud; ui.niqqud.setAttribute('aria-pressed', String(S.niqqud));
  if (S.result) { const stale = ui.outPane.classList.contains('stale'); const errHidden = ui.error.hidden; render(S.result); if (stale) ui.outPane.classList.add('stale'); ui.error.hidden = errHidden; }
});
ui.copy.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(ui.output.textContent); ui.copy.textContent = 'Copied'; } catch (e) { ui.copy.textContent = 'Copy failed'; }
  setTimeout(() => { ui.copy.textContent = 'Copy'; }, 1400);
});
ui.home.addEventListener('click', home);
$('about-open').addEventListener('click', () => ui.about.showModal());
$('history-open').addEventListener('click', openHistory);
$('history-clear').addEventListener('click', () => { S.history = []; renderHistoryCount(); openHistory(); ui.history.showModal(); });
for (const d of [ui.about, ui.history]) {
  d.addEventListener('click', (e) => { if (e.target === d || e.target.closest('[data-close]')) d.close(); });
}
// The info line opens on hover or focus (CSS), on a click, and closes on a click elsewhere or Escape.
ui.info.addEventListener('click', () => { ui.infoWrap.classList.remove('hush'); ui.infoWrap.classList.toggle('open'); });
document.addEventListener('pointerdown', (e) => { if (!ui.infoWrap.contains(e.target)) ui.infoWrap.classList.remove('open'); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && (ui.infoWrap.matches(':hover') || ui.infoWrap.classList.contains('open') || document.activeElement === ui.info)) {
    ui.infoWrap.classList.remove('open'); ui.infoWrap.classList.add('hush');
  }
});
ui.infoWrap.addEventListener('mouseleave', () => ui.infoWrap.classList.remove('hush'));
ui.info.addEventListener('blur', () => ui.infoWrap.classList.remove('hush'));

const root = document.documentElement, KEY = 'mordecai-theme', mq = window.matchMedia('(prefers-color-scheme: dark)');
const effTheme = () => root.dataset.theme || (mq.matches ? 'dark' : 'light');
const syncThemeBtn = () => { const d = effTheme() === 'dark'; $('theme').setAttribute('aria-label', d ? 'Switch to light mode' : 'Switch to dark mode'); $('theme').title = d ? 'Light mode' : 'Dark mode'; };
try { const t = localStorage.getItem(KEY); if (t === 'dark' || t === 'light') root.dataset.theme = t; } catch (e) {}
$('theme').addEventListener('click', () => { const n = effTheme() === 'dark' ? 'light' : 'dark'; root.dataset.theme = n; try { localStorage.setItem(KEY, n); } catch (e) {} syncThemeBtn(); });
mq.addEventListener('change', syncThemeBtn);
syncThemeBtn();

init();
})();
