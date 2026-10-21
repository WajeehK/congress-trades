# Congress Trades

Stock trades disclosed by members of Congress and the President, rebuilt into estimated portfolios.
**Live site:** https://wajeehk.github.io/congress-trades/ (installable as a PWA)

## How it works
- `.github/workflows/pipeline.yml` runs **every hour** (and on push / manual dispatch):
  1. restores the SQLite state (`state/trades.db`: trades, filings, parsed OCR results, Yahoo price cache) from the Actions cache, or from the AES-encrypted backup on the `state` branch if the cache was evicted;
  2. `pipeline/ci_refresh.py` fetches new House Clerk PTRs, Senate trades (Bargo API), OGE 278-T filings (the President) and Yahoo Finance prices, incrementally;
  3. sends ntfy push alerts for genuinely new trades (see below);
  4. `pipeline/export_static.py` writes pre-generated JSON (`data/*.json`) plus the frontend in `web/` to `_site`, which is deployed to GitHub Pages.
- The frontend (`web/`) is the same app as the server version; `web/static/data.js` emulates the API in the browser, so filtering, sorting, estimated prices, portfolios, Mirror and the Alerts tab all run client-side.

## Alerts (ntfy)
Exactly one sender at a time. `NTFY_SENDER` (repository variable):
- `auto` (default): the workflow sends only if the self-hosted server at `BOX_STATUS_URL` is down or hasn't refreshed for 3 hours;
- `actions`: the workflow always sends (use this once the self-hosted server is retired);
- `box`: the workflow never sends.

Topic name comes from the `NTFY_TOPIC` secret; per-politician topics are `<topic>-<politician-slug>`.

## Data sources and attribution
- U.S. House Clerk financial disclosures (public domain)
- U.S. Office of Government Ethics, OGE Form 278-T (public domain)
- **Senate trades via [Bargo](https://www.bargo.ai/free-apis/congress)** under its API terms. This site publishes only processed fields
  (politician, ticker, side, dates, amount range, our price estimates) for trades disclosed in the last 100 days,
  with visible credit to Bargo. Raw Bargo records are never committed or published; they live only in the encrypted state.
  Set the repository variable `PUBLISH_SENATE=0` to hide Senate trades entirely.
- Prices: Yahoo Finance chart data (estimates only; not investment advice).

## Local server version
`app.py` is the FastAPI server (`uvicorn app:app`) that the static build is generated from.
