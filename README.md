# The Black House

Stock trades disclosed by members of Congress and the President, rebuilt into estimated portfolios.
**Live site:** https://wajeehk.github.io/congress-trades/ (installable as a PWA)

## How it works
- `.github/workflows/pipeline.yml` runs **every hour** (and on push / manual dispatch):
  1. restores the SQLite state (`state/trades.db`: trades, filings, parsed OCR results, Yahoo price cache) from the Actions cache, or from the AES-encrypted backup on the `state` branch if the cache was evicted;
  2. `pipeline/ci_refresh.py` fetches new House Clerk PTRs, Senate trades (Bargo API), OGE 278-T filings (the President) and Yahoo Finance prices, incrementally;
  3. sends ntfy push alerts for genuinely new trades (see below);
  4. `pipeline/export_static.py` writes pre-generated JSON (`data/*.json`) plus the frontend in `web/` to `_site`, which is deployed to GitHub Pages.
- The frontend (`web/`) is the same app as the server version; `web/static/data.js` emulates the API in the browser, so filtering, sorting, estimated prices, portfolios, Mirror and the Alerts tab all run client-side.

## Senate relay (box)
Bargo answers GitHub Actions IPs with HTTP 403, so Senate trades come from the self-hosted box:
`box/senate_feed.sh loop` reads the box server's latest Bargo dump each hour, encrypts it with `STATE_KEY`
and force-pushes it to the `senate-feed` branch; the workflow decrypts and ingests it. If the box is off,
House, OGE and prices keep updating; Senate pauses until the box is back.

The relay is also the scheduler: GitHub's hourly cron is often late or skipped for hours, so the relay checks every
10 minutes (:07, :17, ...) and runs `gh workflow run pipeline.yml` right after pushing a new Senate feed, and once per
UTC hour at ~:07 otherwise (skipped if a run is already queued or one started in the last 30 min). The cron stays as a
backup; its `guard` job skips the run if another run succeeded or is running within the last 40 minutes, and the
`pipeline` concurrency group serialises everything.

Health check: `ps -fp $(cat /workspace/ct-build/box-feed/senate_feed.pid)` should show `senate_feed.sh loop`, and
`senate_feed.log` should have a line at least every 10 minutes plus a `dispatched` / `skipped` line every hour.
Restart (only that PID): `cd /workspace/ct-build/box-feed && kill <pid>; nohup setsid ./senate_feed.sh loop >> senate_feed.log 2>&1 < /dev/null &`.
The hourly slot and last feed hash live in `last_hourly` / `last.sha`, so a restart neither double-dispatches nor re-pushes.

## Alerts (ntfy)
Exactly one sender at a time. `NTFY_SENDER` (repository variable):
- `auto` (default): the workflow sends only if the self-hosted server at `BOX_STATUS_URL` (secret) is down or hasn't refreshed for 3 hours;
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
