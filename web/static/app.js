'use strict';
/* The Black House v5 */
/* ============ helpers ============ */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => (s ?? '').toString().replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const api = async (p, o) => { if (window.staticApi) return window.staticApi(p, o); const r = await fetch(p, o); if (!r.ok) throw new Error(r.status); return r.json(); };
const D = d => new Date(d + 'T12:00:00Z');
const todayISO = () => new Date().toLocaleDateString('en-CA', {timeZone: 'America/New_York'});
const daysAgoISO = n => { const d = D(todayISO()); d.setUTCDate(d.getUTCDate() - n); return d.toISOString().slice(0, 10); };
const yr = new Date().getUTCFullYear();
const fmtD = d => d ? D(d).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: D(d).getUTCFullYear() === yr ? undefined : 'numeric', timeZone: 'UTC'}) : '—';
const fmtDY = d => d ? D(d).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'}) : '—';
const fmtUK = iso => new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'}).format(new Date(iso));
const fmtUKlong = iso => new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/London', weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'}).format(new Date(iso));
const dayDiff = (a, b) => Math.round((D(b) - D(a)) / 864e5);
function ago(d) {
  if (!d) return '';
  const n = dayDiff(d, todayISO());
  if (n <= 0) return 'Today';
  if (n === 1) return 'Yesterday';
  if (n < 7) return `${n}d ago`;
  if (n < 60) return `${Math.round(n / 7)}w ago`;
  if (n < 730) return `${Math.round(n / 30.4)}mo ago`;
  return `${Math.round(n / 365)}y ago`;
}
const money = n => n == null ? '—' : Math.abs(n) >= 1e9 ? '$' + (n / 1e9).toFixed(2) + 'B' : Math.abs(n) >= 1e6 ? '$' + (n / 1e6).toFixed(Math.abs(n) >= 1e7 ? 1 : 2) + 'M' : Math.abs(n) >= 1e3 ? '$' + Math.round(n / 1e3) + 'K' : '$' + Math.round(n);
const usd = (n, dp = 2) => n == null ? '—' : (n < 0 ? '-' : '') + '$' + Math.abs(n).toLocaleString('en-US', {minimumFractionDigits: dp, maximumFractionDigits: dp});
const usd0 = n => usd(n, 0);
const sgnUsd = n => (n >= 0 ? '+' : '-') + usd(Math.abs(n), Math.abs(n) >= 1e5 ? 0 : 2);
const pct = (p, dp = 2) => p == null ? '—' : `${p >= 0 ? '' : '-'}${Math.abs(p).toLocaleString('en-US', {minimumFractionDigits: dp, maximumFractionDigits: dp})}%`;
const num = n => n == null ? '—' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'K' : Math.round(n).toLocaleString('en-US');
const amtShort = t => t.amount_low && t.amount_high ? `${money(t.amount_low)}–${money(t.amount_high)}` : t.amount_low ? `${money(t.amount_low - 1)}+` : (t.amount || '—');
const mid = t => t.amount_low ? (t.amount_low + (t.amount_high || t.amount_low)) / 2 : null;
const PARTY = {D: 'Democrat', R: 'Republican', I: 'Independent'};
const PHOTO = {'Donald J. Trump': 'static/img/trump.jpg'};
const ROLE = {'Donald J. Trump': 'President'};
const I = {
  up: '<svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  dn: '<svg viewBox="0 0 24 24"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>',
  swap: '<svg viewBox="0 0 24 24"><path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/></svg>',
  back: '<svg viewBox="0 0 24 24"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>',
  bell: '<svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
  share: '<svg viewBox="0 0 24 24"><path d="M12 3v13M7 8l5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/></svg>',
  chevd: '<svg viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
  doc: '<svg viewBox="0 0 24 24"><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></svg>',
  bank: '<svg viewBox="0 0 24 24"><path d="M3 10h18L12 4zM5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/></svg>',
  bond: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h6M7 13h10M7 16h4"/></svg>',
  cap: '<svg viewBox="0 0 24 24"><path d="M12 3v2M9.5 7.5a2.5 2.5 0 0 1 5 0V9h-5zM4 11h16L12 9zM6 11v7M10 11v7M14 11v7M18 11v7M3 21h18M4 18.5h16"/></svg>',
  copy: '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>',
  ext: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  pie: '<svg viewBox="0 0 24 24"><path d="M21 12A9 9 0 1 1 12 3v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/></svg>',
};
const isWide = () => matchMedia('(min-width:861px)').matches;
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast.h); toast.h = setTimeout(() => t.hidden = true, 2600); }
const store = {get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } }, set: (k, v) => localStorage.setItem(k, JSON.stringify(v))};

/* new since last visit */
const prevVisit = localStorage.getItem('lastVisit') || new Date(Date.now() - 24 * 3600e3).toISOString();
setTimeout(() => localStorage.setItem('lastVisit', new Date().toISOString()), 4000);
const isNew = t => t.first_seen && t.first_seen > prevVisit;

/* theme */
$('#themeBtn').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t; localStorage.setItem('theme5', t);
  $('meta[name=theme-color]').content = t === 'dark' ? '#0c0c0c' : '#f6f4f0';
};

/* ============ building blocks ============ */
const initials = n => {
  const w = (n || '?').replace(/\b(Hon|Dr|Mr|Mrs|Ms|Jr|Sr|II|III|IV)\b\.?/g, '').replace(/,/g, '').trim().split(/\s+/).filter(Boolean);
  return ((w[0] || '?')[0] + (w.length > 1 ? w[w.length - 1][0] : '')).toUpperCase();
};
const photoURL = (name, bio, big) => PHOTO[name] || (bio ? `https://unitedstates.github.io/images/congress/${big ? '450x550' : '225x275'}/${bio}.jpg` : null);
function avatar(name, bio, cls = '') {
  const ph = `<span class="av ${cls}">${esc(initials(name))}</span>`;
  const u = photoURL(name, bio);
  if (!u) return ph;
  return `<img class="av ${cls}" loading="lazy" alt="" src="${esc(u)}" data-ph="${esc(ph)}" onerror="this.outerHTML=this.dataset.ph">`;
}
function portrait(name, bio, cls = '') {
  const u = photoURL(name, bio, true);
  const ini = `<span class="ini">${esc(initials(name))}</span>`;
  return u ? `<img class="${cls}" loading="lazy" alt="" src="${esc(u)}" onerror="this.outerHTML='${esc(ini).replace(/'/g, '&#39;')}'">` : ini;
}
function logo(ticker, kind, cls = '') {
  if (!ticker) return `<span class="logo ph ${cls}">${kind === 'BOND' ? I.bond : kind === 'GS' ? I.bank : I.doc}</span>`;
  const t = encodeURIComponent(ticker.replace('.', '-'));
  const ph = `<span class="logo ph ${cls}">${esc(ticker.slice(0, 4))}</span>`;
  return `<span class="logo ${cls}"><img loading="lazy" alt="" src="https://assets.parqet.com/logos/symbol/${t}?format=png" data-alt="https://financialmodelingprep.com/image-stock/${t}.png" data-ph="${esc(ph)}" onerror="if(this.dataset.alt){this.src=this.dataset.alt;this.dataset.alt=''}else{this.parentNode.outerHTML=this.dataset.ph}"></span>`;
}
const cleanAsset = t => (t.asset || '').replace(/\s*\[[A-Z]{2}\]\s*$/, '').replace(/\s*\(([A-Z0-9.\-\/$]{1,10})\)\s*$/, '').replace(/\s+-\s+/g, ' – ').replace(/\s+/g, ' ').trim();
const assetName = t => t.company || cleanAsset(t);
function loc(p) {
  if (p.chamber === 'Executive') return ROLE[p.politician] || p.district || 'Executive';
  if (p.chamber === 'House' && p.district) {
    const m = p.district.match(/^([A-Z]{2})0*(\d+)$/);
    if (m) return m[2] === '0' ? `${m[1]}-AL` : `${m[1]}-${m[2]}`;
  }
  return p.state || '';
}
const chamberLbl = c => c === 'Executive' ? 'White House' : c;
const metaShort = p => `${p.party || '?'} · ${loc(p)}${p.chamber !== 'Executive' ? ' · ' + p.chamber : ''}`;
function sideTag(t) {
  if (t.side === 'buy') return `<span class="side buy">${I.up}Buy</span>`;
  if (t.side === 'sell') return `<span class="side sell">${I.dn}${/partial/i.test(t.tx_type || '') ? 'Partial sell' : 'Sell'}</span>`;
  return `<span class="side other">${I.swap}${esc(t.tx_type || 'Other')}</span>`;
}
const lagTag = t => t.lag_days == null || t.lag_days < 0 ? '' : `<span class="lag${t.lag_days > 45 ? ' late' : ''}" title="Days between the trade and its public disclosure">${t.lag_days === 0 ? 'same day' : t.lag_days + 'd lag'}</span>`;
const chgTxt = p => p == null ? '' : `<span class="${p >= 0 ? 'up' : 'dn'}">${p >= 0 ? '▲' : '▼'} ${Math.abs(p).toFixed(1)}%</span>`;

/* Trade row, styled like Insiderwave's "Trades in this update" list */
/* ---- committee context (committees.py): "possible overlap" between a member's current committees and the stock's sector ---- */
let CTX = store.get('ctx', null);
function overlap(t) {
  if (!CTX || !t || !t.bioguide || !t.ticker || (t.tx_date || '') < CTX.since) return null;
  const cs = CTX.m[t.bioguide], tk = CTX.t[(t.ticker || '').toUpperCase()];
  if (!cs || !tk) return null;
  const tags = tk.slice(1), hit = cs.map(k => { const lead = k.endsWith('*'), id = k.replace('*', ''), c = CTX.c[id]; const m = c && c.tags.filter(x => tags.includes(x)); return m && m.length ? {id, lead, n: c.n, tags: m} : null; }).filter(Boolean);
  return hit.length ? {industry: tk[0], hit} : null;
}
const ovKey = t => `${t.bioguide}|${(t.ticker || '').toUpperCase()}|${t.tx_date || ''}|${t.politician}`;
const ovTag = t => CTX ? (overlap(t) ? `<span class="ovtag" data-ov="${esc(ovKey(t))}" title="Possible committee overlap">Possible overlap</span>` : '') : `<span class="ovslot" data-ovk="${esc(ovKey(t))}"></span>`;
const ovFromKey = k => { const [bioguide, ticker, tx_date, politician] = k.split('|'); return {bioguide, ticker, tx_date, politician}; };
function ovExplain(t, o) {
  const L = CTX.labels;
  return `<div class="ovx"><div class="ovx-h"><span class="ovtag">Possible overlap</span></div>
    ${o.hit.map(h => `<p><b>${esc(t.politician)}</b> ${h.lead ? 'is a leader (chair or ranking member) of' : 'sits on'} the <b>${esc(h.n)}</b>, which oversees ${h.tags.map(x => esc(L[x] || x)).join(' and ')}.</p>`).join('')}
    <p><b>${esc(t.ticker)}</b> is classed as <b>${esc(o.industry)}</b> by Yahoo Finance.</p>
    <p class="mute">This only means the committee's area and the company's sector line up. It is not evidence of wrongdoing or of inside information. Committee seats are current assignments from the congress-legislators project, so they are only matched to trades made since ${fmtDY(CTX.since)}; seats can change during a Congress. Broad committees (Appropriations, Ways and Means, Finance, Budget) are not counted.</p></div>`;
}
function openOverlap(k) { const t = ovFromKey(k), o = overlap(t); if (!o) return; openSheet(`<div class="td-head">${logo(t.ticker)}<div style="min-width:0"><h2>${esc(t.ticker)}</h2><div class="an">Committee context</div></div></div>${ovExplain(t, o)}`); }
async function loadCtx() {
  try { const d = await api('/api/context'); CTX = d; try { store.set('ctx', d); } catch (e) {} } catch (e) { return; }
  $$('.ovslot').forEach(el => { const t = ovFromKey(el.dataset.ovk); el.outerHTML = overlap(t) ? `<span class="ovtag" data-ov="${esc(el.dataset.ovk)}" title="Possible committee overlap">Possible overlap</span>` : ''; });
}
function tradeRow(t, showWho = true) {
  const sh = t.est_price && t.amount_low ? mid(t) / t.est_price : null;
  const title = t.ticker || cleanAsset(t) || 'Undisclosed asset';
  const sub = t.est_price != null ? `<b>${usd(t.est_price)}</b>/share` : t.ticker ? esc(assetName(t)) : esc(t.asset_type === 'BOND' ? 'Bond · no market price' : (cleanAsset(t) && t.ticker ? '' : 'Not exchange-listed'));
  return `<button class="trow" data-trade="${esc(t.uid)}">
    ${logo(t.ticker, t.asset_type)}
    <div class="mid">
      <div class="l1"><span class="tk">${esc(title)}</span>${sideTag(t)}${isNew(t) ? '<span class="newtag">NEW</span>' : ''}${/^From the OGE 278e/.test(t.description || '') ? '<span class="lag atag" title="From an annual OGE 278e financial disclosure report">278e</span>' : ''}${ovTag(t)}</div>
      <div class="l2">${sub}</div>
    </div>
    <div class="r">
      <div class="sh">${sh ? `~${num(sh)} shares` : esc(t.owner && t.owner !== 'Self' ? t.owner : '')}</div>
      <div class="amt">${amtShort(t)}</div>
      ${t.pct_since != null ? `<div class="pc">${chgTxt(t.pct_since)}</div>` : ''}
    </div>
    <div class="l3">${showWho ? `<span class="who-mini">${avatar(t.politician, t.bioguide, 'round')}${esc(t.politician)}<span class="mute" style="font-weight:500">${esc(t.party || '')}${t.party ? '-' : ''}${esc(loc(t))}</span></span>` : ''}<span class="dates"><span title="Trade date → disclosure date">Traded ${fmtD(t.tx_date)} · Filed ${fmtD(t.disclosure_date)}</span>${lagTag(t)}<span class="ago">${ago(t.disclosure_date).replace("Yesterday", "1d ago")}</span></span></div>
  </button>`;
}
const skRows = n => Array(n).fill('<div class="sk-row"></div>').join('');
const empty = (a, b) => `<div class="empty"><b>${a}</b>${b}</div>`;

