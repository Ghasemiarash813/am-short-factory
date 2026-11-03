"""Visuals: freely-licensed photos from Wikimedia Commons (credited), else the channel's generic B-roll."""
import os, re, html, glob, hashlib
import requests

UA = "AncientMachinesShortFactory/1.0 (+https://github.com/Ghasemiarash813/am-short-factory)"
API = "https://commons.wikimedia.org/w/api.php"
OK_LIC = ("cc0", "public domain", "pd", "cc by", "cc-by", "attribution")
BAD = ("nc", "nd", "fair use", "non-free")
PD_HOSTS = ("nasa.gov", "wikimedia.org", "wikipedia.org")


def log(*a):
    print("[img]", *a, flush=True)


def _clean(s):
    s = re.sub(r"<[^>]+>", "", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:60]


def commons_search(query, limit=12):
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
              "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
              "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1600}
    try:
        r = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=25).json()
    except Exception as e:  # noqa
        log("commons error", e); return []
    pages = sorted((r.get("query", {}).get("pages", {}) or {}).values(), key=lambda p: p.get("index", 99))
    res = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") not in ("image/jpeg", "image/png") or ii.get("width", 0) < 900 or ii.get("height", 0) < 600:
            continue
        md = ii.get("extmetadata", {})
        lic = _clean(md.get("LicenseShortName", {}).get("value", ""))
        l = lic.lower()
        if not any(k in l for k in OK_LIC) or any(re.search(rf"\b{b}\b", l) for b in BAD):
            continue
        title = p.get("title", "")
        if re.search(r"map|diagram|chart|logo|coat of arms|flag|plan\b|svg", title.lower()):
            continue
        res.append({"url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl"),
                    "artist": _clean(md.get("Artist", {}).get("value", "")) or "Wikimedia Commons",
                    "license": lic, "title": title})
    return res


def download(url, dest):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    r.raise_for_status()
    open(dest, "wb").write(r.content)
    return dest


def gather(lines, extra_queries, workdir, article=None, broll_dir="assets/broll"):
    """Assign an image to every line. Returns list of dicts (path, credit, ai, page)."""
    os.makedirs(workdir, exist_ok=True)
    used, pool, credits = set(), [], []
    # 0) article image only if from a public-domain host
    if article and article.get("og_image") and any(h in article.get("host", "") for h in PD_HOSTS):
        try:
            p = download(article["og_image"], os.path.join(workdir, "og.jpg"))
            pool.append({"path": p, "credit": f"Image: {article['host']}", "ai": 0, "page": article["url"]})
        except Exception as e:  # noqa
            log("og image failed", e)
    assigned = []
    queries = [l.get("visual", "") for l in lines]
    for i, q in enumerate(queries):
        pick = None
        for qq in [q] + list(extra_queries):
            if not qq:
                continue
            for c in commons_search(qq):
                if c["url"] in used:
                    continue
                try:
                    fn = os.path.join(workdir, "c_" + hashlib.md5(c["url"].encode()).hexdigest()[:10] + ".jpg")
                    download(c["url"], fn)
                    used.add(c["url"])
                    pick = {"path": fn, "credit": f"Photo: {c['artist'][:40]} / {c['license']} / Wikimedia Commons",
                            "ai": 0, "page": c["page"], "query": qq}
                    break
                except Exception as e:  # noqa
                    log("download failed", e)
            if pick:
                break
        if pick:
            log(f"line {i}: commons '{pick['query']}' -> {pick['page']}")
            pool.append(pick)
        assigned.append(pick)
    broll = sorted(glob.glob(os.path.join(broll_dir, "*.jpg")))
    out, bi = [], 0
    for i, a in enumerate(assigned):
        if a is None:
            # reuse an earlier real photo if we have >=2, else channel B-roll (AI illustration)
            real = [p for p in pool if not p["ai"]]
            if len(real) >= 2 and i % 2 == 1:
                a = real[i % len(real)]
            else:
                a = {"path": broll[(hash(lines[0].get("text", "")) + bi) % len(broll)], "credit": "", "ai": 1, "page": ""}
                bi += 1
        out.append(a)
    for a in out:
        if a.get("page") and a["credit"] and a["credit"] not in [c["credit"] for c in credits]:
            credits.append({"credit": a["credit"], "page": a["page"]})
    return out, credits
