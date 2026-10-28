'use strict';
/* Static data layer for the GitHub Pages build: answers the same /api/* calls the live server does,
   from pre-generated JSON in data/, filtering and sorting in the browser. */
(function () {
  const cache = {};
  const get = (path, fresh) => {
    if (!cache[path] || fresh) cache[path] = fetch(path, {cache: fresh ? 'no-cache' : 'default'}).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
    return cache[path];
  };
  const meta = () => get('data/meta.json');
  const v = async () => (await meta()).build;
  const unpack = o => o.rows.map(r => { const t = {}; o.cols.forEach((k, i) => { t[k] = r[i]; }); return t; });
  const memo = {};
  const once = (k, f) => memo[k] || (memo[k] = f().catch(e => { delete memo[k]; throw e; }));
  const recent = () => once('recent', async () => unpack(await get(`data/trades-recent.json?v=${await v()}`)));
  const all = () => once('all', async () => unpack(await get(`data/trades-all.json?v=${await v()}`)));
  const slug = n => n.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const pol = name => once('p:' + name, async () => { const d = await get(`data/p/${slug(name)}.json?v=${await v()}`); d.rows = unpack(d.trades); return d; });
  const mid = t => ((t.amount_low || 0) + (t.amount_high || t.amount_low || 0)) / 2;
  const cmp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const nz = x => x == null ? '' : x;
  const SORTS = {
    disclosure_date: (a, b) => cmp(nz(b.disclosure_date), nz(a.disclosure_date)) || cmp(nz(b.first_seen), nz(a.first_seen)) || cmp(nz(b.tx_date), nz(a.tx_date)) || cmp(a.uid, b.uid),
    tx_date: (a, b) => cmp(nz(b.tx_date), nz(a.tx_date)) || cmp(nz(b.disclosure_date), nz(a.disclosure_date)) || cmp(a.uid, b.uid),
    amount: (a, b) => cmp(a.amount_low == null, b.amount_low == null) || mid(b) - mid(a) || cmp(nz(b.disclosure_date), nz(a.disclosure_date)) || cmp(a.uid, b.uid),
    amount_asc: (a, b) => cmp(a.amount_low == null, b.amount_low == null) || mid(a) - mid(b) || cmp(nz(b.disclosure_date), nz(a.disclosure_date)) || cmp(a.uid, b.uid),
    tx_oldest: (a, b) => cmp(nz(a.tx_date), nz(b.tx_date)) || cmp(a.uid, b.uid),
    oldest: (a, b) => cmp(nz(a.disclosure_date), nz(b.disclosure_date)) || cmp(nz(a.tx_date), nz(b.tx_date)) || cmp(a.uid, b.uid),
    move: (a, b) => cmp(a.pct_since == null, b.pct_since == null) || Math.abs(b.pct_since || 0) - Math.abs(a.pct_since || 0) || cmp(nz(b.disclosure_date), nz(a.disclosure_date)) || cmp(a.uid, b.uid),
  };
  const isStock = t => t.ticker && (!t.asset_type || t.asset_type === 'ST' || t.asset_type === 'EF');
  function where(rows, p) {
    const match = window.BHSearch ? window.BHSearch.compile(p.get('q') || '') : () => true;
    const df = p.get('date_field') === 'tx_date' ? 'tx_date' : 'disclosure_date';
    const from = p.get('date_from'), to = p.get('date_to');
    const f = {politician: p.get('politician'), ticker: (p.get('ticker') || '').toUpperCase(), chamber: p.get('chamber'), party: p.get('party'), side: p.get('side'), asset: p.get('asset')};
    return rows.filter(t =>
      match(t) &&
      (!f.politician || t.politician === f.politician) && (!f.ticker || (t.ticker || '').toUpperCase() === f.ticker) &&
      (!f.chamber || t.chamber === f.chamber) && (!f.party || t.party === f.party) && (!f.side || t.side === f.side) &&
      (!from || (t[df] && t[df] >= from)) && (!to || (t[df] && t[df] <= to)) &&
      (f.asset !== 'stock' || isStock(t)) && (f.asset !== 'other' || !isStock(t)));
  }
  async function source(p) {
    if (p.get('politician')) return (await pol(p.get('politician'))).rows;
    const m = await meta(), from = p.get('date_from');
    return from && from >= m.recent_from ? recent() : all();
  }
  const dayISO = n => { const d = new Date(); d.setUTCDate(d.getUTCDate() - n); return d.toISOString().slice(0, 10); };
  function group(rows, key, init, add) { const m = new Map(); rows.forEach(t => { const k = key(t); if (k == null) return; if (!m.has(k)) m.set(k, init(t)); add(m.get(k), t); }); return [...m.values()]; }

  const routes = {
    async status() {
      const old = cache['data/meta.json'] ? (await cache['data/meta.json'].catch(() => ({}))).build : null;
      const m = await fetch('data/meta.json', {cache: 'no-cache'}).then(r => r.json());
      if (old && m.build !== old) { Object.keys(memo).forEach(k => delete memo[k]); Object.keys(cache).forEach(k => delete cache[k]); }
      cache['data/meta.json'] = Promise.resolve(m);
      return m.status;
    },
    async refresh() { return {started: false, message: 'This site updates itself every hour'}; },
    async portfolios() { return get(`data/portfolios.json?v=${await v()}`); },
    async intro() { return get(`data/intro.json?v=${await v()}`); },
    async gems() { return get(`data/gems.json?v=${await v()}`); },
    async unusual() { return get(`data/unusual.json?v=${await v()}`); },
    async unusual_event(q) { return get(`data/unusual/${encodeURIComponent(q.get('id'))}.json?v=${await v()}`); },
    async context() { return get(`data/context.json?v=${await v()}`); },
    async bench() { return get(`data/bench.json?v=${await v()}`); },
    async stock(p) {
      const t = (p.get('ticker') || '').toUpperCase(), f = t.replace(/[^A-Za-z0-9.\-]/g, '_');
      try { return await get(`data/stock/${encodeURIComponent(f)}.json?v=${await v()}`); } catch (e) { return {ticker: t, px: null, holders: []}; }
    },
    async most_bought(p) {
      const d = await get(`data/most-bought.json?v=${await v()}`), w = d.windows[p.get('days') || '90'] || d.windows['90'];
      return {days: w.days, since: w.since, items: p.get('etf') === '1' ? w.all : w.stocks};
    },
    async politicians() { return get(`data/politicians.json?v=${await v()}`); },
    async portfolio(p) { return (await pol(p.get('name'))).portfolio; },
    async politician(p) { return {filings: (await pol(p.get('name'))).filings}; },
    async trade(p) { const u = p.get('uid'); let t = (await recent()).find(x => x.uid === u); if (!t) t = (await all()).find(x => x.uid === u); if (!t) throw new Error(404); return t; },
    async trades(p) {
      const rows = where(await source(p), p).sort(SORTS[p.get('sort')] || SORTS.disclosure_date);
      const off = +(p.get('offset') || 0), lim = +(p.get('limit') || 50);
      return {total: rows.length, trades: rows.slice(off, off + lim)};
    },
    async stats(p) {
      const days = +(p.get('days') || 30), since = dayISO(days), m = await meta();
      const src = since >= m.recent_from ? await recent() : await all();
      const rows = src.filter(t => (t.disclosure_date || '') >= since && (!p.get('chamber') || t.chamber === p.get('chamber')) && (!p.get('party') || t.party === p.get('party')));
      const ticks = group(rows, t => t.ticker, t => ({ticker: t.ticker, asset: t.asset, company: t.company, n: 0, buys: 0, sells: 0, _p: new Set()}),
        (g, t) => { g.n++; g.buys += t.side === 'buy'; g.sells += t.side === 'sell'; g._p.add(t.politician); });
      ticks.forEach(g => { g.pols = g._p.size; delete g._p; });
      const pols = group(rows, t => t.politician + '|' + t.chamber, t => ({politician: t.politician, chamber: t.chamber, party: t.party, state: t.state, bioguide: t.bioguide, n: 0, buys: 0, sells: 0, latest: ''}),
        (g, t) => { g.n++; g.buys += t.side === 'buy'; g.sells += t.side === 'sell'; if ((t.disclosure_date || '') > g.latest) g.latest = t.disclosure_date; g.bioguide = g.bioguide || t.bioguide; });
      const by = (a, b) => b.n - a.n;
      return {days, since, totals: {n: rows.length, buys: rows.filter(t => t.side === 'buy').length, sells: rows.filter(t => t.side === 'sell').length,
        pols: new Set(rows.map(t => t.politician)).size, vol_low: rows.reduce((a, t) => a + (t.amount_low || 0), 0), vol_high: rows.reduce((a, t) => a + (t.amount_high || t.amount_low || 0), 0)},
        top_tickers: ticks.sort(by).slice(0, 8), top_politicians: pols.sort(by).slice(0, 8)};
    },
  };
  window.staticApi = async (path, opts) => {
    const u = new URL(path, location.href);
    const name = u.pathname.replace(/^.*\/api\//, '');
    const f = routes[name];
    if (!f) throw new Error('404 ' + name);
    return f(u.searchParams, opts);
  };
})();