/* ============ charts ============ */
function smoothPath(pts) {
  if (pts.length < 2) return '';
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 2] || pts[i - 1], p1 = pts[i - 1], p2 = pts[i], p3 = pts[i + 1] || p2;
    const t = 0.18;
    const c1 = [p1[0] + (p2[0] - p0[0]) * t, p1[1] + (p2[1] - p0[1]) * t];
    const c2 = [p2[0] - (p3[0] - p1[0]) * t, p2[1] - (p3[1] - p1[1]) * t];
    d += `C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}
function sparkSVG(vals, up) {
  if (!vals || vals.length < 2) return '';
  const W = 300, H = 62, mn = Math.min(...vals), mx = Math.max(...vals), r = mx - mn || 1;
  const pts = vals.map((v, i) => [i / (vals.length - 1) * W, H - 6 - (v - mn) / r * (H - 14)]);
  const col = up ? 'var(--up-l)' : 'var(--dn)';
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path d="${smoothPath(pts)}" stroke="${col}" stroke-width="1.8" fill="none" vector-effect="non-scaling-stroke"/></svg>`;
}

/* ============ routing ============ */
let baseView = 'home', statusData = null, lastSeen = null;
const VIEWS = ['home', 'trades', 'people', 'alerts', 'pol', 'mb', 'stock', 'un', 'und'];
function showView(v) {
  VIEWS.forEach(x => { $('#v-' + x).hidden = x !== v; });
  document.body.classList.toggle('on-pol', v === 'pol');
  const nav = v === 'pol' || v === 'stock' ? null : v === 'mb' ? 'home' : v;
  $$('#tabs a, #dock a').forEach(a => a.classList.toggle('on', a.dataset.v === nav));
}
function route() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (h.startsWith('x=')) { openTrade(h.slice(2)); return; }
  if (h.startsWith('m=')) { history.replaceState(null, '', '#p=' + encodeURIComponent(h.slice(2))); route.after = 'mirror'; }
  if (h.startsWith('f=')) { history.replaceState(null, '', '#p=' + encodeURIComponent(h.slice(2))); route.after = 'follow'; }
  const h2 = decodeURIComponent(location.hash.slice(1));
  if (h2 !== h) return route();
  closeSheet(false);
  let v = 'home';
  if (h.startsWith('p=')) v = 'pol';
  else if (['trades', 'people', 'alerts'].includes(h)) v = h;
  else if (h === 'mostbought') v = 'mb';
  else if (h === 'unusual') v = 'un';
  else if (h.startsWith('unusual=')) v = 'und';
  else if (h.startsWith('t=')) v = 'stock';
  else if (h.startsWith('people:')) { const [, s, per] = h.split(':'); if (s) P.sort = s; if (per) P.period = per; P.dir = -1; v = 'people'; }
  else if (h === 'info') v = 'alerts';
  const changed = v !== route.cur || ((v === 'pol' || v === 'stock' || v === 'und') && h !== route.h);
  showView(v); route.cur = v; route.h = h;
  if (!['pol', 'mb', 'stock', 'un', 'und'].includes(v)) baseView = v;
  if (changed) window.scrollTo({top: 0, behavior: 'instant'});
  if (v === 'home') loadHome();
  if (v === 'mb' && !MB.loaded) loadMostBought();
  if (v === 'trades' && !F.loaded) { F.loaded = true; loadKpis(); loadFeed(); }
  if (v === 'people') loadPeople();
  if (v === 'alerts') renderAlerts();
  if (v === 'pol' && changed) openPolitician(h.slice(2));
  if (v === 'stock' && changed) openStock(h.slice(2));
  if (v === 'un') renderUnusualAll();
  if (v === 'und' && changed) openUnusual(h.slice(8));
}
addEventListener('hashchange', route);
addEventListener('scroll', () => $('#top').classList.toggle('scrolled', scrollY > 4), {passive: true});

/* ============ status ============ */
async function loadStatus() {
  try {
    const s = await api('/api/status');
    statusData = s;
    const live = $('#live');
    live.classList.toggle('busy', s.running);
    $('#liveTxt').textContent = s.running ? 'Checking…' : s.last_refresh ? `Updated ${fmtUK(s.last_refresh)}` : 'Live';
    const newest = s.sources.map(x => x.newest_disclosure).sort().pop();
    live.title = `Last checked ${s.last_refresh ? fmtUKlong(s.last_refresh) : 'never'}. Newest filing ${fmtDY(newest)}. Click to check now.`;
    const seen = s.sources.map(x => x.newest_seen).sort().pop();
    if (lastSeen && seen > lastSeen) { F.loaded && loadFeed(); toast('New trades just came in'); }
    lastSeen = seen;
    if (route.cur === 'alerts') renderAlerts();
  } catch (e) { /* offline */ }
}
$('#live').onclick = async () => {
  const r = await api('/api/refresh', {method: 'POST'}).catch(() => ({message: 'Could not start a check'}));
  toast(r.started ? 'Checking for new filings…' : r.message);
  setTimeout(loadStatus, 1500);
};

/* ============ portfolios (shared) ============ */
let PF = null;
async function portfolios() {
  if (!PF) PF = api('/api/portfolios').then(rows => { const m = new Map(); rows.forEach(r => m.set(r.politician, r)); return m; }).catch(() => new Map());
  return PF;
}
function portfolioCard(p, pf, o = {}) {
  const all = pf && pf.periods ? pf.periods[o.period || 'ALL'] : null;
  const up = !all || all[1] == null || all[1] >= 0;
  return `<button class="pcard" data-pol="${esc(p.politician)}">
    <div class="ph">${portrait(p.politician, p.bioguide)}${o.rank ? `<span class="rank">${o.rank}</span>` : ''}<div class="tag"><i class="pty-${esc(p.party || '')}"></i>${esc(p.party || '?')} · ${esc(loc(p))}</div><div class="nm">${esc(p.politician)}</div></div>
    ${pf ? `<div class="b"><div class="k">Portfolio Value</div><div class="v">${usd0(pf.value)}</div>
      <div class="d">${all ? `<span>${sgnUsd(all[0])}</span><span class="${up ? 'up' : 'dn'}"><span class="tri">${up ? '▲' : '▼'}</span> ${pct(Math.abs(all[1]))}</span>` : ''}</div></div>
      <div class="spark">${sparkSVG(pf.spark, up)}</div>`
    : `<div class="b"><div class="k">${num(p.n)} disclosed trades</div></div><div class="none">No priced stock trades to build a portfolio from.</div>`}
  </button>`;
}

/* ============ home ============ */
const H = {period: '1Y', loaded: false};
const MB = {days: '90', loaded: false, items: [], seq: 0};
const MB_NOTE = {'30': '30 days', '90': '90 days', '365': 'year'};
async function loadMostBought() {
  MB.loaded = true;
  const seq = ++MB.seq;
  if (!MB.items.length) { $('#mbList').innerHTML = skRows(5); $('#mbFull').innerHTML = skRows(8); }
  $$('#mbPills button, #mbPills2 button').forEach(x => x.classList.toggle('on', x.dataset.v === MB.days));
  try {
    const d = await api(`/api/most_bought?days=${MB.days}&etf=1`);
    if (seq !== MB.seq) return;
    MB.items = d.items || [];
    const note = `Stocks and funds ranked by how many politicians bought · last ${MB_NOTE[MB.days]}`;
    $('#mbNote').textContent = note; $('#mbNote2').textContent = note;
    renderMostBought();
  } catch (e) { MB.loaded = false; $('#mbList').innerHTML = $('#mbFull').innerHTML = empty('Could not load', String(e.message || e)); }
}
/* ---- unusual activity (unusual.py): every type, ranked; Home top 5, full list #unusual, detail #unusual=<id> ---- */
const UT = {cluster_buy: ['Cluster buy', 'cl'], bipartisan: ['Bipartisan', 'bp'], cluster_sell: ['Cluster sell', 'cs'], large: ['Large', 'lg'],
  committee: ['Committee', 'cm'], first_buy: ['First buy', 'fb'], options: ['Options', 'op'], burst: ['Burst', 'bu'], late: ['Late filing', 'lt'], hindsight: ['Hindsight', 'hs']};
const UT_HELP = {
  cluster_buy: 'Three or more different politicians bought the same stock or fund within 14 days of each other.',
  bipartisan: 'A buying cluster (3+ politicians within 14 days) that includes both Democrats and Republicans.',
  cluster_sell: 'Three or more different politicians sold the same stock or fund within 14 days of each other.',
  large: 'A trade with a disclosed range starting at $250,000 or more, or one in the top 1% of that person’s own trades by size.',
  committee: 'A $50K+ trade in a sector overseen by one of the member’s current committees. Possible overlap only: it does not show the trade was related to committee work.',
  first_buy: 'A heavy trader (100+ disclosed trades) bought $50K+ of a stock they had never traded before in the disclosures.',
  options: 'An options trade. Options are leveraged bets on a price move by a certain date.',
  burst: 'Far more trades in one week than this politician usually makes (5x or more their weekly average over the prior year).',
  late: 'Disclosed more than 45 days after the trade, past the STOCK Act deadline. Usually paperwork, sometimes not.',
  hindsight: 'The price moved 15% or more in the trade’s favour within 30 days. This is hindsight: it shows timing, not intent or inside information.'};
