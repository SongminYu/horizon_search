"""Enrich cached OpenAlex works with DOI / landing-page links.

The people cache (raw/people/<grant>.json) was fetched with a slim select that
omits links. This pass collects every distinct work id across the cache and
batch-fetches its DOI + open-access landing page by OpenAlex id (50 ids/request),
so the Works layer can carry a real clickable link.

Output : raw/works_doi.json   {work_id: {"doi": ..., "url": ...}}  (resumable)
Net: stdlib urllib only, OpenAlex polite pool. No API key.
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "raw" / "people"
OUT = ROOT / "raw" / "works_doi.json"
MAILTO = "yu.ceepcas@gmail.com"
BATCH = 50


def all_work_ids():
    ids = set()
    for f in CACHE.glob("*.json"):
        for w in json.loads(f.read_text()):
            ids.add(w["id"].rsplit("/", 1)[-1])
    return sorted(ids)


def fetch_batch(ids):
    filt = "ids.openalex:" + "|".join(ids)
    url = (f"https://api.openalex.org/works?filter={filt}"
           f"&select=id,doi,primary_location&per-page={BATCH}&mailto={MAILTO}")
    req = urllib.request.Request(url, headers={"User-Agent": f"eu3e-works-bot ({MAILTO})"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["results"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503): time.sleep(2 ** attempt); continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    print("  ! gave up on a batch")
    return []


def main():
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    ids = [i for i in all_work_ids() if i not in out]
    print(f"works needing links: {len(ids)} (already have {len(out)})")
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        for w in fetch_batch(chunk):
            wid = w["id"].rsplit("/", 1)[-1]
            loc = w.get("primary_location") or {}
            out[wid] = {"doi": w.get("doi"), "url": loc.get("landing_page_url")}
        # mark misses so we don't refetch forever
        for wid in chunk:
            out.setdefault(wid, {"doi": None, "url": None})
        if (i // BATCH) % 20 == 0:
            OUT.write_text(json.dumps(out))
            print(f"  {i + len(chunk)}/{len(ids)} | with DOI: {sum(1 for v in out.values() if v.get('doi')):,}", flush=True)
        time.sleep(0.12)
    OUT.write_text(json.dumps(out))
    doi = sum(1 for v in out.values() if v.get("doi"))
    print(f"done: {len(out):,} works | DOI {doi:,} ({doi/len(out):.0%}) | saved {OUT}")


if __name__ == "__main__":
    main()
