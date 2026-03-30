#!/usr/bin/env python3
import json, os, sys, time
import requests

GROUP_ID = "6271906"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "weisslabmit-lab-website/1.0 (+github actions)",
    "Accept": "application/json"
})

BASE = f"https://api.zotero.org/groups/{GROUP_ID}/items?format=csljson&limit=100"
TIMEOUT = 30
MAX_RETRIES = 5
MAX_PAGES = 50
GLOBAL_DEADLINE = time.time() + 12 * 60  # ~12 minutes max

def fetch(url):
    attempt = 0
    while True:
        if time.time() > GLOBAL_DEADLINE:
            raise TimeoutError("Global deadline reached while fetching Zotero API")
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
        except requests.RequestException:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            time.sleep(1.5 * attempt)
            continue

        backoff = r.headers.get("Backoff") or r.headers.get("Retry-After")
        if backoff:
            try:
                delay = float(backoff)
            except ValueError:
                delay = 5.0
            print(f"Zotero throttling; sleeping {delay:.1f}s …", flush=True)
            time.sleep(delay)

        if 200 <= r.status_code < 300:
            return r
        elif r.status_code in (429, 503):
            attempt += 1
            if attempt > MAX_RETRIES:
                r.raise_for_status()
            sleep_for = 3.0 * attempt
            print(f"HTTP {r.status_code}; retrying in {sleep_for:.1f}s …", flush=True)
            time.sleep(sleep_for)
            continue
        else:
            r.raise_for_status()

def next_link(resp):
    link = resp.headers.get("Link")
    if not link:
        return None
    for p in [p.strip() for p in link.split(",")]:
        if 'rel="next"' in p:
            start = p.find("<"); end = p.find(">")
            if start != -1 and end != -1 and end > start:
                return p[start+1:end]
    return None

def main():
    url = BASE
    all_items = []
    pages = 0

    while url:
        pages += 1
        if pages > MAX_PAGES:
            print(f"Reached safety cap of {MAX_PAGES} pages; stopping.", flush=True)
            break

        print(f"Fetching page {pages}: {url}", flush=True)
        resp = fetch(url)
        batch = resp.json()
        if isinstance(batch, dict) and "items" in batch:
            batch = batch["items"]
        if not isinstance(batch, list):
            print(f"Unexpected payload type: {type(batch).__name__}; stopping.", flush=True)
            break

        print(f"  → {len(batch)} items", flush=True)
        if not batch:
            break

        all_items.extend(batch)

        b = resp.headers.get("Backoff") or resp.headers.get("Retry-After")
        if b:
            try:
                delay = float(b)
            except ValueError:
                delay = 5.0
            print(f"Throttled between pages; sleeping {delay:.1f}s …", flush=True)
            time.sleep(delay)
        else:
            time.sleep(0.2)

        url = next_link(resp)

    os.makedirs("data", exist_ok=True)
    # Write BOTH names so either key works in Hugo
    with open("data/publications.zotero.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    with open("data/publications.json", "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"Done. Wrote data/publications.zotero.json and data/publications.json with {len(all_items)} items.", flush=True)

if __name__ == "__main__":
    main()