const UN = {loaded: false, all: [], win: '30', type: ''};
const lastNm = n => { const w = String(n || '').replace(/,/g, ' ').split(/\s+/).filter(x => x && !/^(Jr|Sr|II|III|IV)\.?$/.test(x)); return w[w.length - 1] || n; };
const unTag = t => `<span class="unb ${(UT[t] || [, 'lg'])[1]}">${esc((UT[t] || [t])[0])}</span>`;
function unRow(e) {
  const lead = e.ticker ? logo(e.ticker) : avatar(e.pols[0] && e.pols[0].name, e.pols[0] && e.pols[0].bioguide, 'round');
  const stack = e.n_pols > 1 ? `<div class="mbwho"><span class="mbstack">${e.pols.slice(0, 4).map(p => avatar(p.name, p.bioguide, 'round')).join('')}</span><span>${esc(e.pols.map(p => lastNm(p.name)).slice(0, 3).join(', '))}${e.n_pols > 3 ? ` +${e.n_pols - 3}` : ''}</span></div>` : '';
  return `<button class="unrow" data-un="${esc(e.id)}">${lead}
    <div class="um"><div class="ut">${unTag(e.type)}<span class="mute">${fmtD(e.disclosed)}</span></div><div class="t"><b>${esc(e.title)}</b></div><div class="s why">${esc(e.why)}</div>${stack}</div></button>`;
}
async function loadUnusual(force) {
  if (UN.loaded && !force) return;
  UN.loaded = true;
  let d; try { d = await api('/api/unusual'); } catch (e) { UN.loaded = false; return; }
  UN.all = d.events || [];
  const cut = daysAgoISO(30), home = UN.all.filter(e => e.disclosed >= cut).slice(0, 5);
  if (home.length) {
    $('#unHead').hidden = false; $('#unList').hidden = false; $('#unMore').hidden = false;
    $('#unList').innerHTML = home.map(unRow).join('');
  }
  if (route.cur === 'un') renderUnusualAll();
}
function renderUnusualAll() {
  if (!UN.loaded) { loadUnusual(); $('#unFull').innerHTML = skRows(6); return; }
  const cut = daysAgoISO(+UN.win), inWin = UN.all.filter(e => e.disclosed >= cut);
  const n = {}; inWin.forEach(e => n[e.type] = (n[e.type] || 0) + 1);
  if (UN.type && !n[UN.type]) UN.type = '';
  $('#unTypes').innerHTML = `<button class="chip-btn ${UN.type ? '' : 'on'}" data-ut="">All <small>${inWin.length}</small></button>`
    + Object.keys(UT).filter(k => n[k]).map(k => `<button class="chip-btn ${UN.type === k ? 'on' : ''}" data-ut="${k}"><i class="dot ${UT[k][1]}"></i>${UT[k][0]} <small>${n[k]}</small></button>`).join('');
  const list = inWin.filter(e => !UN.type || e.type === UN.type);
  $('#unNote').textContent = UN.type ? UT_HELP[UN.type] : `${list.length} item${list.length === 1 ? '' : 's'} disclosed in the last ${UN.win} days, strongest first`;
  $('#unFull').innerHTML = list.map(unRow).join('') || empty('Nothing unusual in this window', 'Try a longer window.');
  $$('#unTypes [data-ut]').forEach(b => b.onclick = () => { UN.type = b.dataset.ut; renderUnusualAll(); });
}
$$('#unWin button').forEach(b => b.onclick = () => { UN.win = b.dataset.v; $$('#unWin button').forEach(x => x.classList.toggle('on', x === b)); renderUnusualAll(); });
async function openUnusual(id) {
  const el = $('#v-und');
  el.innerHTML = `<div class="mbp-top"><button class="ib" data-back aria-label="Back">${I.back}</button></div><div class="sk-card" style="height:120px;margin-top:16px"></div><div class="sk-card" style="height:240px;margin-top:16px"></div>`;
  let e; try { e = await api('/api/unusual_event?id=' + encodeURIComponent(id)); }
  catch (x) { el.innerHTML = `<div class="mbp-top"><button class="ib" data-back aria-label="Back">${I.back}</button></div>` + empty('This item is no longer listed', 'Unusual activity covers the last 90 days.'); return; }
  if (route.h !== 'unusual=' + id) return;
  e.trades.forEach(t => trades.set(t.uid, t));
  const T = [...e.trades].sort((a, b) => (b.tx_date || '') < (a.tx_date || '') ? -1 : 1);
  const first = [...e.trades].filter(t => t.est_price).sort((a, b) => a.tx_date < b.tx_date ? -1 : 1)[0];
  const cur = e.trades.find(t => t.cur_price != null);
  const mv = e.ticker && first && cur ? (cur.cur_price / first.est_price - 1) * 100 : null;
  const ticks = [...new Set(e.trades.map(t => t.ticker).filter(Boolean))];
  const days = Math.max(1, Math.round((D(e.to) - D(e.from)) / 864e5) + 1);
  el.innerHTML = `<div class="mbp-top"><button class="ib" data-back aria-label="Back">${I.back}</button></div>
    <div class="und-h">${e.ticker ? logo(e.ticker) : avatar(e.pols[0].name, e.pols[0].bioguide, 'round')}<div class="und-t">${unTag(e.type)}<h1>${esc(e.title)}</h1>${e.name && e.ticker ? `<div class="mute">${esc(e.name)}</div>` : ''}</div></div>
    <p class="und-why">${esc(e.why)}</p>
    ${e.type === 'hindsight' ? '<p class="und-warn">Hindsight: this looks back at what the price did after the trade. It says nothing about why they traded.</p>' : ''}
    <div class="st-stats">
      <div class="card"><div class="k">Politicians</div><b>${e.n_pols}</b><span>${e.pols.map(p => p.party).filter(Boolean).sort().join(' · ') || ''}</span></div>
      <div class="card"><div class="k">Trades</div><b>${e.n_trades}</b><span>${e.from === e.to ? fmtDY(e.from) : `${fmtD(e.from)} – ${fmtD(e.to)} · ${days} days`}</span></div>
      <div class="card"><div class="k">Est. amount</div><b>${money(e.est_total)}</b><span>range midpoints</span></div>
      <div class="card"><div class="k">${e.ticker ? `${esc(e.ticker)} since` : 'Disclosed'}</div>${e.ticker ? `<b class="${mv == null ? '' : mv >= 0 ? 'up' : 'dn'}">${mv == null ? '—' : (mv >= 0 ? '+' : '') + mv.toFixed(1) + '%'}</b><span>${first ? `from ${usd(first.est_price)} on ${fmtD(first.tx_date)}` : 'no price'}</span>` : `<b>${fmtD(e.disclosed)}</b><span>${ticks.length} ticker${ticks.length === 1 ? '' : 's'}</span>`}</div>
    </div>
    ${e.ticker ? `<div class="card st-chart" style="margin-top:14px"><div id="unChart"><div class="sk-card" style="height:230px"></div></div><div class="st-pop card" id="unPop" hidden></div>
      <div class="st-leg"><span><i class="b"></i>Buy</span><span><i class="s"></i>Sell</span><span class="mute">Only the trades in this item</span></div></div>
      <a class="viewall more-btn" href="#t=${encodeURIComponent(e.ticker)}">Open ${esc(e.ticker)} stock page</a>`
      : ticks.length ? `<div class="und-ticks">${ticks.slice(0, 24).map(t => `<button class="chip-btn" data-tick="${esc(t)}">${esc(t)}</button>`).join('')}</div>` : ''}
    <div class="sec-h"><h2>Politicians</h2><small class="mute">tap for profile</small></div>
    <div class="und-pols">${e.pols.map(p => `<button class="chip-btn und-p" data-pol="${esc(p.name)}">${avatar(p.name, p.bioguide, 'round')}${esc(p.name)}${p.party ? `<small class="mute">${esc(p.party)}</small>` : ''}</button>`).join('')}</div>
    <div class="sec-h"><h2>Trades involved</h2><small class="mute">${e.n_trades}${e.n_trades > e.trades.length ? ` · first ${e.trades.length} shown` : ''}</small></div>
    <div class="card tlist">${T.map(t => tradeRow(t)).join('')}</div>
    <p class="fine"><b>${esc((UT[e.type] || [e.type])[0])}.</b> ${UT_HELP[e.type] || ''} Amounts are disclosed ranges; prices are estimated from Yahoo daily closes.</p>`;
  if (e.ticker) {
    let st; try { st = await api('/api/stock?ticker=' + encodeURIComponent(e.ticker)); } catch (x) { st = null; }
    if (route.h !== 'unusual=' + id) return;
    ST.t = e.ticker; ST.s = st || {}; ST.rows = e.trades; ST.pts = [];
    if (st && st.px) { let ms = D(st.px.d0).getTime(); st.px.dd.forEach((x, i) => { ms += x * 864e5; ST.pts.push([new Date(ms).toISOString().slice(0, 10), st.px.c[i]]); }); }
    ST_RANGES.EV = Math.max(90, Math.round((Date.now() - D(e.from)) / 864e5) + 45); ST.range = 'EV';
    const c = $('#unChart'); c.innerHTML = stockChart(Math.max(280, c.clientWidth));
    c.onclick = x => { const m = x.target.closest('[data-mk]'); if (m) stockPop(+m.dataset.mk, '#unPop'); };
  }
}
function mbRows(it) {
  if (!it.length) return empty('No purchases in this window', 'Try a longer window.');
  return it.map((x, i) => {
    const av = x.pols.slice(0, 4).map(p => avatar(p.name, p.bioguide, 'round')).join('');
    const more = x.n_pols > 4 ? `<span class="av round more">+${x.n_pols - 4}</span>` : '';
    const who = x.n_pols === 1 ? x.pols[0].name.split(' ').slice(-1)[0] : `${x.n_pols} politicians`;
    return `<button class="mbrow" data-tick="${esc(x.ticker)}" title="${esc(x.pols.map(p => p.name).join(', '))}"><span class="rk">${i + 1}</span>${logo(x.ticker)}
      <div class="mbmid"><div class="tk">${esc(x.ticker)}${x.kind === 'etf' ? ' <span class="tag">ETF</span>' : ''}</div><div class="nm">${esc(x.name || '')}</div></div>
      <div class="r"><div class="val">${money(x.est_total)}</div><div class="g ${x.chg == null ? '' : x.chg >= 0 ? 'up' : 'dn'}">${x.chg == null ? '' : (x.chg >= 0 ? '+' : '') + x.chg.toFixed(1) + '%'}</div></div>
      <div class="mbwho"><span class="mbstack">${av}${more}</span><span>${esc(who)} · ${x.n_buys} buy${x.n_buys === 1 ? '' : 's'}</span></div></button>`;
  }).join('');
}
function renderMostBought() {
  $('#mbList').innerHTML = mbRows(MB.items.slice(0, 5));
  $('#mbFull').innerHTML = mbRows(MB.items);
}
$$('#mbPills button, #mbPills2 button').forEach(b => b.onclick = () => { MB.days = b.dataset.v; loadMostBought(); });

async function loadIntro() {
  if (loadIntro.done) return; loadIntro.done = true;
  let d; try { d = await api('/api/intro'); } catch (e) { loadIntro.done = false; return; }
  const sg = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
  const cards = [
    d.late && d.late.trades ? [d.late.trades.toLocaleString('en-US'), `congressional trades filed past the 45-day deadline in the last year, by ${d.late.members} members`, '#unusual'] : null,
    d.best_1y != null && d.spy_1y != null ? [sg(d.best_1y), `best 1-year portfolio return. The S&P 500 did ${sg(d.spy_1y)}`, '#people:ret:1Y'] : null,
    d.eligible ? [`${d.beat}<small> of ${d.eligible}</small>`, 'tracked portfolios beat the S&P 500 over the past year', '#people:ret:1Y'] : null,
    [d.trades.toLocaleString('en-US'), `trades disclosed · ${d.portfolios} portfolios tracked`, '#trades']].filter(Boolean);
  $('#heroCards').innerHTML = cards.map(c => `<a class="hcard" href="${c[2]}"><b>${c[0]}</b><span>${c[1]}</span></a>`).join('');
}
async function loadHome() {
  loadIntro();
  if (!MB.loaded) loadMostBought();
  if (!UN.loaded) loadUnusual();
  const pfs = await portfolios();
  const list = [...pfs.values()];
  // top performers: meaningful portfolios only
  const k = H.period;
  const elig = list.filter(p => p.value >= 50000 && p.n_priced >= 5 && p.periods[k] && p.periods[k][1] != null);
  elig.sort((a, b) => b.periods[k][1] - a.periods[k][1]);
  $('#perfRail').innerHTML = elig.slice(0, 12).map((p, i) => {
    const r = p.periods[k][1], up = r >= 0;
    return `<button class="pcard-s" data-pol="${esc(p.politician)}"><div class="ph">${portrait(p.politician, p.bioguide)}<span class="rank">${i + 1}</span><span class="badge ${up ? 'up' : 'dn'}">${up ? '+' : ''}${pct(r)}</span></div>
      <div class="b"><div class="nm">${esc(p.politician)}</div><div class="mt">${esc(metaShort(p))}</div></div></button>`;
  }).join('') || empty('No data yet', '');
  if (!H.loaded) {
    H.loaded = true;
    const tot = list.reduce((a, p) => a + p.value, 0);
    const f = list.filter(p => p.n_priced >= 5 && p.periods.ALL && p.periods.ALL[1] > 0 && p.politician !== 'Donald J. Trump').sort((a, b) => b.value - a.value)[0];
    if (f && isWide()) {
      const all = f.periods.ALL;
      $('#heroPhone').innerHTML = `<div class="scr" data-pol="${esc(f.politician)}"><span class="notch"></span><div class="ph">${portrait(f.politician, f.bioguide)}<span class="hb" style="left:14px">${I.back}</span><span class="hb" style="right:54px">${I.bell}</span><span class="hb" style="right:14px">${I.share}</span><div class="nm">${esc(f.politician.split(' ')[0])}</div></div>
        <div class="bd"><div class="k">Portfolio Value</div><div class="v">${usd(f.value)}</div><div class="d"><span>${sgnUsd(all[0])}</span><span class="up">▲ ${pct(all[1])}</span></div></div>
        <div class="sp">${sparkSVG(f.spark, true)}</div><div class="tb"><span>1W</span><span>1M</span><span>3M</span><span>YTD</span><span>1Y</span><span>5Y</span><span class="on">ALL</span></div></div>`;
    }
    const top = list.filter(p => p.n_priced >= 5).sort((a, b) => b.value - a.value).slice(0, isWide() ? 8 : 6);
    $('#homeGrid').innerHTML = top.map(p => portfolioCard(p, p)).join('');
    $('#homeTrades').innerHTML = skRows(5);
    const d = await api('/api/trades?limit=5&sort=disclosure_date');
    $('#homeTrades').innerHTML = d.trades.map(t => tradeRow(t)).join('');
  }
}
$$('#perfPills button').forEach(b => b.onclick = () => { $$('#perfPills button').forEach(x => x.classList.toggle('on', x === b)); H.period = b.dataset.v; $('#perfAll').href = '#people:ret:' + H.period; loadHome(); });

