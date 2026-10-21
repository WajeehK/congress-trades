/* The Black House: smart search shared by the trades feed and the politicians list.
   Case-insensitive partial matching across ticker, asset, company, politician, party, state, chamber
   and trade type, plus brand aliases (google -> GOOGL/GOOG, facebook -> META, berkshire -> BRK.B ...). */
(function () {
  const ALIASES = {"mp materials":{"t":["MP"],"n":["mp matls"]},"usa rare earth":{"t":["USAR"],"n":[]},"google":{"t":["GOOGL","GOOG","GOOGM","GOOGN"],"n":["alphabet"]},"alphabet":{"t":["GOOGL","GOOG","GOOGM","GOOGN"],"n":[]},"youtube":{"t":["GOOGL","GOOG"],"n":["alphabet"]},"waymo":{"t":["GOOGL","GOOG"],"n":["alphabet"]},"facebook":{"t":["META","FB"],"n":["meta platforms"]},"meta":{"t":["META","FB"],"n":[]},"instagram":{"t":["META","FB"],"n":["meta platforms"]},"whatsapp":{"t":["META","FB"],"n":["meta platforms"]},"berkshire":{"t":["BRK.B","BRK.A"],"n":[]},"berkshire hathaway":{"t":["BRK.B","BRK.A"],"n":[]},"buffett":{"t":["BRK.B","BRK.A"],"n":["berkshire"]},"tesla":{"t":["TSLA"],"n":[]},"amazon":{"t":["AMZN"],"n":[]},"aws":{"t":["AMZN"],"n":["amazon"]},"microsoft":{"t":["MSFT"],"n":[]},"apple":{"t":["AAPL"],"n":[]},"iphone":{"t":["AAPL"],"n":["apple inc"]},"nvidia":{"t":["NVDA"],"n":[]},"netflix":{"t":["NFLX"],"n":[]},"disney":{"t":["DIS"],"n":[]},"walmart":{"t":["WMT"],"n":[]},"costco":{"t":["COST"],"n":[]},"jpmorgan":{"t":["JPM"],"n":[]},"jp morgan":{"t":["JPM"],"n":[]},"chase":{"t":["JPM"],"n":["jpmorgan"]},"bank of america":{"t":["BAC"],"n":[]},"bofa":{"t":["BAC"],"n":[]},"goldman":{"t":["GS"],"n":[]},"goldman sachs":{"t":["GS"],"n":[]},"morgan stanley":{"t":["MS"],"n":[]},"wells fargo":{"t":["WFC"],"n":[]},"citi":{"t":["C"],"n":[]},"citigroup":{"t":["C"],"n":[]},"visa":{"t":["V"],"n":[]},"mastercard":{"t":["MA"],"n":[]},"paypal":{"t":["PYPL"],"n":[]},"amex":{"t":["AXP"],"n":[]},"american express":{"t":["AXP"],"n":[]},"blackrock":{"t":["BLK"],"n":[]},"coca cola":{"t":["KO"],"n":[]},"coca-cola":{"t":["KO"],"n":[]},"coke":{"t":["KO"],"n":["coca-cola"]},"pepsi":{"t":["PEP"],"n":[]},"pepsico":{"t":["PEP"],"n":[]},"mcdonalds":{"t":["MCD"],"n":[]},"mcdonald's":{"t":["MCD"],"n":[]},"starbucks":{"t":["SBUX"],"n":[]},"nike":{"t":["NKE"],"n":[]},"boeing":{"t":["BA"],"n":[]},"lockheed":{"t":["LMT"],"n":[]},"lockheed martin":{"t":["LMT"],"n":[]},"raytheon":{"t":["RTX"],"n":[]},"northrop":{"t":["NOC"],"n":[]},"general dynamics":{"t":["GD"],"n":[]},"intel":{"t":["INTC"],"n":[]},"amd":{"t":["AMD"],"n":[]},"broadcom":{"t":["AVGO"],"n":[]},"qualcomm":{"t":["QCOM"],"n":[]},"oracle":{"t":["ORCL"],"n":[]},"salesforce":{"t":["CRM"],"n":[]},"adobe":{"t":["ADBE"],"n":[]},"ibm":{"t":["IBM"],"n":[]},"cisco":{"t":["CSCO"],"n":[]},"palantir":{"t":["PLTR"],"n":[]},"uber":{"t":["UBER"],"n":[]},"airbnb":{"t":["ABNB"],"n":[]},"exxon":{"t":["XOM"],"n":[]},"exxonmobil":{"t":["XOM"],"n":[]},"chevron":{"t":["CVX"],"n":[]},"pfizer":{"t":["PFE"],"n":[]},"moderna":{"t":["MRNA"],"n":[]},"johnson & johnson":{"t":["JNJ"],"n":[]},"johnson and johnson":{"t":["JNJ"],"n":[]},"j&j":{"t":["JNJ"],"n":[]},"unitedhealth":{"t":["UNH"],"n":[]},"lilly":{"t":["LLY"],"n":[]},"eli lilly":{"t":["LLY"],"n":[]},"home depot":{"t":["HD"],"n":[]},"at&t":{"t":["T"],"n":[]},"verizon":{"t":["VZ"],"n":[]},"comcast":{"t":["CMCSA"],"n":[]},"tsmc":{"t":["TSM"],"n":[]},"taiwan semiconductor":{"t":["TSM"],"n":[]},"coinbase":{"t":["COIN"],"n":[]},"microstrategy":{"t":["MSTR"],"n":[]},"snowflake":{"t":["SNOW"],"n":[]},"crowdstrike":{"t":["CRWD"],"n":[]},"shopify":{"t":["SHOP"],"n":[]},"spotify":{"t":["SPOT"],"n":[]},"s&p 500":{"t":["SPY","VOO","IVV"],"n":[]},"s&p":{"t":["SPY","VOO","IVV"],"n":[]},"nasdaq":{"t":["QQQ"],"n":[]},"trump media":{"t":["DJT"],"n":[]},"truth social":{"t":["DJT"],"n":["trump media"]},"general electric":{"t":["GE"],"n":[]},"general motors":{"t":["GM"],"n":[]},"ford":{"t":["F"],"n":[]},"target":{"t":["TGT"],"n":[]},"dell":{"t":["DELL"],"n":[]},"micron":{"t":["MU"],"n":[]},"supermicro":{"t":["SMCI"],"n":[]},"super micro":{"t":["SMCI"],"n":[]},"robinhood":{"t":["HOOD"],"n":[]},"bitcoin":{"t":["IBIT","FBTC","GBTC","MSTR","COIN"],"n":[]},"gamestop":{"t":["GME"],"n":[]},"amc":{"t":["AMC"],"n":[]},"rivian":{"t":["RIVN"],"n":[]},"lucid":{"t":["LCID"],"n":[]},"ups":{"t":["UPS"],"n":[]},"fedex":{"t":["FDX"],"n":[]},"caterpillar":{"t":["CAT"],"n":[]},"deere":{"t":["DE"],"n":[]},"john deere":{"t":["DE"],"n":[]},"3m":{"t":["MMM"],"n":[]},"procter":{"t":["PG"],"n":[]},"procter & gamble":{"t":["PG"],"n":[]},"p&g":{"t":["PG"],"n":[]},"merck":{"t":["MRK"],"n":[]},"abbvie":{"t":["ABBV"],"n":[]},"amgen":{"t":["AMGN"],"n":[]},"gilead":{"t":["GILD"],"n":[]},"cvs":{"t":["CVS"],"n":[]},"walgreens":{"t":["WBA"],"n":[]},"servicenow":{"t":["NOW"],"n":[]},"intuit":{"t":["INTU"],"n":[]},"applied materials":{"t":["AMAT"],"n":[]},"lam research":{"t":["LRCX"],"n":[]},"asml":{"t":["ASML"],"n":[]},"arm":{"t":["ARM"],"n":[]},"zoom":{"t":["ZM"],"n":[]},"salesforce.com":{"t":["CRM"],"n":[]},"dupont":{"t":["DD"],"n":[]},"dow":{"t":["DOW"],"n":[]},"honeywell":{"t":["HON"],"n":[]},"verisign":{"t":["VRSN"],"n":[]}};
  const STATES = {AL:'alabama',AK:'alaska',AZ:'arizona',AR:'arkansas',CA:'california',CO:'colorado',CT:'connecticut',DE:'delaware',FL:'florida',GA:'georgia',HI:'hawaii',ID:'idaho',IL:'illinois',IN:'indiana',IA:'iowa',KS:'kansas',KY:'kentucky',LA:'louisiana',ME:'maine',MD:'maryland',MA:'massachusetts',MI:'michigan',MN:'minnesota',MS:'mississippi',MO:'missouri',MT:'montana',NE:'nebraska',NV:'nevada',NH:'new hampshire',NJ:'new jersey',NM:'new mexico',NY:'new york',NC:'north carolina',ND:'north dakota',OH:'ohio',OK:'oklahoma',OR:'oregon',PA:'pennsylvania',RI:'rhode island',SC:'south carolina',SD:'south dakota',TN:'tennessee',TX:'texas',UT:'utah',VT:'vermont',VA:'virginia',WA:'washington',WV:'west virginia',WI:'wisconsin',WY:'wyoming',DC:'district of columbia',PR:'puerto rico',GU:'guam',VI:'virgin islands',AS:'american samoa',MP:'northern mariana islands'};
  const PARTY = {D: 'democrat democratic dem', R: 'republican gop rep', I: 'independent ind'};
  const SIDE = {buy: 'buy bought purchase', sell: 'sell sold sale'};
  const norm = s => String(s || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ').trim();
  const compact = s => norm(s).replace(/[^a-z0-9]/g, '');
  const tick = s => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');   // BRK.B == BRK-B == BRKB
  const KEYS = Object.keys(ALIASES).map(k => [norm(k), ALIASES[k].t.map(tick), ALIASES[k].n]);
  const MULTI = KEYS.filter(([k]) => k.includes(' ')).sort((a, b) => b[0].length - a[0].length);

  function aliasTickers(text) {
    const out = new Set(), names = new Set();
    for (const [k, ts, ns] of KEYS) {
      // exact alias always; prefix-typing ("goo", "berksh") once 3+ letters and the alias is long enough to be unambiguous
      if (k === text || (text.length >= 3 && k.length >= 4 && k.startsWith(text))) { ts.forEach(t => out.add(t)); ns.forEach(n => names.add(n)); }
    }
    return {out, names: [...names]};
  }
  function parse(q) {
    let s = ' ' + norm(q).replace(/["']/g, '') + ' ';
    const terms = [];
    for (const [k] of MULTI) {
      if (s.includes(' ' + k + ' ')) { terms.push(k); s = s.split(' ' + k + ' ').join(' '); }
      else if (s.trim().length >= 3 && k.startsWith(s.trim()) && s.trim().includes(' ')) { terms.push(s.trim()); s = ' '; }
    }
    s.split(' ').filter(Boolean).forEach(w => terms.push(w));
    return terms.map(text => { const a = aliasTickers(text); return {text, c: compact(text), tk: tick(text), alias: a.out, names: a.names}; });
  }
  function tradeHay(t) {
    if (t._hay) return t._hay;
    const st = (t.state || '').toUpperCase();
    const h = norm([t.politician, t.ticker, t.asset, t.company, t.description && String(t.description).slice(0, 200),
      PARTY[t.party] || t.party, t.party && st ? `${t.party}-${st}` : '', st, STATES[st], t.chamber, t.chamber === 'President' ? 'white house trump' : '',
      t.tx_type, SIDE[t.side] || t.side, t.owner].filter(Boolean).join(' | '));
    Object.defineProperty(t, '_hay', {value: {h, c: h.replace(/[^a-z0-9]/g, ''), t: tick(t.ticker)}, enumerable: false});
    return t._hay;
  }
  function termHit(x, hay) {
    if (hay.t && (x.alias.has(hay.t) || (x.tk && hay.t.startsWith(x.tk)))) return true;
    if (hay.h.includes(x.text) || x.names.some(n => hay.h.includes(n))) return true;
    return x.c.length >= 3 && hay.c.includes(x.c);   // "jp morgan" ~ "JPMorgan", "brk.b" ~ "BRK-B"
  }
  function compile(q) {
    const terms = parse(q);
    if (!terms.length) return () => true;
    return t => { const hay = tradeHay(t); return terms.every(x => termHit(x, hay)); };
  }
  function compilePeople(q) {
    const terms = parse(q);
    if (!terms.length) return () => true;
    return p => {
      if (!p._hay) {
        const st = (p.state || '').toUpperCase();
        const h = norm([p.politician, PARTY[p.party] || p.party, p.party && st ? `${p.party}-${st}` : '', st, STATES[st], p.chamber, p.chamber === 'President' ? 'white house' : ''].filter(Boolean).join(' | '));
        Object.defineProperty(p, '_hay', {value: {h, c: h.replace(/[^a-z0-9]/g, ''), t: ''}, enumerable: false});
      }
      return terms.every(x => p._hay.h.includes(x.text) || (x.c.length >= 3 && p._hay.c.includes(x.c)));
    };
  }
  window.BHSearch = {compile, compilePeople, parse, ALIASES};
})();
