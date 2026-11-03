"""Fetch fresh archaeology news from RSS feeds, dedupe, resolve and extract articles."""
import calendar, html, json, re, time
from urllib.parse import quote, urlparse
import feedparser, requests

BOT_UA = "AncientMachinesShortFactory/1.0 (+https://github.com/Ghasemiarash813/am-short-factory)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
STOP = set("a an the of in on at to for and or with from by is are was were be has have new just its it this that as how why what who after into near over".split())


def log(*a):
    print("[news]", *a, flush=True)


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def title_key(t):
    w = [x for x in re.findall(r"[a-z0-9]+", t.lower()) if x not in STOP]
    return " ".join(sorted(w[:9]))


def similar(a, b):
    A, B = set(a.split()), set(b.split())
    if not A or not B:
        return False
    return len(A & B) / min(len(A), len(B)) >= 0.6


def fetch_feeds(cfg, hours):
    now = time.time()
    items = []
    for f in cfg["feeds"]:
        for ua in (BOT_UA, BROWSER_UA):
            try:
                r = requests.get(f["url"], headers={"User-Agent": ua}, timeout=25)
                d = feedparser.parse(r.content)
                if d.entries:
                    break
            except Exception as e:  # noqa
                d = None
                log("feed error", f["url"], e)
        if not d or not d.entries:
            log("feed empty/blocked:", f["url"])
            continue
        n = 0
        for e in d.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if not t:
                continue
            ts = calendar.timegm(t)
            if now - ts > hours * 3600 or ts - now > 6 * 3600:
                continue
            title = strip_html(e.get("title", ""))
            source = f["name"]
            source_url = ""
            if "news.google.com" in f["url"]:
                src = e.get("source") or {}
                source = src.get("title") or source
                source_url = src.get("href", "")
                title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title)
            items.append({
                "title": title, "link": e.get("link", ""), "source": source, "source_home": source_url,
                "summary": strip_html(e.get("summary", ""))[:500], "ts": ts,
                "published": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts)),
                "age_h": round((now - ts) / 3600, 1), "tier": f.get("tier", 2),
            })
            n += 1
        log(f"{n:3d} fresh from {f['name']} {f['url'][:70]}")
    # dedupe within this batch (prefer tier 1 / direct feeds)
    items.sort(key=lambda x: (x["tier"], "news.google.com" in x["link"], -x["ts"]))
    out = []
    for it in items:
        k = title_key(it["title"])
        if any(similar(k, title_key(o["title"])) or it["link"] == o["link"] for o in out):
            continue
        out.append(it)
    return out


def filter_history(items, history):
    keys = [h.get("title_key", "") for h in history]
    links = {h.get("link") for h in history} | {h.get("resolved") for h in history}
    res = []
    for it in items:
        k = title_key(it["title"])
        if it["link"] in links or any(similar(k, hk) for hk in keys if hk):
            continue
        res.append(it)
    return res


def gnews_resolve(url):
    """Decode a news.google.com/rss/articles/... link to the publisher URL (best effort)."""
    m = re.search(r"/articles/([^?/]+)", url)
    if not m:
        return url
    gid = m.group(1)
    try:
        r = requests.get(f"https://news.google.com/rss/articles/{gid}", headers={"User-Agent": BROWSER_UA}, timeout=20)
        sig = re.search(r'data-n-a-sg="([^"]+)"', r.text)
        ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
        if not (sig and ts):
            return None
        inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
                 '"X","X",1,[1,1,1],1,1,null,0,0,null,0],"%s",%s,"%s"]' % (gid, ts.group(1), sig.group(1)))
        payload = [[["Fbv4je", inner]]]
        r2 = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                           headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "User-Agent": BROWSER_UA},
                           data="f.req=" + quote(json.dumps(payload)), timeout=20)
        body = r2.text.split("\n\n", 1)[1]
        parsed = json.loads(body)[:-2]
        return json.loads(parsed[0][2])[1]
    except Exception as e:  # noqa
        log("gnews decode failed", e)
        return None


def fetch_article(url):
    """Return dict(url, text, og_image, title) or None."""
    import trafilatura
    if "news.google.com" in url:
        url = gnews_resolve(url)
        if not url:
            return None
    for ua in (BROWSER_UA, BOT_UA):
        try:
            r = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "en"}, timeout=30)
            if r.status_code >= 400 or len(r.text) < 2000:
                continue
            text = trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True) or ""
            if len(text) < 700:
                continue
            og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text)
            return {"url": r.url, "text": text[:14000], "og_image": og.group(1) if og else "",
                    "host": urlparse(r.url).netloc.replace("www.", "")}
        except Exception as e:  # noqa
            log("article fetch error", url, e)
    return None