/* ============ trades feed ============ */
const F = {offset: 0, range: '90', side: '', chamber: '', ticker: null, total: 0, PAGE: 40, seq: 0, loaded: false};
const trades = new Map();
function rangeDates() {
  if (F.range === 'custom') return [$('#from').value || null, $('#to').value || null];
  if (F.range === 'all') return [null, null];
  return [daysAgoISO(+F.range), null];
}
function feedParams() {
  const p = new URLSearchParams();
  const set = (k, v) => v && p.set(k, v);
  const [a, b] = rangeDates();
  set('q', $('#q').value.trim()); set('chamber', F.chamber); set('party', $('#party').value); set('side', F.side);
  set('date_field', $('#dateField').value); set('date_from', a); set('date_to', b); set('asset', $('#assetSel').value);
  set('sort', $('#sort').value); set('ticker', F.ticker);
  p.set('limit', F.PAGE); p.set('offset', F.offset);
  return p;
}
async function loadFeed(append = false) {
  if (!append) { F.offset = 0; $('#feed').innerHTML = skRows(8); }
  const seq = ++F.seq;
  const d = await api('/api/trades?' + feedParams());
  if (seq !== F.seq) return;
  d.trades.forEach(t => trades.set(t.uid, t));
  F.total = d.total;
  const html = d.trades.map(t => tradeRow(t)).join('');
  if (append) $('#feed').insertAdjacentHTML('beforeend', html);
  const lbl = {0: 'today', 7: 'in the past week', 30: 'in the past month', 90: 'in the past 3 months', 365: 'in the past year', all: 'all time', custom: 'in the chosen dates'}[F.range];
  const qv = $('#q').value.trim();
  if (!append) $('#feed').innerHTML = html || (qv ? empty(`No trades match “${esc(qv)}” ${F.range === 'all' ? 'at all' : lbl}`, F.range === 'all' ? 'Try a ticker (GOOGL), a company (Google) or a politician’s name.' : 'Try a wider date range like 1 year or All, or fewer filters.') : empty('No trades match', 'Try a wider date range or fewer filters.'));
  const newN = d.trades.filter(isNew).length;
  $('#feedCount').innerHTML = `<span><b>${d.total.toLocaleString()}</b> trades ${$('#dateField').value === 'tx_date' ? 'made' : 'disclosed'} ${lbl}${newN && !append ? ` · <span style="color:var(--blue);font-weight:600">${newN} new since your last visit</span>` : ''}</span>`;
  $('#tickChip').innerHTML = F.ticker ? `<button class="chip-btn" id="clrTick">${esc(F.ticker)} ✕</button>` : '';
  $('#more').hidden = F.offset + F.PAGE >= d.total;
}
async function loadKpis() {
  const days = F.range === 'all' ? 3650 : F.range === 'custom' ? 365 : Math.max(+F.range, 1);
  const p = new URLSearchParams({days});
  if (F.chamber) p.set('chamber', F.chamber);
  if ($('#party').value) p.set('party', $('#party').value);
  const s = await api('/api/stats?' + p);
  const t = s.totals, top = s.top_tickers[0], tp = s.top_politicians[0];
  $('#kpis').innerHTML = `
    <div class="kpi"><div class="k">Trades disclosed</div><div class="v">${(t.n || 0).toLocaleString()}</div><div class="f">${money(t.vol_low)}–${money(t.vol_high)}</div></div>
    <div class="kpi"><div class="k">Buys / sells</div><div class="v"><span class="up">${num(t.buys || 0)}</span> <span class="mute" style="font-weight:400">/</span> <span style="color:var(--sell)">${num(t.sells || 0)}</span></div><div class="f">${t.pols || 0} people trading</div></div>
    <div class="kpi"><div class="k">Most traded</div>${top ? `<button class="who-k" data-tick="${esc(top.ticker)}">${logo(top.ticker, null, 'sm')}<span>${esc(top.ticker)}<br><small class="mute" style="font-weight:500">${top.n} trades</small></span></button>` : '—'}</div>
    <div class="kpi"><div class="k">Most active</div>${tp ? `<button class="who-k" data-pol="${esc(tp.politician)}">${avatar(tp.politician, tp.bioguide)}<span>${esc(tp.politician)}<br><small class="mute" style="font-weight:500">${num(tp.n)} trades</small></span></button>` : '—'}</div>`;
}

/* ============ politicians ============ */
const P = {sort: 'value', dir: -1, chamber: '', list: null, period: '1Y'};
// same eligibility as Home > Top performers, so "See all" continues that ranking
const perfOK = (pf, k) => !!(pf && pf.value >= 50000 && pf.n_priced >= 5 && pf.periods && pf.periods[k] && pf.periods[k][1] != null);
function syncPolPills() {
  $$('#polSort button').forEach(x => x.classList.toggle('on', x.dataset.v === P.sort));
  $$('#polPeriod button').forEach(x => x.classList.toggle('on', x.dataset.v === P.period));
  $('#polPeriod').hidden = P.sort !== 'ret';
}
async function loadPeople() {
  if (!P.list) {
    $('#polGrid').innerHTML = Array(8).fill('<div class="sk-card"></div>').join('');
    const [people, pfs] = await Promise.all([api('/api/politicians'), portfolios()]);
    P.list = people.map(p => ({...p, pf: pfs.get(p.politician) || null}));
  }
  const q = $('#pq').value.trim(), m = window.BHSearch ? BHSearch.compilePeople(q) : (p => p.politician.toLowerCase().includes(q.toLowerCase()));
  let L = P.list.filter(p => (!P.chamber || p.chamber === P.chamber) && (!q || m(p)));
  const key = {
    value: p => p.pf ? p.pf.value : -1, ret: p => perfOK(p.pf, P.period) ? p.pf.periods[P.period][1] : -1e9,
    n: p => p.n, volume: p => p.volume || 0, latest: p => p.latest || '', name: p => p.politician,
  }[P.sort];
  L.sort((a, b) => { const x = key(a), y = key(b); const c = x < y ? -1 : x > y ? 1 : 0; return P.sort === 'name' ? c * -P.dir : c * P.dir; });
  if (P.sort === 'ret' && P.dir === 1) L = L.filter(p => key(p) > -1e9).concat(L.filter(p => key(p) <= -1e9));
  $('#polDir span').textContent = P.sort === 'name' ? (P.dir === -1 ? 'A → Z' : 'Z → A') : (P.dir === -1 ? 'High → low' : 'Low → high');
  syncPolPills();
  const ret = P.sort === 'ret', nOK = ret ? L.filter(p => key(p) > -1e9).length : 0;
  $('#polGrid').innerHTML = L.map((p, i) => ret ? portfolioCard(p, p.pf, {period: P.period, rank: key(p) > -1e9 ? (P.dir === -1 ? i + 1 : nOK - i) : 0}) : portfolioCard(p, p.pf)).join('') || (q ? empty(`Nobody matches “${esc(q)}”`, 'Search by name, party (e.g. Democrat) or state (e.g. Texas or TX).') : empty('Nobody found', ''));
}

/* ============ politician page ============ */
const POL = {name: null, data: null, period: 'ALL', offset: 0, showAll: false};
const PERIOD_DAYS = {'1W': 7, '1M': 30, '3M': 91, '1Y': 365, '5Y': 1826, 'ALL': 36500};
function periodSlice(s, key) {
  const d = s.d, n = d.length;
  const last = d[n - 1];
  let since;
  if (key === 'YTD') since = last.slice(0, 4) + '-01-01';
  else { const x = D(last); x.setUTCDate(x.getUTCDate() - PERIOD_DAYS[key]); since = x.toISOString().slice(0, 10); }
  let j = d.findIndex(x => x >= since);
  if (j < 0) j = n - 1;
  const base = j > 0 ? j - 1 : -1;
  return {start: Math.max(base, 0), bi: base >= 0 ? s.i[base] : 1, bp: base >= 0 ? s.p[base] : 0};
}
const following = () => store.get('follows', []);
const isFollowing = n => following().includes(n);
// names are normalised server-side (clean_name in app.py); migrate follows saved under the old spelling
(() => { const H = new Set(['mr', 'mrs', 'ms', 'miss', 'dr', 'hon', 'rep', 'sen', 'honorable', 'md', 'facs', 'phd', 'dds', 'dvm', 'cpa', 'esq']);
  const clean = n => { const o = []; for (const w of n.split(/\s+/)) { const k = w.toLowerCase().replace(/^[.,]+|[.,]+$/g, ''); if (!w || H.has(k)) continue; if (o.length && k === o[o.length - 1].toLowerCase().replace(/^[.,]+|[.,]+$/g, '')) continue; o.push(w); } return o.join(' ') || n; };
  try { const f = following(), g = [...new Set(f.map(clean))]; if (g.join('|') !== f.join('|')) store.set('follows', g); } catch (e) {} })();
function setFollow(n, on) { const f = following().filter(x => x !== n); if (on) f.push(n); store.set('follows', f); if (typeof pushRefresh === 'function') pushRefresh(true); }

