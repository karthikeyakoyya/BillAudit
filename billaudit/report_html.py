"""Single-file HTML dashboard. Inline SVG charts, a small inline script for
navigation and filtering, no external requests.

Page behaviour: skip link, sticky section navigation with a menu button on
narrow screens, theme switch (system, light, dark) remembered in the browser,
reading-progress bar, back-to-top button, claim filter, copy-claim-id buttons,
native expandable notes, and a print stylesheet.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from .config import RULE_LABELS, RULE_PRIORITY

LIGHT = "--bg:#f7f7f5;--card:#ffffff;--ink:#1f2937;--mute:#6b7280;--line:#e5e7eb;--hover:#f3f4f6;--a:#0f766e;--b:#94a3b8;--c:#cbd5e1;--warn:#b45309;--bad:#b91c1c;--good:#15803d"
DARK = "--bg:#0f1418;--card:#171d23;--ink:#e5e7eb;--mute:#9ca3af;--line:#2a323a;--hover:#1e262d;--a:#2dd4bf;--b:#64748b;--c:#475569;--warn:#f59e0b;--bad:#f87171;--good:#4ade80"

CSS = f"""
:root{{{LIGHT}}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{{DARK}}}}}
:root[data-theme="dark"]{{{DARK}}}
:root[data-theme="light"]{{{LIGHT}}}
*{{box-sizing:border-box}}
html{{scroll-padding-top:68px}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 "Segoe UI",Arial,sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:24px 20px 56px}}
h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:15px;margin:0 0 12px}}
section{{margin-bottom:26px}}
.sub{{color:var(--mute);margin:0 0 18px}}
a{{color:inherit}}
:focus-visible{{outline:2px solid var(--a);outline-offset:2px}}
.skip{{position:absolute;left:12px;top:-48px;background:var(--card);border:1px solid var(--line);padding:8px 12px;border-radius:6px;z-index:30}}
.skip:focus{{top:8px}}
#progress{{position:fixed;left:0;top:0;height:3px;width:0;background:var(--a);z-index:40}}
header.top{{position:sticky;top:0;z-index:20;background:var(--card);border-bottom:1px solid var(--line)}}
.bar{{max-width:1120px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:14px}}
.brand{{font-weight:600;text-decoration:none;margin-right:auto}}
nav{{display:flex;gap:2px}}
nav a{{text-decoration:none;color:var(--mute);padding:5px 10px;border-radius:6px}}
nav a:hover{{background:var(--hover);color:var(--ink)}}
button{{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:5px 10px;cursor:pointer}}
button:hover{{background:var(--hover)}}
#menuBtn{{display:none}}
.grid{{display:grid;gap:14px}}.kpis{{grid-template-columns:repeat(6,1fr)}}
.two{{grid-template-columns:repeat(auto-fit,minmax(420px,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;animation:rise .3s ease both;transition:border-color .15s}}
.card:hover{{border-color:var(--b)}}
@keyframes rise{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
.kpi .v{{font-size:20px;font-weight:600;margin-top:2px}}.kpi .l{{color:var(--mute);font-size:12px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:6px 8px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}
th{{color:var(--mute);font-weight:600;font-size:12px}}td.n,th.n{{text-align:right}}
tbody tr:hover{{background:var(--hover)}}
tr[hidden]{{display:none}}
.wrap{{overflow-x:auto}}
.tall{{max-height:460px;overflow:auto}}
.pill{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;border:1px solid var(--line)}}
.credited,.accepted,.partial{{color:var(--good)}}.rejected{{color:var(--bad)}}.filed{{color:var(--warn)}}
svg text{{fill:var(--ink);font-family:"Segoe UI",Arial,sans-serif}}svg .m{{fill:var(--mute)}}
svg rect:hover{{opacity:.85}}
.key{{display:flex;gap:14px;font-size:12px;color:var(--mute);margin-bottom:6px;flex-wrap:wrap}}
.key i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.note{{color:var(--mute);font-size:12px;margin-top:10px}}
.filters{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}}
input[type=search],select{{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 10px}}
input[type=search]{{min-width:240px}}
.count{{color:var(--mute);font-size:12px}}
.copy{{padding:0 6px;font-size:11px;margin-left:6px;color:var(--mute)}}
details{{border-bottom:1px solid var(--line);padding:8px 0}}
details:last-child{{border-bottom:0}}
summary{{cursor:pointer;font-weight:600}}summary:hover{{color:var(--a)}}
details p{{margin:8px 0 2px;color:var(--mute)}}
#toTop{{position:fixed;right:18px;bottom:18px;z-index:20;box-shadow:0 1px 4px rgba(0,0,0,.2)}}
#toTop[hidden]{{display:none}}
.sr{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}
footer{{color:var(--mute);font-size:12px;margin-top:8px}}
@media (max-width:900px){{.kpis{{grid-template-columns:repeat(3,1fr)}}}}
@media (max-width:760px){{
  .two{{grid-template-columns:1fr}}
  #menuBtn{{display:inline-block}}
  nav{{display:none;position:absolute;left:0;right:0;top:100%;background:var(--card);border-bottom:1px solid var(--line);flex-direction:column;padding:6px 20px 10px}}
  .nav-open nav{{display:flex}}
  .bar{{position:relative}}
}}
@media (max-width:520px){{.kpis{{grid-template-columns:repeat(2,1fr)}}input[type=search]{{min-width:0;width:100%}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important;scroll-behavior:auto!important}}}}
@media print{{
  :root,:root[data-theme="dark"],:root[data-theme="light"]{{{LIGHT}}}
  @page{{margin:14mm}}
  header.top,#progress,#toTop,.filters,.copy,.skip,#menuBtn{{display:none!important}}
  body{{background:#fff}}
  main{{padding:0}}
  .card{{break-inside:avoid;animation:none}}
  .tall,.wrap{{max-height:none;overflow:visible}}
  section{{break-inside:auto}}
  a{{text-decoration:none}}
}}
"""

HEAD_SCRIPT = """(function(){try{var t=localStorage.getItem('billaudit-theme');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t)}}catch(e){}})();"""

SCRIPT = """
(function () {
  var root = document.documentElement, KEY = 'billaudit-theme';
  var themeBtn = document.getElementById('themeBtn');
  function stored() { try { return localStorage.getItem(KEY) || 'system'; } catch (e) { return 'system'; } }
  function apply(t) {
    if (t === 'system') { root.removeAttribute('data-theme'); } else { root.setAttribute('data-theme', t); }
    themeBtn.textContent = 'Theme: ' + t;
  }
  var theme = stored();
  apply(theme);
  themeBtn.addEventListener('click', function () {
    theme = theme === 'system' ? 'light' : (theme === 'light' ? 'dark' : 'system');
    apply(theme);
    try { localStorage.setItem(KEY, theme); } catch (e) {}
  });

  var menuBtn = document.getElementById('menuBtn'), nav = document.getElementById('nav');
  menuBtn.addEventListener('click', function () {
    var open = document.body.classList.toggle('nav-open');
    menuBtn.setAttribute('aria-expanded', String(open));
  });
  nav.addEventListener('click', function (e) {
    if (e.target.tagName === 'A') {
      document.body.classList.remove('nav-open');
      menuBtn.setAttribute('aria-expanded', 'false');
    }
  });

  var bar = document.getElementById('progress'), toTop = document.getElementById('toTop');
  function onScroll() {
    var h = document.documentElement, max = h.scrollHeight - h.clientHeight;
    bar.style.width = (max > 0 ? Math.min(100, h.scrollTop / max * 100) : 0) + '%';
    toTop.hidden = h.scrollTop < 600;
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
  toTop.addEventListener('click', function () {
    var calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: calm ? 'auto' : 'smooth' });
  });

  var q = document.getElementById('q'), st = document.getElementById('st');
  var rows = [].slice.call(document.querySelectorAll('#claimRows tr'));
  var count = document.getElementById('count'), empty = document.getElementById('empty');
  function filter() {
    var s = q.value.trim().toLowerCase(), t = st.value, n = 0;
    rows.forEach(function (r) {
      var ok = (!s || r.getAttribute('data-search').indexOf(s) > -1) && (!t || r.getAttribute('data-status') === t);
      r.hidden = !ok;
      if (ok) { n += 1; }
    });
    count.textContent = 'Showing ' + n + ' of ' + rows.length + ' filed claims';
    empty.hidden = n > 0;
  }
  q.addEventListener('input', filter);
  st.addEventListener('change', filter);
  filter();

  var live = document.getElementById('live');
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta);
      if (ok) { resolve(); } else { reject(new Error('copy failed')); }
    });
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('.copy') : null;
    if (!b) { return; }
    var text = b.getAttribute('data-copy');
    copyText(text).then(function () {
      var old = b.textContent;
      b.textContent = 'Copied';
      live.textContent = text + ' copied';
      setTimeout(function () { b.textContent = old; }, 1400);
    }, function () { live.textContent = 'Copy failed'; });
  });

  var opened = [];
  window.addEventListener('beforeprint', function () {
    opened = [].slice.call(document.querySelectorAll('details')).filter(function (d) { return !d.open; });
    opened.forEach(function (d) { d.open = true; });
  });
  window.addEventListener('afterprint', function () {
    opened.forEach(function (d) { d.open = false; });
    opened = [];
  });
})();
"""

FAQ = [
    ("What does flagged value mean?",
     "The estimated overcharge on every invoice line that tripped an audit rule. A line is counted once, under the highest-priority rule that caught it."),
    ("What is time-barred?",
     "Invoice periods older than the vendor's dispute window as of the audit date (6, 9, 12 and 12 months for the four vendors). They are shown separately and left out of what can be filed."),
    ("How is expected recovery calculated?",
     "Claimable value multiplied by the rule's recovery rate in last year's dispute history. The history is simulated, and rules with few past claims are pulled toward 50%."),
    ("Why is the spike rule's precision below 100%?",
     "It compares a charge with the circuit's own history, so it also flags legitimate usage overages on voice lines. The other six rules matched the answer key exactly."),
    ("What is real and what is simulated?",
     "Everything. Vendors, rates, circuits, contracts, the LERG-style and NECA-style tables, the injected errors and the vendor responses after filing are all generated from a seed."),
]


def money(x: float, short: bool = False) -> str:
    if short and abs(x) >= 1000:
        return f"${x / 1000:,.1f}k"
    return f"${x:,.0f}"


def _hbars(rows: list[tuple[str, list[float]]], names: list[str], colors: list[str],
           width: int = 520, label_w: int = 150) -> str:
    """Overlaid horizontal bars: values are drawn largest first so smaller ones sit on top."""
    mx = max((max(v) for _, v in rows), default=1) or 1
    h = 30 * len(rows) + 6
    inner = width - label_w - 70
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img">']
    for i, (label, vals) in enumerate(rows):
        y = 4 + i * 30
        out.append(f'<text x="0" y="{y + 15}" font-size="12">{escape(label)}</text>')
        for v, col, name in sorted(zip(vals, colors, names), key=lambda t: -t[0]):
            w = max(0.0, v / mx * inner)
            out.append(f'<rect x="{label_w}" y="{y + 3}" width="{w:.1f}" height="16" rx="2" style="fill:var({col})">'
                       f'<title>{escape(label)}: {name} ${v:,.0f}</title></rect>')
        out.append(f'<text class="m" x="{label_w + vals[0] / mx * inner + 6:.1f}" y="{y + 16}" font-size="11">{money(vals[0], True)}</text>')
    out.append("</svg>")
    return "".join(out)


def _columns(items: list[tuple[str, int]], width: int = 520, height: int = 190) -> str:
    mx = max((v for _, v in items), default=1) or 1
    bw = 70
    gap = (width - bw * len(items)) / (len(items) + 1)
    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img">']
    base = height - 28
    for i, (label, v) in enumerate(items):
        x = gap + i * (bw + gap)
        hh = v / mx * (base - 24)
        out.append(f'<rect x="{x:.1f}" y="{base - hh:.1f}" width="{bw}" height="{hh:.1f}" rx="2" style="fill:var(--a)"><title>{escape(label)}: {v} claims</title></rect>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{base - hh - 6:.1f}" font-size="12" text-anchor="middle">{v}</text>')
        out.append(f'<text class="m" x="{x + bw / 2:.1f}" y="{height - 8}" font-size="12" text-anchor="middle">{escape(label)}</text>')
    out.append("</svg>")
    return "".join(out)


def _funnel(items: list[tuple[str, int]]) -> str:
    mx = max(v for _, v in items) or 1
    out = [f'<svg viewBox="0 0 520 {30 * len(items) + 6}" width="100%" role="img">']
    for i, (k, v) in enumerate(items):
        y = 4 + i * 30
        out.append(f'<text x="0" y="{y + 15}" font-size="12">{k}</text>')
        out.append(f'<rect x="150" y="{y + 3}" width="{v / mx * 300:.1f}" height="16" rx="2" style="fill:var(--a)"><title>{k}: {v}</title></rect>')
        out.append(f'<text class="m" x="{150 + v / mx * 300 + 6:.1f}" y="{y + 16}" font-size="11">{v}</text>')
    out.append("</svg>")
    return "".join(out)


def build_dashboard(path: Path, d: dict) -> None:
    c = d["claims"]
    m = d["meta"]
    filed = c[c.decision == "file"].sort_values(["expected_value", "claim_id"], ascending=[False, True])

    by_rule = []
    for r in RULE_PRIORITY:
        s = c[c.rule == r]
        by_rule.append((RULE_LABELS[r], [float(s.total_overcharge.sum()), float(s.claimable_amount.sum()), float(s.credit_amount.sum())]))
    by_vendor = []
    for v in d["vendors"].itertuples():
        s = filed[filed.vendor_id == v.vendor_id]
        by_vendor.append((v.vendor_name, [float(s.claimable_amount.sum()), float(s.credit_pending.sum() + s.credit_amount.sum()), float(s.credit_amount.sum())]))

    kpis = [
        ("Flagged value", money(c.total_overcharge.sum())),
        ("Inside dispute windows", money(c.claimable_amount.sum())),
        ("Time-barred", money(c.barred_amount.sum())),
        (f"Filed ({len(filed)} claims)", money(filed.claimable_amount.sum())),
        ("Expected recovery", money(filed.expected_value.sum())),
        ("Credits received", money(c.credit_amount.sum())),
    ]
    kpi_html = "".join(f'<div class="card kpi"><div class="l">{escape(k)}</div><div class="v">{v}</div></div>' for k, v in kpis)

    aging = filed[filed.status == "filed"]["aging_bucket"].value_counts()
    aging_items = [(b, int(aging.get(b, 0))) for b in ("0-30 days", "31-60 days", "61+ days")]
    funnel = [
        ("Claims raised", len(c)),
        ("Eligible to file", int((~c.decision.isin(["time_barred", "below_threshold"])).sum())),
        ("Filed", len(filed)),
        ("Vendor answered", int(filed.response_outcome.notna().sum())),
        ("Credit applied", int((filed.status == "credited").sum())),
    ]

    statuses = [s for s in ("credited", "accepted", "partial", "rejected", "filed") if (filed.status == s).any()]
    status_opts = "".join(f'<option value="{s}">{s.capitalize()}</option>' for s in statuses)
    claim_rows = "".join(
        f'<tr data-status="{r.status}" data-search="{escape((r.claim_id + " " + r.vendor_name + " " + r.circuit_id + " " + RULE_LABELS[r.rule]).lower())}">'
        f'<td>{r.claim_id}<button type="button" class="copy" data-copy="{r.claim_id}" aria-label="Copy claim id {r.claim_id}">Copy</button></td>'
        f"<td>{escape(r.vendor_name)}</td><td>{r.circuit_id}</td><td>{escape(RULE_LABELS[r.rule])}</td>"
        f'<td class="n">{money(r.claimable_amount)}</td><td class="n">{money(r.expected_value)}</td>'
        f'<td><span class="pill {r.status}">{r.status}</span></td></tr>'
        for r in filed.itertuples()
    )

    perf = d["rule_perf"]
    prow = "".join(
        f"<tr><td>{escape(RULE_LABELS[r.rule])}</td><td class='n'>{r.injected}</td><td class='n'>{r.flagged}</td>"
        f"<td class='n'>{'-' if r.precision is None else f'{r.precision:.0%}'}</td><td class='n'>{'-' if r.recall is None else f'{r.recall:.0%}'}</td></tr>"
        for r in perf.itertuples()
    )
    cal = d["calibration"]
    crow = "".join(
        f"<tr><td>{escape(RULE_LABELS[r.rule])}</td><td class='n'>{r.resolved}</td><td class='n'>{r.predicted_rate:.0%}</td><td class='n'>{r.actual_rate:.0%}</td></tr>"
        for r in cal.itertuples()
    )
    rej = d["dq"][d["dq"].status == "rejected"]
    drow = "".join(f"<tr><td>{escape(r.file)}</td><td>{escape(r.issues.split(' | ')[0])}</td></tr>" for r in rej.itertuples())
    faq = "".join(f"<details><summary>{escape(q)}</summary><p>{escape(a)}</p></details>" for q, a in FAQ)
    now = datetime.now().astimezone()

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Telecom invoice audit</title>
<script>{HEAD_SCRIPT}</script><style>{CSS}</style></head><body>
<a class="skip" href="#main">Skip to content</a>
<div id="progress" aria-hidden="true"></div>
<header class="top"><div class="bar">
<a class="brand" href="#summary">Telecom invoice audit</a>
<button id="menuBtn" type="button" aria-expanded="false" aria-controls="nav">Menu</button>
<nav id="nav" aria-label="Sections"><a href="#summary">Summary</a><a href="#charts">Charts</a><a href="#claims">Claims</a><a href="#rules">Rules</a><a href="#quality">Quality gate</a><a href="#notes">Notes</a></nav>
<button id="themeBtn" type="button" aria-label="Change colour theme">Theme: system</button>
</div></header>
<main id="main">
<section id="summary">
<h1>Telecom invoice audit</h1>
<p class="sub">{m['year']} invoices, audit run {m['as_of']}, tracker cut {m['report_date']}. {m['lines_loaded']:,} invoice lines audited. Simulated data.</p>
<div class="grid kpis">{kpi_html}</div>
</section>
<section id="charts">
<div class="grid two" style="margin-bottom:14px">
<div class="card"><h2>Value by rule</h2><div class="key"><span><i style="background:var(--c)"></i>Flagged</span><span><i style="background:var(--b)"></i>Inside window</span><span><i style="background:var(--a)"></i>Credited</span></div>{_hbars(by_rule, ["Flagged", "Inside window", "Credited"], ["--c", "--b", "--a"])}</div>
<div class="card"><h2>Filed claims by vendor</h2><div class="key"><span><i style="background:var(--c)"></i>Filed</span><span><i style="background:var(--b)"></i>Accepted</span><span><i style="background:var(--a)"></i>Credited</span></div>{_hbars(by_vendor, ["Filed", "Accepted", "Credited"], ["--c", "--b", "--a"])}</div>
</div>
<div class="grid two">
<div class="card"><h2>Claim pipeline</h2>{_funnel(funnel)}</div>
<div class="card"><h2>Filed, no answer yet: age in days</h2>{_columns(aging_items)}<p class="note">Counted from the filing date to the tracker cut.</p></div>
</div>
</section>
<section id="claims">
<div class="card"><h2>Filed claims, highest expected recovery first</h2>
<div class="filters">
<input id="q" type="search" placeholder="Filter by claim, vendor, circuit or rule" aria-label="Filter filed claims">
<select id="st" aria-label="Filter by status"><option value="">All statuses</option>{status_opts}</select>
<span id="count" class="count" aria-live="polite"></span>
</div>
<div class="wrap tall"><table><thead><tr><th>Claim</th><th>Vendor</th><th>Circuit</th><th>Rule</th><th class="n">Claimable</th><th class="n">Expected</th><th>Status</th></tr></thead><tbody id="claimRows">{claim_rows}</tbody></table></div>
<p id="empty" class="note" hidden>No filed claims match.</p>
</div>
</section>
<section id="rules">
<div class="grid two">
<div class="card"><h2>Rules against the answer key</h2><div class="wrap"><table><thead><tr><th>Rule</th><th class="n">Injected</th><th class="n">Flagged</th><th class="n">Precision</th><th class="n">Recall</th></tr></thead><tbody>{prow}</tbody></table></div><p class="note">The spike rule also flags legitimate usage overages on voice lines, which is why its precision is below 100%.</p></div>
<div class="card"><h2>Predicted vs actual recovery</h2><div class="wrap"><table><thead><tr><th>Rule</th><th class="n">Answered</th><th class="n">Predicted</th><th class="n">Actual</th></tr></thead><tbody>{crow}</tbody></table></div><p class="note">Predicted comes from last year's disputes. Actual is this cycle's answered claims; small counts move a lot.</p></div>
</div>
</section>
<section id="quality">
<div class="card"><h2>Invoice files held back by the quality gate</h2><div class="wrap"><table><thead><tr><th>File</th><th>Reason</th></tr></thead><tbody>{drow or '<tr><td colspan="2">None</td></tr>'}</tbody></table></div></div>
</section>
<section id="notes">
<div class="card"><h2>Notes</h2>{faq}</div>
</section>
<footer>Last updated <time datetime="{now.isoformat(timespec='minutes')}">{now.strftime('%d %b %Y, %H:%M')}</time>. Data as of {m['as_of']}.</footer>
</main>
<button id="toTop" type="button" hidden aria-label="Back to top">Top</button>
<div id="live" class="sr" role="status" aria-live="polite"></div>
<script>{SCRIPT}</script>
</body></html>"""
    Path(path).write_text(html, encoding="utf-8")
