"""Check that the Senate eFD site (efdsearch.senate.gov) answers from this network: agreement form + one PTR search."""
import re, sys, time, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
B = "https://efdsearch.senate.gov"
s = requests.Session(); s.headers.update(UA)
r = s.get(B + "/search/home/", timeout=60); print("home", r.status_code, len(r.text))
m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
if not m: print(r.text[:300]); sys.exit(0)
time.sleep(2)
r = s.post(B + "/search/home/", data={"prohibition_agreement": "1", "csrfmiddlewaretoken": m.group(1)}, headers={"Referer": B + "/search/home/"}, timeout=60)
print("agree", r.status_code, r.url)
time.sleep(2)
tok = s.cookies.get("csrftoken")
r = s.post(B + "/search/report/data/", data={"start": "0", "length": "5", "report_types": "[11]", "filer_types": "[]",
    "submitted_start_date": "10/01/2026 00:00:00", "submitted_end_date": "", "candidate_state": "", "senator_state": "",
    "office_id": "", "first_name": "", "last_name": "", "csrfmiddlewaretoken": tok},
    headers={"Referer": B + "/search/", "X-CSRFToken": tok}, timeout=60)
print("search", r.status_code, r.text[:800])