async function openPolitician(name) {
  POL.name = name; POL.period = 'ALL'; POL.showAll = false; POL.offset = 0;
  const el = $('#v-pol');
  el.innerHTML = `<div class="phero"><button class="hbtn back" data-back>${I.back}</button></div><div class="pbody"><div class="sk-card" style="height:120px"></div></div>`;
  let d;
  try { d = await api('/api/portfolio?name=' + encodeURIComponent(name)); } catch (e) { el.innerHTML = empty('Politician not found', `<a href="#people">Browse politicians</a>`); return; }
  if (POL.name !== name) return;
  POL.data = d;
  const p = {...d, politician: name};
  const has = d.series && d.series.d.length > 1;
  const fol = isFollowing(name);
  el.innerHTML = `
    <div class="phero">${portrait(name, d.bioguide, 'portrait')}
      <button class="hbtn back" data-back aria-label="Back">${I.back}</button>
      <button class="hbtn bell${fol ? ' on' : ''}" id="bellBtn" aria-label="Follow">${I.bell}</button>
      <button class="hbtn share" id="shareBtn" aria-label="Share">${I.share}</button>
      <div class="nm"><h1>${esc(name)}</h1><div class="sub"><span><i class="pty-${esc(d.party || '')}"></i>${esc(PARTY[d.party] || 'Unknown party')}</span><span>${esc(loc(p))}</span><span>${esc(chamberLbl(d.chamber))}</span></div></div>
    </div>
    <div class="pbody">
      <div class="pv-k">Portfolio Value <span class="est">Estimate</span></div>
      <div class="pv-v" id="pvV">${has ? usd(d.value) : '—'}</div>
      <div class="pv-d" id="pvD">${has ? '' : '<span class="when">No priced stock trades to build a portfolio from.</span>'}</div>
      ${has ? `<div class="chart" id="chart"></div>
      <div class="rtabs" id="rtabs">${['1W', '1M', '3M', 'YTD', '1Y', '5Y', 'ALL'].map(k => `<button data-v="${k}"${k === POL.period ? ' class="on"' : ''}>${k}</button>`).join('')}</div>` : ''}
      <div class="stats">
        <div class="stat"><div class="k">Win Rate</div><div class="v">${d.win_rate != null ? d.win_rate.toFixed(1) + '%' : '—'}</div><div class="f">${d.win_n ? `${num(d.win_n)} trades, ${d.win_days}d later` : 'Needs trades 30+ days old'}</div></div>
        <div class="stat"><div class="k">Expectancy</div><div class="v ${d.edge == null ? '' : d.edge >= 0 ? 'up' : 'dn'}">${d.edge != null ? (d.edge >= 0 ? '+' : '') + d.edge.toFixed(2) + '%' : '—'}</div><div class="f">Avg move their way, ${d.win_days}d</div></div>
        <div class="stat"><div class="k">Avg Delay</div><div class="v">${d.avg_delay != null ? Math.round(d.avg_delay) + ' days' : '—'}</div><div class="f">Trade → disclosure</div></div>
        <div class="stat"><div class="k">Trades</div><div class="v">${num(d.n)}</div><div class="f"><span class="up">${num(d.buys)} buys</span> · <span style="color:var(--sell)">${num(d.sells)} sells</span></div></div>
        <div class="stat"><div class="k">Holdings</div><div class="v">${num(d.n_holdings)}</div><div class="f">Since ${fmtDY(d.first_tx)}</div></div>
      </div>
      ${has ? `<div class="h2s"><h2>If you’d copied ${esc(name.split(' ').slice(-1)[0])}</h2><small>Estimate</small></div><div class="card cpy" id="copySim">${skRows(2)}</div>` : ''}
      ${d.holdings.length ? `<button class="btn mirror-btn" id="mirrorBtn">${I.copy}Mirror portfolio</button>` : ''}
      ${d.holdings.length ? `<div class="h2s"><h2>Current Holdings</h2><small>${num(d.n_holdings)} positions · est.</small></div>
      <div class="card hlist" id="holdings"></div>` : ''}
      <div class="h2s"><h2>Trades</h2><small>Newest disclosed first</small></div>
      <div class="card tlist" id="polTrades">${skRows(4)}</div>
      <button class="btn ghost full" id="polMore" hidden>Show more trades</button>
      <div class="h2s"><h2>Disclosures</h2><small id="filN"></small></div>
      <div class="card flist" id="polFilings">${skRows(2)}</div>
      <p class="note">${I.info}<span>Portfolio value, holdings and returns are <b>estimates</b> rebuilt only from disclosed trades: each trade's range midpoint is turned into shares at that day's Yahoo close, and sells reduce the position. Stock held before ${fmtDY(d.first_tx)} or never disclosed isn't included. Returns are time-weighted, so new money doesn't count as a gain. Not investment advice.${d.politician === 'Donald J. Trump' ? ' The President\'s reports are scanned PDFs read with OCR, so some trades are missing.' : ''}</span></p>
    </div>`;
  if (has) { renderPeriod(); POL.cp = POL.cp || '1Y'; renderCopy(); }
  renderHoldings();
  loadPolTrades();
  loadFilings(name);
  $('#bellBtn').onclick = () => toggleFollow(name);
  $('#shareBtn').onclick = async () => {
    const url = location.href.split('#')[0] + '#p=' + encodeURIComponent(name);
    if (navigator.share) { try { await navigator.share({title: `${name} · The Black House`, url}); } catch (e) { /* cancelled */ } }
    else { await navigator.clipboard.writeText(url).catch(() => {}); toast('Link copied'); }
  };
  if ($('#mirrorBtn')) $('#mirrorBtn').onclick = () => openMirror();
  if (route.after === 'mirror' && d.holdings.length) openMirror();
  if (route.after === 'follow') openFollowSheet(name);
  route.after = null;
  if ($('#rtabs')) $$('#rtabs button').forEach(b => b.onclick = () => { POL.period = b.dataset.v; $$('#rtabs button').forEach(x => x.classList.toggle('on', x === b)); renderPeriod(); });
}
/* ---- copy-trade simulator: the portfolio's time-weighted index vs SPY over the same dates ---- */
let BENCH = null;
const decodePx = px => { const out = []; if (!px) return out; let ms = D(px.d0).getTime(); px.dd.forEach((x, i) => { ms += x * 864e5; out.push([new Date(ms).toISOString().slice(0, 10), px.c[i]]); }); return out; };
const CP_DAYS = {'3M': 91, '1Y': 365, '3Y': 1095, '5Y': 1826, 'ALL': 1e5};
async function renderCopy() {
  const el = $('#copySim'); if (!el) return;
  const name = POL.name, s = POL.data.series, n = s.d.length, last = s.d[n - 1];
  if (!BENCH) { try { BENCH = decodePx((await api('/api/bench')).SPY); } catch (e) { BENCH = []; } }
  if (POL.name !== name || !$('#copySim')) return;
  const k = POL.cp, since = D(last); since.setUTCDate(since.getUTCDate() - CP_DAYS[k]);
  const sIso = since.toISOString().slice(0, 10);
  let j = s.d.findIndex(x => x >= sIso); if (j < 0) j = n - 1;
  const base = j > 0 ? j - 1 : 0, startD = s.d[base], bi = j > 0 ? s.i[base] : 1;
  const amt = 10000, me = amt * s.i[n - 1] / bi;
  const at = d => { let v = null; for (const p of BENCH) { if (p[0] <= d) v = p[1]; else break; } return v; };
  const b0 = at(startD), b1 = BENCH.length ? BENCH[BENCH.length - 1][1] : null, spy = b0 && b1 ? amt * b1 / b0 : null;
  const r1 = (me / amt - 1) * 100, r2 = spy ? (spy / amt - 1) * 100 : null, diff = r2 == null ? null : r1 - r2;
  // two normalised lines
  const idx = []; for (let q = base; q < n; q++) idx.push(q);
  const step = Math.max(1, Math.floor(idx.length / 300)), pick = idx.filter((_, q) => q % step === 0 || q === idx.length - 1);
  const A = pick.map(q => amt * s.i[q] / bi), B = pick.map(q => { const v = at(s.d[q]); return v && b0 ? amt * v / b0 : null; });
  const all = A.concat(B.filter(x => x != null)), mn = Math.min(...all), mx = Math.max(...all), rr = mx - mn || 1, W = 1000, Hh = 140;
  const X = q => pick.length === 1 ? W : q / (pick.length - 1) * W, Y = v => Hh - 8 - (v - mn) / rr * (Hh - 16);
  const path = vals => vals.map((v, q) => v == null ? '' : `${q && vals[q - 1] != null ? 'L' : 'M'}${X(q).toFixed(1)},${Y(v).toFixed(1)}`).join('');
  const before = startD < s.d[0] || j === 0;
  el.innerHTML = `<div class="cp-tabs pills">${Object.keys(CP_DAYS).map(x => `<button data-v="${x}" class="${x === k ? 'on' : ''}">${x}</button>`).join('')}</div>
    <div class="cp-q">$10,000 copied ${before ? 'from their first priced trade' : 'on'} <b>${fmtDY(before ? s.d[0] : startD)}</b> would now be about</div>
    <div class="cp-rows">
      <div class="cp-r"><span class="sw me"></span><span class="l">Copying ${esc(name)}</span><b>${usd(me, 0)}</b><span class="${r1 >= 0 ? 'up' : 'dn'}">${r1 >= 0 ? '+' : ''}${pct(r1)}</span></div>
      <div class="cp-r"><span class="sw spy"></span><span class="l">S&amp;P 500 (SPY)</span><b>${spy ? usd(spy, 0) : '—'}</b><span class="${r2 == null ? '' : r2 >= 0 ? 'up' : 'dn'}">${r2 == null ? '' : (r2 >= 0 ? '+' : '') + pct(r2)}</span></div>
    </div>
    <svg class="cp-ch" viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none"><path d="${path(B)}" class="spy" vector-effect="non-scaling-stroke"/><path d="${path(A)}" class="me" vector-effect="non-scaling-stroke"/></svg>
    ${diff != null ? `<div class="cp-v ${diff >= 0 ? 'up' : 'dn'}">${diff >= 0 ? 'Beat' : 'Trailed'} the S&amp;P 500 by ${Math.abs(diff).toFixed(1)} points</div>` : ''}
    <p class="cp-f">Estimate. Each disclosed trade is copied on its trade date at the estimated price (range midpoint ÷ that day's close), using the same time-weighted return as the chart above. In reality you'd only see trades after disclosure (avg ${POL.data.avg_delay != null ? Math.round(POL.data.avg_delay) : '?'} days later); fees, taxes and dividends are ignored.</p>`;
  $$('#copySim .cp-tabs button').forEach(b => b.onclick = () => { POL.cp = b.dataset.v; renderCopy(); });
}
function headerAt(s, sl, idx) {
  const pnl = s.p[idx] - sl.bp, r = (s.i[idx] / sl.bi - 1) * 100, up = pnl >= 0;
  $('#pvV').textContent = usd(s.v[idx]);
  const label = idx === s.d.length - 1 ? ({'1W': 'Past week', '1M': 'Past month', '3M': 'Past 3 months', 'YTD': 'Year to date', '1Y': 'Past year', '5Y': 'Past 5 years', 'ALL': 'All time'}[POL.period]) : fmtDY(s.d[idx]);
  $('#pvD').innerHTML = `<span>${sgnUsd(pnl)}</span><span class="pct ${r >= 0 ? 'up' : 'dn'}">${r >= 0 ? '▲' : '▼'} ${pct(Math.abs(r))}</span><span class="when">${label}</span>`;
  return up;
}
function renderPeriod() {
  const s = POL.data.series, sl = periodSlice(s, POL.period);
  const n = s.d.length, idx = [];
  for (let k = sl.start; k < n; k++) idx.push(k);
  const step = Math.max(1, Math.floor(idx.length / 600));
  const pick = idx.filter((_, j) => j % step === 0 || j === idx.length - 1);
  const vals = pick.map(k => s.v[k]);
  const up = headerAt(s, sl, n - 1);
  const W = 1000, Hh = 260, mn = Math.min(...vals), mx = Math.max(...vals), rr = mx - mn || mx || 1;
  const X = j => pick.length === 1 ? W : j / (pick.length - 1) * W, Y = v => Hh - 14 - (v - mn) / rr * (Hh - 34);
  const pts = vals.map((v, j) => [X(j), Y(v)]);
  const col = up ? 'var(--up-l)' : 'var(--dn)';
  const ch = $('#chart');
  ch.innerHTML = `<svg viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none"><path d="${smoothPath(pts)}" stroke="${col}" stroke-width="2.2" fill="none" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>
    <span class="cdot" id="cdot" style="left:100%;top:${(pts[pts.length - 1][1] / Hh * 100).toFixed(2)}%;background:${col}"></span><span class="cursor" id="ccur" hidden></span>`;
  const move = e => {
    const r = ch.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const j = Math.round(fx * (pick.length - 1));
    $('#cdot').style.left = (X(j) / W * 100) + '%'; $('#cdot').style.top = (pts[j][1] / Hh * 100) + '%';
    $('#ccur').hidden = false; $('#ccur').style.left = (X(j) / W * 100) + '%';
    headerAt(s, sl, pick[j]);
  };
  const leave = () => { $('#ccur').hidden = true; $('#cdot').style.left = '100%'; $('#cdot').style.top = (pts[pts.length - 1][1] / Hh * 100) + '%'; headerAt(s, sl, n - 1); };
  ch.onpointermove = move; ch.onpointerdown = move; ch.onpointerleave = leave; ch.onpointerup = e => e.pointerType !== 'mouse' && leave();
}
function renderHoldings() {
  const el = $('#holdings'); if (!el) return;
  const H = POL.data.holdings, n = POL.showAll ? Math.min(H.length, 100) : 5;
  el.innerHTML = H.slice(0, n).map(h => `<button class="hrow" data-tick="${esc(h.ticker)}">${logo(h.ticker)}
      <div><div class="tk">${esc(h.ticker)}</div><div class="w">${h.weight.toFixed(2)}%</div></div>
      <div class="r"><div class="val">${usd(h.value)}</div><div class="g ${h.gain_pct == null ? '' : h.gain_pct >= 0 ? 'up' : 'dn'}">${h.gain_pct == null ? '' : (h.gain_pct >= 0 ? '+' : '') + pct(h.gain_pct)}</div></div></button>`).join('')
    + (H.length > 5 ? `<button class="viewall${POL.showAll ? ' open' : ''}" id="viewAll">${POL.showAll ? 'Show less' : 'View All'} ${I.chevd}</button>` : '');
  if ($('#viewAll')) $('#viewAll').onclick = () => { POL.showAll = !POL.showAll; renderHoldings(); };
}
async function loadPolTrades(append = false) {
  const name = POL.name;
  const d = await api(`/api/trades?politician=${encodeURIComponent(name)}&limit=25&offset=${POL.offset}`);
  if (POL.name !== name) return;
  d.trades.forEach(t => trades.set(t.uid, t));
  const html = d.trades.map(t => tradeRow(t, false)).join('');
  if (append) $('#polTrades').insertAdjacentHTML('beforeend', html); else $('#polTrades').innerHTML = html || empty('No trades', '');
  $('#polMore').hidden = POL.offset + 25 >= d.total;
  $('#polMore').onclick = () => { POL.offset += 25; loadPolTrades(true); };
}
async function loadFilings(name) {
  const d = await api('/api/politician?name=' + encodeURIComponent(name)).catch(() => null);
  if (!d || POL.name !== name) return;
  const F2 = d.filings.filter(f => f.url);
  $('#filN').textContent = `${F2.length} filing${F2.length === 1 ? '' : 's'}`;
  $('#polFilings').innerHTML = F2.slice(0, 8).map(f => `<a href="${esc(f.url)}" target="_blank" rel="noopener">${I.doc}<span>${esc(f.status === 'amendment' || /AMENDED/i.test(f.url) ? 'Amended report' : f.source === 'oge' ? (/annual/i.test(f.url) ? 'OGE 278e annual report' : /termination/i.test(f.url) ? 'OGE 278e termination report' : 'OGE 278-T report') : 'Periodic transaction report')}${f.n_tx ? ` · ${f.n_tx} trades` : ''}</span><span class="f">${fmtDY(f.filing_date)}</span></a>`).join('') || empty('No filing links', 'Senate trades link to the eFD search portal.');
}
function toggleFollow(name) {
  const on = !isFollowing(name);
  setFollow(name, on);
  $('#bellBtn').classList.toggle('on', on);
  if (on) openFollowSheet(name); else toast(`Unfollowed ${name}`);
}
async function openFollowSheet(name) {
  const d = POL.data && POL.data.politician === name ? POL.data : null;
  const sub = await pushSub().catch(() => null), on = !!sub && Notification.permission === 'granted';
  openSheet(`<div class="td-head">${avatar(name, d && d.bioguide)}<div><h2 style="font-size:22px">Following ${esc(name)}</h2><div class="an">Saved on this device</div></div></div>
    <div class="lock" style="margin-bottom:16px;padding:18px 14px 20px"><div class="noti"><span class="ic">${I.cap}</span><div style="flex:1;min-width:0"><div class="app"><span>The Black House</span><span>now</span></div><div class="t">${esc(name)} disclosed new trades.</div><div class="s">Tap to see what they bought and sold.</div></div></div></div>
    ${on ? `<p class="prose">You’ll get a notification on this device when ${esc(name)} discloses new trades.${store.get('pushAll', true) ? ' (You also get every new trade; turn that off in Alerts to hear only about people you follow.)' : ''}</p>`
      : `<p class="prose">Turn on notifications to hear about ${esc(name)}’s new trades on this device.</p><button class="sbtn pc-on" id="sheetPushOn" style="height:40px;padding:0 18px">Enable notifications</button>`}`);
  if ($('#sheetPushOn')) $('#sheetPushOn').onclick = async () => { await pushEnable(); closeSheet(); };
}

