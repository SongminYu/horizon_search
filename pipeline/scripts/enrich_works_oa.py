"""Enrich cached OpenAlex works with open-access status.

The people cache (raw/people/<grant>.json) was fetched with a slim select that
omits open_access. This pass collects every distinct work id across the cache and
batch-fetches its open-access status by OpenAlex id (50 ids/request), so the Works
layer can carry whether each paper is open access and by which route.

Horizon 2020 / Horizon Europe mandate open access for funded peer-reviewed
publications, but compliance is not 100% — this records the actual status.

Output : raw/works_oa.json   {work_id: {"is_oa": bool, "oa_status": str}}  (resumable)
oa_status is OpenAlex's classification: gold | green | hybrid | bronze | diamond | closed.
Net: stdlib urllib only, OpenAlex polite pool (optional key for higher quota).
"""
import json
import time
import http.client
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "raw" / "people"
OUT = ROOT / "raw" / "works_oa.json"
MAILTO = "yu.ceepcas@gmail.com"
BATCH = 50


def load_openalex_key():
    import os
    env = (os.environ.get("OPENALEX_API_KEY") or "").strip()
    if env:
        return env
    f = ROOT / "openalex_api_key.local"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" in s:
                s = s.split("=", 1)[1]
            return s.strip().strip('"').strip("'") or None
    return None


OPENALEX_KEY = load_openalex_key()


def all_work_ids():
    ids = set()
    for f in CACHE.glob("*.json"):
        for w in json.loads(f.read_text()):
            ids.add(w["id"].rsplit("/", 1)[-1])
    return sorted(ids)


def fetch_batch(ids):
    filt = "ids.openalex:" + "|".join(ids)
    url = (f"https://api.openalex.org/works?filter={filt}"
           f"&select=id,open_access&per-page={BATCH}&mailto={MAILTO}")
    if OPENALEX_KEY:
        url += "&api_key=" + OPENALEX_KEY
    req = urllib.request.Request(url, headers={"User-Agent": f"horizon-works-bot ({MAILTO})"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["results"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503): time.sleep(2 ** attempt); continue
            raise
        except (urllib.error.URLError, TimeoutError,
                http.client.IncompleteRead, http.client.HTTPException,
                ConnectionError, OSError):
            time.sleep(2 ** attempt)
    print("  ! gave up on a batch")
    return []


def main():
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    ids = [i for i in all_work_ids() if i not in out]
    print(f"works needing open-access status: {len(ids)} (already have {len(out)})")
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        for w in fetch_batch(chunk):
            wid = w["id"].rsplit("/", 1)[-1]
            oa = w.get("open_access") or {}
            out[wid] = {"is_oa": bool(oa.get("is_oa")), "oa_status": oa.get("oa_status")}
        # mark misses so we don't refetch forever
        for wid in chunk:
            out.setdefault(wid, {"is_oa": None, "oa_status": None})
        if (i // BATCH) % 20 == 0:
            OUT.write_text(json.dumps(out))
            oa_n = sum(1 for v in out.values() if v.get("is_oa"))
            print(f"  {i + len(chunk)}/{len(ids)} | open access: {oa_n:,}", flush=True)
        time.sleep(0.12)
    OUT.write_text(json.dumps(out))
    resolved = [v for v in out.values() if v.get("oa_status") is not None]
    oa_n = sum(1 for v in resolved if v.get("is_oa"))
    pct = (oa_n / len(resolved) * 100) if resolved else 0
    print(f"done: {len(out):,} works | resolved {len(resolved):,} | open access {oa_n:,} ({pct:.0f}%) | saved {OUT}")


if __name__ == "__main__":
    main()
