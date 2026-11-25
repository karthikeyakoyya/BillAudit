// Behaviour checks for the dashboard page, run in jsdom.
// Usage: node dashboard_behaviour.js path/to/dashboard.html
const assert = require('assert');
const fs = require('fs');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(process.argv[2], 'utf8');
let passed = 0;
function check(name, fn) {
  try { fn(); passed += 1; console.log('ok   ' + name); }
  catch (e) { console.log('FAIL ' + name + '\n     ' + e.message); process.exitCode = 1; }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function load(setup) {
  return new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/',
    beforeParse(window) { if (setup) { setup(window); } },
  });
}
function fire(win, el, type) { el.dispatchEvent(new win.Event(type, { bubbles: true })); }
function visibleRows(d) { return [].slice.call(d.querySelectorAll('#claimRows tr')).filter((r) => !r.hidden); }

(async () => {
  const dom = load();
  const w = dom.window, d = w.document;
  const total = d.querySelectorAll('#claimRows tr').length;

  check('skip link targets the main region', () => {
    const a = d.querySelector('a.skip');
    assert.strictEqual(a.getAttribute('href'), '#main');
    assert.ok(d.getElementById('main'));
  });
  check('every nav link points at a section that exists', () => {
    const links = [].slice.call(d.querySelectorAll('#nav a'));
    assert.ok(links.length >= 5);
    links.forEach((a) => assert.ok(d.querySelector(a.getAttribute('href')), a.getAttribute('href')));
  });
  check('claims table lists all filed claims and reports the count', () => {
    assert.ok(total > 0);
    assert.strictEqual(d.getElementById('count').textContent, `Showing ${total} of ${total} filed claims`);
  });
  check('search filters by vendor text', () => {
    const q = d.getElementById('q');
    q.value = 'harborline'; fire(w, q, 'input');
    const rows = visibleRows(d);
    assert.ok(rows.length > 0 && rows.length < total);
    rows.forEach((r) => assert.ok(r.textContent.toLowerCase().includes('harborline')));
    assert.strictEqual(d.getElementById('count').textContent, `Showing ${rows.length} of ${total} filed claims`);
  });
  check('status filter combines with search', () => {
    const st = d.getElementById('st');
    st.value = 'credited'; fire(w, st, 'change');
    visibleRows(d).forEach((r) => {
      assert.strictEqual(r.getAttribute('data-status'), 'credited');
      assert.ok(r.textContent.toLowerCase().includes('harborline'));
    });
  });
  check('a search with no match shows the empty message', () => {
    const q = d.getElementById('q');
    q.value = 'zzzz-no-such-claim'; fire(w, q, 'input');
    assert.strictEqual(visibleRows(d).length, 0);
    assert.strictEqual(d.getElementById('empty').hidden, false);
  });
  check('clearing the filters restores every row', () => {
    const q = d.getElementById('q'), st = d.getElementById('st');
    q.value = ''; fire(w, q, 'input'); st.value = ''; fire(w, st, 'change');
    assert.strictEqual(visibleRows(d).length, total);
    assert.strictEqual(d.getElementById('empty').hidden, true);
  });
  check('searching the word "copy" does not match every row', () => {
    const q = d.getElementById('q');
    q.value = 'copy'; fire(w, q, 'input');
    assert.strictEqual(visibleRows(d).length, 0);
    q.value = ''; fire(w, q, 'input');
  });

  check('theme button cycles light, dark, system and remembers the choice', () => {
    const btn = d.getElementById('themeBtn'), root = d.documentElement;
    assert.strictEqual(btn.textContent, 'Theme: system');
    btn.click(); assert.strictEqual(root.getAttribute('data-theme'), 'light'); assert.strictEqual(w.localStorage.getItem('billaudit-theme'), 'light');
    btn.click(); assert.strictEqual(root.getAttribute('data-theme'), 'dark'); assert.strictEqual(btn.textContent, 'Theme: dark');
    btn.click(); assert.strictEqual(root.hasAttribute('data-theme'), false); assert.strictEqual(w.localStorage.getItem('billaudit-theme'), 'system');
  });
  check('a saved theme is applied on load', () => {
    const d2 = load((win) => win.localStorage.setItem('billaudit-theme', 'dark')).window.document;
    assert.strictEqual(d2.documentElement.getAttribute('data-theme'), 'dark');
    assert.strictEqual(d2.getElementById('themeBtn').textContent, 'Theme: dark');
  });
  check('page still works when browser storage is blocked', () => {
    const d3 = load((win) => {
      Object.defineProperty(win, 'localStorage', { get() { throw new Error('blocked'); } });
    }).window.document;
    d3.getElementById('themeBtn').click();
    assert.strictEqual(d3.documentElement.getAttribute('data-theme'), 'light');
  });

  check('menu button opens and closes the nav and updates aria-expanded', () => {
    const btn = d.getElementById('menuBtn');
    btn.click();
    assert.ok(d.body.classList.contains('nav-open')); assert.strictEqual(btn.getAttribute('aria-expanded'), 'true');
    d.querySelector('#nav a').click();
    assert.ok(!d.body.classList.contains('nav-open')); assert.strictEqual(btn.getAttribute('aria-expanded'), 'false');
  });

  check('progress bar and back-to-top follow the scroll position', () => {
    const h = d.documentElement;
    Object.defineProperty(h, 'scrollHeight', { value: 3000, configurable: true });
    Object.defineProperty(h, 'clientHeight', { value: 1000, configurable: true });
    const top = d.getElementById('toTop'), bar = d.getElementById('progress');
    assert.strictEqual(top.hidden, true);
    Object.defineProperty(h, 'scrollTop', { value: 1000, configurable: true, writable: true });
    fire(w, w, 'scroll');
    assert.strictEqual(top.hidden, false);
    assert.strictEqual(bar.style.width, '50%');
    let target = null; w.scrollTo = (o) => { target = o; };
    top.click();
    assert.strictEqual(target.top, 0);
    h.scrollTop = 0; fire(w, w, 'scroll');
    assert.strictEqual(top.hidden, true);
  });

  const btn = d.querySelector('.copy'), id = btn.getAttribute('data-copy');
  let copied = null;
  Object.defineProperty(w.navigator, 'clipboard', { value: { writeText: (t) => { copied = t; return Promise.resolve(); } }, configurable: true });
  btn.click(); await sleep(20);
  check('copy writes the claim id and shows Copied', () => {
    assert.strictEqual(copied, id);
    assert.strictEqual(btn.textContent, 'Copied');
    assert.ok(d.getElementById('live').textContent.includes(id));
  });
  await sleep(1500);
  check('copy label returns to normal', () => assert.strictEqual(btn.textContent, 'Copy'));

  const dom2 = load(); const w2 = dom2.window, d2 = w2.document;
  let execd = false; d2.execCommand = () => { execd = true; return true; };
  const b2 = d2.querySelector('.copy'); b2.click(); await sleep(20);
  check('copy falls back to execCommand without the clipboard API', () => {
    assert.ok(execd); assert.strictEqual(b2.textContent, 'Copied');
  });
  const dom3 = load(); const w3 = dom3.window, d3 = w3.document;
  d3.execCommand = () => false; const b3 = d3.querySelector('.copy'); b3.click(); await sleep(20);
  check('a failed copy is reported, not hidden', () => assert.strictEqual(d3.getElementById('live').textContent, 'Copy failed'));

  check('print opens the notes and restores them afterwards', () => {
    const det = [].slice.call(d.querySelectorAll('details'));
    assert.ok(det.length >= 4 && det.every((x) => !x.open));
    fire(w, w, 'beforeprint'); assert.ok(det.every((x) => x.open));
    fire(w, w, 'afterprint'); assert.ok(det.every((x) => !x.open));
  });
  check('page makes no network requests and has a last-updated date', () => {
    assert.ok(!/(src|href)="https?:/.test(html));
    assert.ok(!/fetch\(|XMLHttpRequest|sendBeacon/.test(html));
    assert.ok(d.querySelector('footer time'));
  });

  console.log(`\n${passed} checks passed${process.exitCode ? ', some failed' : ''}`);
})();