/* ============ mirror calculator (screenshot 03) ============ */
function openMirror() {
  const d = POL.data; if (!d) return;
  const top = d.holdings.slice(0, 10), tw = top.reduce((a, h) => a + h.weight, 0) || 1;
  const amt0 = store.get('mirrorAmt', 1000);
  openSheet(`<div class="mir-h"><div class="k">Mirror amount</div>
      <div class="mir-amt">$<input id="mirAmt" type="text" inputmode="decimal" value="${amt0.toFixed(2)}" aria-label="Amount in dollars"></div>
      <div class="mir-who">${avatar(d.politician, d.bioguide, 'round')}${esc(d.politician)}</div></div>
    <div class="quick">${[100, 500, 1000, 5000].map(v => `<button data-amt="${v}">$${v.toLocaleString()}</button>`).join('')}</div>
    <div class="h2s" style="margin-top:8px"><h2 style="font-size:18px">Top holdings</h2><small>${top.length} of ${num(d.n_holdings)}</small></div>
    <div id="mirList"></div>
    <div class="infobox">${I.info}<span><b>Hypothetical illustration, not advice.</b> Splits your amount across their ${top.length} largest <i>estimated</i> holdings in proportion to estimated weight. Holdings are rebuilt from disclosed trade ranges and are delayed by up to 45 days. No orders are placed.</span></div>`);
  const fit = () => { const el = $('#mirAmt'); el.style.width = Math.max(3, el.value.length + 0.4) + 'ch'; };
  const draw = () => {
    fit();
    const a = Math.max(0, parseFloat(($('#mirAmt').value || '0').replace(/[^0-9.]/g, '')) || 0);
    store.set('mirrorAmt', a);
    $('#mirList').innerHTML = top.map(h => { const w = h.weight / tw; return `<div class="mrow">${logo(h.ticker)}<div style="min-width:0"><div class="tk">${esc(h.ticker)}</div><div class="hrs">${I.clock}9:30 AM – 4:00 PM ET</div></div><div class="r"><div class="a">${usd(a * w)}</div><div class="w">${(w * 100).toFixed(2)}%</div></div></div>`; }).join('');
  };
  $('#mirAmt').oninput = draw;
  $('#mirAmt').onblur = () => { const a = parseFloat($('#mirAmt').value.replace(/[^0-9.]/g, '')) || 0; $('#mirAmt').value = a.toFixed(2); fit(); };
  $$('[data-amt]').forEach(b => b.onclick = () => { $('#mirAmt').value = (+b.dataset.amt).toFixed(2); draw(); });
  draw();
}

/* ============ sheets ============ */
function openSheet(html) { $('#sheetBody').innerHTML = html; $('#sheet').hidden = false; document.body.style.overflow = 'hidden'; $('.sheet').scrollTop = 0; }
function closeSheet(updateHash = true) {
  if ($('#sheet').hidden) return;
  $('#sheet').hidden = true; document.body.style.overflow = '';
  const h = decodeURIComponent(location.hash.slice(1));
  if (updateHash && (h.startsWith('t=') || h.startsWith('x='))) history.back();
}
function rangeBar(t) {
  const close = t.est_price;
  if (close == null) return `<div class="rng none">${!t.ticker ? (t.asset_type === 'BOND' ? 'Bond, no market price' : 'Not exchange-listed') : 'No price for that day'}</div>`;
  const lo = t.day_low ?? close, hi = t.day_high ?? close;
  const nowT = t.cur_price != null && t.pct_since != null ? close * (1 + t.pct_since / 100) : null;
  const pts = [lo, hi, close].concat(nowT != null ? [nowT] : []);
  let mn = Math.min(...pts), mx = Math.max(...pts);
  const pad = (mx - mn) * 0.08 || close * 0.01; mn -= pad; mx += pad;
  const x = v => ((v - mn) / (mx - mn) * 100).toFixed(2) + '%';
  const dir = t.pct_since != null ? (t.pct_since >= 0 ? 'up' : 'dn') : '';
  return `<div class="rng"><div class="vals"><span><b>${usd(close)}</b>close${t.est_date && t.est_date !== t.tx_date ? ` · ${fmtD(t.est_date)}` : ''}</span>${nowT != null ? `<span>now ${usd(t.cur_price)}</span>` : ''}</div>
    <div class="bar"><span class="day" style="left:${x(lo)};width:calc(${x(hi)} - ${x(lo)})"></span>${nowT != null ? `<span class="link ${dir}" style="left:${x(Math.min(close, nowT))};width:calc(${x(Math.max(close, nowT))} - ${x(Math.min(close, nowT))})"></span><span class="now" style="left:${x(nowT)}"></span>` : ''}<span class="cl" style="left:${x(close)}"></span></div>
    <div class="lh"><span>Day low ${usd(lo)}</span><span>Day high ${usd(hi)}</span></div></div>`;
}
async function openTrade(uid) {
  let t = trades.get(uid);
  if (!t) { try { t = await api('/api/trade?uid=' + encodeURIComponent(uid)); trades.set(uid, t); } catch (e) { location.hash = ''; return; } }
  if (!route.cur) { showView('home'); route.cur = 'home'; loadHome(); }
  const close = t.est_price, lo = t.day_low ?? close, hi = t.day_high ?? close;
  const sh = close != null && t.amount_low ? [t.amount_low / hi, (t.amount_high || t.amount_low) / lo] : null;
  const k = t.pct_since != null ? 1 + t.pct_since / 100 : null;
  openSheet(`<div class="td-head">${logo(t.ticker, t.asset_type)}<div style="min-width:0"><h2>${esc(t.ticker || cleanAsset(t).slice(0, 34))}</h2><div class="an">${esc(t.ticker ? assetName(t) : t.tx_type)}</div></div><div style="margin-left:auto">${sideTag(t)}</div></div>
    <button class="who" data-pol="${esc(t.politician)}">${avatar(t.politician, t.bioguide)}<span><div class="nm">${esc(t.politician)}</div><div class="mt">${esc(metaShort(t))}</div></span></button>
    ${overlap(t) ? `<div class="card ovcard">${ovExplain(t, overlap(t))}</div>` : ''}
    <div class="card" style="padding:16px;margin-top:16px"><div class="mute" style="font-size:13px">Estimated price on ${fmtDY(t.tx_date)}</div>${rangeBar(t)}</div>
    <div class="kv">
      <div><div class="k">Amount disclosed</div><div class="v">${esc(amtShort(t))}</div><div class="f">Midpoint ${money(mid(t))}</div></div>
      <div><div class="k">Implied shares</div><div class="v">${sh ? `${num(sh[0])}–${num(sh[1])}` : '—'}</div><div class="f">${sh ? 'Range ÷ day high / low' : 'Needs a trade-day price'}</div></div>
      <div><div class="k">Since the trade</div><div class="v ${t.pct_since == null ? '' : t.pct_since >= 0 ? 'up' : 'dn'}">${t.pct_since != null ? (t.pct_since >= 0 ? '+' : '') + t.pct_since.toFixed(2) + '%' : '—'}</div><div class="f">${t.cur_price != null ? `Now ${usd(t.cur_price)}` : ''}</div></div>
      <div><div class="k">Same shares today</div><div class="v">${k && t.amount_low ? `${money(t.amount_low * k)}–${money((t.amount_high || t.amount_low) * k)}` : '—'}</div><div class="f">Estimate</div></div>
      <div><div class="k">Traded</div><div class="v">${fmtDY(t.tx_date)}</div><div class="f">${ago(t.tx_date)}</div></div>
      <div><div class="k">Disclosed</div><div class="v">${fmtDY(t.disclosure_date)}</div><div class="f">${t.lag_days != null ? `${t.lag_days} days later${t.lag_days > 45 ? ' (late)' : ''}` : ''}</div></div>
      <div><div class="k">Owner</div><div class="v">${esc(t.owner || 'Self')}</div><div class="f">${esc(t.tx_type || '')}</div></div>
      <div><div class="k">Day open / close</div><div class="v">${t.day_open != null ? `${usd(t.day_open)} / ${usd(close)}` : '—'}</div><div class="f">Yahoo daily bar</div></div>
    </div>
    ${t.ticker ? '' : `<p class="note">${esc(cleanAsset(t))}</p>`}
    ${t.description ? `<p class="note">${esc(t.description)}</p>` : ''}
    <div class="infobox">${I.info}<span>Prices are estimates from Yahoo Finance daily data for the trade date: any fill that day was between the low and high, and the close is our single best guess. Disclosures only give dollar ranges.</span></div>
    <div class="btns"><a class="btn" href="${esc(t.url || '#')}" target="_blank" rel="noopener">${I.doc}Original filing</a>${t.ticker ? `<button class="btn ghost" data-tick="${esc(t.ticker)}">All ${esc(t.ticker)} trades</button>` : ''}</div>`);
}
/* ============ stock page ============ */
const ST = {t: null, s: null, rows: [], total: 0, range: '1Y', pts: [], shown: 15, mb: {}};
const openTicker = tk => { location.hash = 't=' + encodeURIComponent(tk); };
async function openStock(tk) {
  tk = decodeURIComponent(tk).toUpperCase(); ST.t = tk; ST.shown = 15; ST.range = '1Y';
  const el = $('#v-stock'), enc = encodeURIComponent(tk);
  el.innerHTML = `<div class="mbp-top"><button class="ib" data-back aria-label="Back">${I.back}</button></div>
    <div class="st-head">${logo(tk)}<div><h1>${esc(tk)}</h1><div class="mute" id="stName">Loading…</div></div></div><div class="sk-card" style="height:260px;margin-top:16px"></div>`;
  let s, d;
  try { [s, d] = await Promise.all([api('/api/stock?ticker=' + enc), api(`/api/trades?ticker=${enc}&limit=2000`)]); }
  catch (e) { el.innerHTML += empty('Could not load', esc(String(e.message || e))); return; }
  if (ST.t !== tk) return;
  d.trades.forEach(t => trades.set(t.uid, t));
  ST.s = s; ST.rows = d.trades; ST.total = d.total; ST.pts = [];
  if (s.px) { let ms = D(s.px.d0).getTime(); s.px.dd.forEach((x, i) => { ms += x * 864e5; ST.pts.push([new Date(ms).toISOString().slice(0, 10), s.px.c[i]]); }); }
  ST.mb = {};
  await Promise.all(['90', '365'].map(async w => { try { const m = await api(`/api/most_bought?days=${w}&etf=1`); const i = m.items.findIndex(x => x.ticker === tk); if (i >= 0) ST.mb[w] = {rank: i + 1, ...m.items[i]}; } catch (e) {} }));
  if (ST.t === tk) renderStock();
}
const ST_RANGES = {'3M': 91, '1Y': 365, '3Y': 1095, 'ALL': 1e5};
function stRange() {
  const P = ST.pts; if (!P.length) return [];
  const since = daysAgoISO(ST_RANGES[ST.range]);
  const r = P.filter(p => p[0] >= since);
  return r.length > 1 ? r : P.slice(-2);
}
function stockChart(w) {
  const P = stRange(), h = 230, pt = 14, pb = 24, pl = 4, pr = 46;
  if (P.length < 2) return `<div class="empty"><b>No price history</b>Yahoo has no daily prices for this ticker.</div>`;
  const t0 = D(P[0][0]).getTime(), t1 = D(P[P.length - 1][0]).getTime();
  const lo = Math.min(...P.map(p => p[1])), hi = Math.max(...P.map(p => p[1])), pad = (hi - lo) * 0.08 || hi * 0.05;
  const X = d => pl + (D(d).getTime() - t0) / Math.max(1, t1 - t0) * (w - pl - pr), Y = v => pt + (1 - (v - lo + pad) / (hi - lo + 2 * pad)) * (h - pt - pb);
  const up = P[P.length - 1][1] >= P[0][1], col = up ? 'var(--up)' : 'var(--dn)';
  const line = P.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('');
  const area = `${line}L${X(P[P.length - 1][0]).toFixed(1)},${h - pb}L${X(P[0][0]).toFixed(1)},${h - pb}Z`;
  const idx = new Map(P.map(p => [p[0], p[1]]));
  const near = d => { if (idx.has(d)) return idx.get(d); let best = null; for (const p of P) { if (p[0] <= d) best = p[1]; else break; } return best ?? P[0][1]; };
  const g = new Map();
  ST.rows.forEach(t => { if (!t.tx_date || t.tx_date < P[0][0] || t.tx_date > P[P.length - 1][0] || (t.side !== 'buy' && t.side !== 'sell')) return;
    const k = t.tx_date + '|' + t.side; if (!g.has(k)) g.set(k, {d: t.tx_date, side: t.side, rows: []}); g.get(k).rows.push(t); });
  ST.groups = [...g.values()].sort((a, b) => a.d < b.d ? -1 : 1);
  const mk = ST.groups.map((m, i) => { const v = m.rows[0].est_price || near(m.d), r = 4.5 + Math.min(4, Math.log2(m.rows.length));
    return `<circle class="mk ${m.side}" data-mk="${i}" cx="${X(m.d).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="${r.toFixed(1)}"/>`; }).join('');
  const ticks = [0, 0.33, 0.66, 1].map(f => { const t = new Date(t0 + f * (t1 - t0)), iso = t.toISOString().slice(0, 10);
    return `<text x="${(pl + f * (w - pl - pr)).toFixed(1)}" y="${h - 6}" text-anchor="${f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}">${ST.range === '3M' ? fmtD(iso) : D(iso).toLocaleDateString('en-US', {month: 'short', year: '2-digit', timeZone: 'UTC'})}</text>`; }).join('');
  const yl = [hi, (hi + lo) / 2, lo].map(v => `<text x="${w - 2}" y="${(Y(v) + 4).toFixed(1)}" text-anchor="end">${usd(v, v >= 1000 ? 0 : 2)}</text><line x1="${pl}" x2="${w - pr + 4}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/>`).join('');
  return `<svg class="stc" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><defs><linearGradient id="stg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${up ? '#22c55e' : '#ef4444'}" stop-opacity=".22"/><stop offset="1" stop-color="${up ? '#22c55e' : '#ef4444'}" stop-opacity="0"/></linearGradient></defs>
    <g class="grid">${yl}</g><path d="${area}" fill="url(#stg)"/><path d="${line}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>${mk}<g class="ax">${ticks}</g></svg>`;
}
function stockPop(i, pop = '#stPop') {
  const m = ST.groups[i]; if (!m) return;
  const rows = m.rows.slice(0, 6);
  $(pop).innerHTML = `<div class="sp-h"><span class="side ${m.side}">${m.side === 'buy' ? 'Bought' : 'Sold'}</span> ${fmtDY(m.d)}${m.rows.length > 1 ? ` · ${m.rows.length} trades` : ''}<button class="sp-x" aria-label="Close">×</button></div>`
    + rows.map(t => `<button class="sp-r" data-trade="${esc(t.uid)}">${avatar(t.politician, t.bioguide, 'round')}<span class="n">${esc(t.politician)}</span><span class="a">${amtShort(t)}</span></button>`).join('')
    + (m.rows.length > 6 ? `<div class="sp-more">+${m.rows.length - 6} more in the list below</div>` : '');
  $(pop).hidden = false;
  $(pop + ' .sp-x').onclick = () => { $(pop).hidden = true; };
}
const STAR = on => `<svg viewBox="0 0 24 24" width="22" height="22" style="fill:${on ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.25 4.1 1 5.85L12 16.9l-5.25 2.75 1-5.85L3.5 9.7l5.9-.9z"/></svg>`;
const watching = () => store.get('watch', []);
function setWatch(tk, on) {
  const w = watching().filter(x => x !== tk); if (on) w.unshift(tk);
  store.set('watch', w); pushRefresh(true);
  toast(on ? `Watching ${tk}` : `Removed ${tk} from watchlist`);
}
function renderStock() {
  const s = ST.s, tk = ST.t, R = ST.rows, t0 = R[0] || {};
  const name = t0.company || cleanAsset(t0) || '', P = stRange(), cur = t0.cur_price ?? (ST.pts.length ? ST.pts[ST.pts.length - 1][1] : null);
  const ch = P.length > 1 ? (P[P.length - 1][1] / P[0][1] - 1) * 100 : null;
  const yr = daysAgoISO(365), R1 = R.filter(t => (t.tx_date || '') >= yr);
  const buyers = new Set(R1.filter(t => t.side === 'buy').map(t => t.politician)).size, sellers = new Set(R1.filter(t => t.side === 'sell').map(t => t.politician)).size;
  const H = s.holders || [], hv = H.reduce((a, h) => a + h.value, 0);
  const mb = w => ST.mb[w] ? `<b>#${ST.mb[w].rank}</b><span>${ST.mb[w].n_pols} politician${ST.mb[w].n_pols === 1 ? '' : 's'} · ${ST.mb[w].n_buys} buys</span>` : `<b>—</b><span>not bought</span>`;
  $('#v-stock').innerHTML = `<div class="mbp-top"><button class="ib" data-back aria-label="Back">${I.back}</button></div>
    <div class="st-head">${logo(tk)}<div class="st-t"><h1>${esc(tk)}</h1><div class="mute">${esc(name)}</div></div><button class="st-star ${watching().includes(tk) ? 'on' : ''}" id="stStar" aria-label="Watch ${esc(tk)}">${STAR(watching().includes(tk))}<span>${watching().includes(tk) ? 'Watching' : 'Watch'}</span></button></div>
    <div class="st-px"><b>${cur != null ? usd(cur) : '—'}</b>${ch != null ? `<span class="${ch >= 0 ? 'up' : 'dn'}">${ch >= 0 ? '▲' : '▼'} ${Math.abs(ch).toFixed(2)}% <small class="mute">${ST.range === 'ALL' ? 'all' : ST.range}</small></span>` : ''}</div>
    <div class="card st-chart"><div id="stChart"></div><div class="st-pop card" id="stPop" hidden></div>
      <div class="st-leg"><span><i class="b"></i>Politician buy</span><span><i class="s"></i>Sell</span><span class="mute">Tap a dot</span></div></div>
    <div class="pills st-rng" id="stRange">${Object.keys(ST_RANGES).filter(k => k !== 'EV').map(k => `<button data-v="${k}" class="${k === ST.range ? 'on' : ''}">${k}</button>`).join('')}</div>
    <div class="st-stats">
      <div class="card"><div class="k">Most bought 90D</div>${mb('90')}</div>
      <div class="card"><div class="k">Most bought 1Y</div>${mb('365')}</div>
      <div class="card"><div class="k">Trades · last 1Y</div><b>${num(R1.length)}</b><span>${buyers} buying · ${sellers} selling</span></div>
      <div class="card"><div class="k">Est. held by</div><b>${H.length}</b><span>${H.length ? money(hv) + ' est.' : 'nobody (from disclosures)'}</span></div>
    </div>
    <div class="sec-h"><h2>Estimated holders</h2><small class="mute">${H.length}</small></div>
    <div class="card tlist">${H.length ? H.slice(0, 12).map(h => `<button class="hrow" data-pol="${esc(h.politician)}">${avatar(h.politician, h.bioguide, 'round')}
      <div><div class="tk" style="font-size:15px">${esc(h.politician)}</div><div class="w">${esc(h.party || '')}${h.chamber ? ' · ' + esc(h.chamber) : ''} · ${num(h.shares)} sh</div></div>
      <div class="r"><div class="val">${money(h.value)}</div><div class="g ${h.gain_pct == null ? '' : h.gain_pct >= 0 ? 'up' : 'dn'}">${h.gain_pct == null ? '' : (h.gain_pct >= 0 ? '+' : '') + pct(h.gain_pct)}</div></div></button>`).join('')
      : empty('No estimated holders', 'Nobody holds it according to the disclosed trades.')}</div>
    <div class="sec-h"><h2>Recent trades</h2><small class="mute">${num(ST.total)}</small></div>
    <div class="card tlist" id="stTrades">${R.slice(0, ST.shown).map(t => tradeRow(t)).join('') || empty('No trades', '')}</div>
    ${R.length > ST.shown ? `<button class="viewall more-btn" id="stMore">See more trades</button>` : ''}
    <p class="fine">Prices are Yahoo Finance daily closes. Dots are politicians' trades by trade date at the estimated price; holdings are estimates rebuilt from disclosed ranges.</p>`;
  const draw = () => { const el = $('#stChart'); if (el) el.innerHTML = stockChart(Math.max(280, el.clientWidth)); };
  draw();
  $('#stChart').onclick = e => { const c = e.target.closest('[data-mk]'); if (c) stockPop(+c.dataset.mk); };
  $$('#stRange button').forEach(b => b.onclick = () => { ST.range = b.dataset.v; renderStock(); });
  if ($('#stMore')) $('#stMore').onclick = () => { ST.shown += 30; renderStock(); };
  $('#stStar').onclick = () => { setWatch(tk, !watching().includes(tk)); renderStock(); };
}
addEventListener('resize', () => { if (route.cur === 'stock' && ST.s && $('#stChart')) $('#stChart').innerHTML = stockChart(Math.max(280, $('#stChart').clientWidth)); });

/* ============ alerts (screenshot 06) ============ */
/* ============ native Web Push (see webpush.py) ============ */
const PUSH_KEY = 'BFR_8mhNgGoPpD-5cQIyJmoyC5dCsW3gk38_4cUh0h9MJhxZ7_bn9Hj3uwKVALUsrX1j80doKWHMJmZ3cVivd9Y';
const PUSH_TOPIC = 'https://ntfy.sh/bh-subs-0ddc01105a955b4f';
const pushOK = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const b64u = s => { const p = '='.repeat((4 - s.length % 4) % 4), b = atob((s + p).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(b, c => c.charCodeAt(0)); };
async function pushSub() { if (!pushOK()) return null; const r = await navigator.serviceWorker.getRegistration(); return r ? r.pushManager.getSubscription() : null; }
async function pushPublish(sub, off) {
  const body = {v: 1, sub: sub.toJSON(), all: store.get('pushAll', true), follows: following(), watch: store.get('watch', []), unusual: store.get('pushUnusual', true), off: !!off};
  const r = await fetch(PUSH_TOPIC, {method: 'POST', body: JSON.stringify(body)});
  if (!r.ok) throw new Error('register ' + r.status);
  store.set('pushPub', Date.now());
}
async function pushEnable() {
  if (!pushOK()) return toast('This browser can’t receive notifications');
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return toast('Install the app from wajeehk.github.io/congress-trades first');
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') { toast('Notifications are blocked. Allow them in site settings.'); renderAlerts(); return; }
  try {
    const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: b64u(PUSH_KEY)});
    await pushPublish(sub);
    toast('Notifications on');
  } catch (e) { toast('Could not enable: ' + (e.message || e)); }
  renderAlerts();
}
async function pushDisable() {
  const sub = await pushSub();
  if (sub) { try { await pushPublish(sub, true); } catch (e) {} await sub.unsubscribe(); }
  toast('Notifications off'); renderAlerts();
}
async function pushRefresh(force) {  // keep the server-side list current (follows changed, or daily heartbeat)
  try { const sub = await pushSub(); if (sub && Notification.permission === 'granted' && (force || Date.now() - store.get('pushPub', 0) > 20 * 3600e3)) await pushPublish(sub); } catch (e) {}
}
async function pushCard() {
  if (!pushOK()) return `<div class="card pushcard"><div class="pc-t"><b>Phone notifications</b><p>This browser can’t receive web notifications. On iPhone you need iOS 16.4+ and must add the app to your Home Screen first.</p></div></div>`;
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return `<div class="card pushcard"><div class="pc-t"><b>Phone notifications</b><p>Open <a href="https://wajeehk.github.io/congress-trades/" style="text-decoration:underline">wajeehk.github.io/congress-trades</a> and install it to get notifications.</p></div></div>`;
  const sub = await reg.pushManager.getSubscription(), perm = Notification.permission, on = !!sub && perm === 'granted', all = store.get('pushAll', true), n = following().length;
  if (!on) return `<div class="card pushcard"><div class="pc-t"><b>Phone notifications</b><p>${perm === 'denied' ? 'Notifications are blocked for this site. Allow them in your browser’s site settings, then tap Enable.' : 'Get a notification on this device the moment new trades are disclosed. No extra app needed.'}</p></div><button class="sbtn pc-on" id="pushOn">Enable notifications</button></div>`;
  return `<div class="card pushcard on"><div class="pc-t"><b>Notifications are on</b><p>${all ? 'Every new trade' : (n || watching().length) ? `Only ${[n ? `the ${n} ${n === 1 ? 'person' : 'people'} you follow` : '', watching().length ? `trades in your ${watching().length} watched ticker${watching().length === 1 ? '' : 's'}` : ''].filter(Boolean).join(' and ')}` : 'Nothing yet: follow someone, watch a stock or turn on all trades'} · this device</p></div>
    <label class="pc-row"><span>All new trades</span><input type="checkbox" id="pushAll" ${all ? 'checked' : ''}></label>
    <label class="pc-row"><span>Unusual activity<small class="mute">Clusters of 3+ buyers and $250K+ trades</small></span><input type="checkbox" id="pushUnusual" ${store.get('pushUnusual', true) ? 'checked' : ''}></label>
    <div class="pc-row"><span>People you follow</span><span class="mute">${n} ${n === 1 ? 'person' : 'people'} · tap the bell on a politician</span></div>
    <div class="pc-row"><span>Watchlist</span><span class="mute">${watching().length} ticker${watching().length === 1 ? '' : 's'} · tap the star on a stock</span></div>
    <div class="pc-btns"><button class="chip-btn" id="pushOff">Turn off</button></div></div>`;
}
async function renderAlerts() {
  const s = statusData || {};
  const fol = following();
  const pfs = await portfolios();
  const now = new Date();
  const newest = (s.sources || []).map(x => x.newest_disclosure).sort().pop();
  const by = c => (s.sources || []).filter(x => x.chamber === c).reduce((a, x) => a + x.n, 0);
  const sample = fol[0] || 'Nancy Pelosi';
  $('#v-alerts').innerHTML = `
    <div class="page-h"><div class="eyebrow">Instant alerts</div><h1>Never miss<br>a trade.</h1></div>
    <div class="lock"><div class="time">${now.toLocaleDateString('en-US', {weekday: 'long', month: 'long', day: 'numeric'})}</div>
      <div class="clock">${now.toLocaleTimeString('en-US', {hour: 'numeric', minute: '2-digit', hour12: false})}</div>
      <div class="noti"><span class="ic">${I.cap}</span><div style="flex:1;min-width:0"><div class="app"><span>The Black House</span><span>now</span></div><div class="t">${esc(sample)} disclosed new trades.</div><div class="s">Tap to see what they bought and sold.</div></div></div></div>
    <div class="h2s" style="margin-top:8px"><h2>Notifications</h2></div>${await pushCard()}
    <div class="h2s"><h2>Following</h2><small>${fol.length} ${fol.length === 1 ? 'person' : 'people'}</small></div>
    <div class="card">${fol.length ? fol.map(n => { const p = pfs.get(n) || {}; return `<div class="frow">${avatar(n, p.bioguide)}<div class="t"><b>${esc(n)}</b><small class="mute">${esc(p.party ? metaShort(p) : '')}</small></div><button class="sbtn ghost" data-unfollow="${esc(n)}">Remove</button></div>`; }).join('')
      : `<div class="empty"><b>You're not following anyone yet</b>Open a politician and tap the ${I.bell.replace('<svg', '<svg style="width:15px;height:15px;vertical-align:-2px"')} bell.</div>`}</div>
    <div class="h2s"><h2>Watchlist</h2><small>${watching().length} ticker${watching().length === 1 ? '' : 's'}</small></div>
    <div class="card">${watching().length ? watching().map(t => `<div class="frow wrow" data-tick="${esc(t)}">${logo(t)}<div class="t"><b>${esc(t)}</b><small class="mute">Alert on any politician trade</small></div><button class="sbtn ghost" data-unwatch="${esc(t)}">Remove</button></div>`).join('')
      : `<div class="empty"><b>No watched stocks yet</b>Open a stock and tap ${STAR(false).replace('<svg', '<svg style="width:15px;height:15px;vertical-align:-2px"')} Watch to get notified whenever a politician trades it.</div>`}</div>
    <div class="h2s"><h2>How it works</h2></div>
    <div class="steps">
      <div class="step card"><div><b>Turn on notifications</b><p>Tap Enable notifications above and allow them. Works in the installed app on Android and desktop, and on iPhone (iOS 16.4+) once it’s added to your Home Screen.</p></div></div>
      <div class="step card"><div><b>Choose what you hear about</b><p>Every new trade, or only the people you follow and the stocks you watch: tap the bell on a politician or the star on a stock.</p></div></div>
      <div class="step card"><div><b>Get “Name disclosed new trades.”</b><p>Filings are checked every hour. New trades arrive as one notification with the tickers and amounts; tap it to open their page.</p></div></div>
    </div>
    <div class="h2s"><h2>Data</h2><small>Checked ${s.last_refresh ? fmtUKlong(s.last_refresh) : '—'}</small></div>
    <div class="card prose" style="padding:4px 18px 18px">
      <p><b>${by('House').toLocaleString()}</b> House trades from official <a href="https://disclosures-clerk.house.gov/FinancialDisclosure" target="_blank" rel="noopener">House Clerk</a> filings, <b>${by('Senate').toLocaleString()}</b> Senate trades from the Senate's own <a href="https://efdsearch.senate.gov/search/" target="_blank" rel="noopener">eFD</a> reports (plus <a href="https://www.bargo.ai/free-apis/congress" target="_blank" rel="noopener">Bargo</a> for the newest), and <b>${by('Executive').toLocaleString()}</b> trades from <a href="https://extapps2.oge.gov/201/Presiden.nsf/President%20and%20Vice%20President%20Index?OpenView&Count=1000" target="_blank" rel="noopener">OGE reports</a> of the President, Vice President and Cabinet. Scanned paper filings are read with OCR. Newest filing ${fmtDY(newest)}.</p>
      <p>Prices come from Yahoo Finance daily data and photos from the public-domain congress-legislators project. Politicians have up to 45 days to disclose, so trades appear when they're filed, not when they're made.</p>
      <p><b>How estimates work.</b> Each disclosed amount range becomes its midpoint, which is turned into shares at that day's close. Buys add to a position and sells reduce it (a full sale closes it). Portfolio value is those shares at today's price. Returns are time-weighted, so new money doesn't count as a gain. Win rate is the share of trades where the price moved their way within 30 days. Only disclosed trades count, so these are rough estimates, not advice.</p>
    </div>`;
  $$('[data-unfollow]').forEach(b => b.onclick = () => { setFollow(b.dataset.unfollow, false); renderAlerts(); });
  $$('[data-unwatch]').forEach(b => b.onclick = e => { e.stopPropagation(); setWatch(b.dataset.unwatch, false); renderAlerts(); });
  if ($('#pushOn')) $('#pushOn').onclick = pushEnable;
  if ($('#pushOff')) $('#pushOff').onclick = pushDisable;
  if ($('#pushAll')) $('#pushAll').onchange = e => { store.set('pushAll', e.target.checked); pushRefresh(true); renderAlerts(); };
  if ($('#pushUnusual')) $('#pushUnusual').onchange = e => { store.set('pushUnusual', e.target.checked); pushRefresh(true); };

}

/* ============ events ============ */
document.addEventListener('click', e => {
  const a = e.target.closest('a[href^="http"]'); if (a) return;
  const cp = e.target.closest('[data-copy]'); if (cp) { navigator.clipboard.writeText(cp.dataset.copy).then(() => toast('Copied')).catch(() => toast(cp.dataset.copy)); return; }
  if (e.target.closest('[data-back]')) { if (history.length > 1 && document.referrer !== undefined && route.prev) history.back(); else location.hash = baseView === 'home' ? '' : baseView; return; }
  if (e.target.closest('#clrTick')) { F.ticker = null; loadFeed(); return; }
  const un = e.target.closest('[data-un]'); if (un) { location.hash = 'unusual=' + un.dataset.un; return; }
  const pol = e.target.closest('[data-pol]'); if (pol) { closeSheet(false); location.hash = 'p=' + encodeURIComponent(pol.dataset.pol); return; }
  const tk = e.target.closest('[data-tick]'); if (tk) { location.hash = 't=' + encodeURIComponent(tk.dataset.tick); return; }
  const ov = e.target.closest('[data-ov]'); if (ov) { openOverlap(ov.dataset.ov); return; }
  const tr = e.target.closest('[data-trade]'); if (tr) { location.hash = 'x=' + encodeURIComponent(tr.dataset.trade); return; }
  if (e.target.id === 'sheet' || e.target.closest('#sheetX')) closeSheet();
});
addEventListener('hashchange', () => { route.prev = true; });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeSheet();
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); location.hash = 'trades'; setTimeout(() => $('#q').focus(), 50); }
});
function pills(id, cb) { $$(`#${id} button`).forEach(b => b.onclick = () => { $$(`#${id} button`).forEach(x => x.classList.toggle('on', x === b)); cb(b.dataset.v); }); }
pills('rangeSeg', v => { F.range = v; $('#custom').hidden = v !== 'custom'; if (v !== 'custom') { loadFeed(); loadKpis(); } });
pills('sideSeg', v => { F.side = v; loadFeed(); });
pills('chamberSeg', v => { F.chamber = v; loadFeed(); loadKpis(); });
pills('polSort', v => { P.sort = v; P.dir = -1; loadPeople(); });
pills('polPeriod', v => { P.period = v; loadPeople(); });
pills('polChamber', v => { P.chamber = v; loadPeople(); });
$('#polDir').onclick = () => { P.dir *= -1; loadPeople(); };
let deb;
$('#q').addEventListener('input', () => { clearTimeout(deb); deb = setTimeout(() => loadFeed(), 250); });
let pdeb;
$('#pq').addEventListener('input', () => { clearTimeout(pdeb); pdeb = setTimeout(() => loadPeople(), 120); });
$$('.search').forEach(l => { const inp = l.querySelector('input'), x = l.querySelector('.sx'); if (!inp || !x) return;
  const upd = () => l.classList.toggle('has', !!inp.value); inp.addEventListener('input', upd); upd();
  x.onclick = e => { e.preventDefault(); inp.value = ''; upd(); inp.dispatchEvent(new Event('input')); inp.focus(); }; });
$('#party').onchange = () => { loadFeed(); loadKpis(); };
['#dateField', '#sort', '#assetSel'].forEach(s => $(s).onchange = () => loadFeed());
['#from', '#to'].forEach(s => $(s).onchange = () => { loadFeed(); loadKpis(); });
$('#reset').onclick = () => {
  ['#q', '#from', '#to', '#party', '#assetSel'].forEach(s => $(s).value = ''); $$('.search').forEach(l => l.classList.remove('has'));
  $('#dateField').value = 'disclosure_date'; $('#sort').value = 'disclosure_date';
  F.ticker = null; F.side = ''; F.chamber = ''; F.range = '90'; $('#custom').hidden = true;
  [['rangeSeg', '90'], ['sideSeg', ''], ['chamberSeg', '']].forEach(([id, v]) => $$(`#${id} button`).forEach(b => b.classList.toggle('on', b.dataset.v === v)));
  loadFeed(); loadKpis();
};
$('#more').onclick = () => { F.offset += F.PAGE; $('#more').textContent = 'Loading…'; loadFeed(true).then(() => $('#more').textContent = 'Show more trades'); };

/* ============ boot ============ */
const qp = new URLSearchParams(location.search);
if (qp.get('chamber')) { F.chamber = qp.get('chamber'); $$('#chamberSeg button').forEach(b => b.classList.toggle('on', b.dataset.v === F.chamber)); }
loadStatus();
loadCtx();
route();
setInterval(loadStatus, 5 * 60e3);
document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && loadStatus());

setTimeout(() => pushRefresh(false), 4000);
if ('serviceWorker' in navigator) navigator.serviceWorker.addEventListener('message', e => { if (e.data && e.data.type === 'push') { window.__lastPush = e.data; loadStatus(); } });
