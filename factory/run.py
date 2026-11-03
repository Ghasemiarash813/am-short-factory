"""Ancient Machines Short Factory: news -> script -> voice -> visuals -> 1080x1920 Short -> page data."""
import datetime as dt, json, os, re, shutil, sys, time, traceback
import requests

sys.path.insert(0, os.path.dirname(__file__))
import news, writer, images, tts, render, llm  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
CFG = json.load(open("factory/config.json"))
HIST_F = "data/history.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "Ghasemiarash813/am-short-factory")
RUN_NO = os.environ.get("GITHUB_RUN_NUMBER", "0")
RUN_URL = f"https://github.com/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
CTA = "Tap the link below for the full case file."
NOW = dt.datetime.now(dt.timezone.utc)
TEHRAN = NOW.astimezone(dt.timezone(dt.timedelta(hours=3, minutes=30)))


def log(*a):
    print("[run]", *a, flush=True)


def load_json(p, default):
    try:
        return json.load(open(p))
    except Exception:  # noqa
        return default


def words(lines):
    return sum(len(l["text"].split()) for l in lines)


def as_list(v, sep=r",\s*"):
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        return [x for x in re.split(sep, v) if x.strip()]
    return []


RELATED_RULES = [
    (r"antikythera|\bgears?\b|geared|mechanism|astronomical calculator", "X8newfre5Ds"),
    (r"great pyramid|khufu|cheops|scanpyramids|muon", "0oxRyjMgIBU"),
    (r"nazca|geoglyph|peru|andes|inca", "BfBOHKLFXa8"),
    (r"solstice|equinox|observator|astronom|\bstars?\b|constellation|orion|calendar", "wFKi87528Rc"),
    (r"egypt|saqqara|giza|pharaoh|nile|luxor|tomb of|mummy|sarcophag", "BDB2DcM3w14"),
]


def pick_related(text):
    longs = {l["id"]: l for l in CFG["related_longs"]}
    t = text.lower()
    for pat, vid in RELATED_RULES:
        if re.search(pat, t) and vid in longs:
            return longs[vid]
    return CFG["related_longs"][0]


def clean_title(t):
    t = re.sub(r"\s*#\w+", "", t or "").strip().strip('"')
    if len(t) > 50:
        t = t[:50].rsplit(" ", 1)[0].rstrip(",:;-")
    return t


def main():
    os.makedirs("out", exist_ok=True); os.makedirs("docs", exist_ok=True); os.makedirs("data", exist_ok=True)
    work = "out/work"; shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    hist = load_json(HIST_F, [])
    prev = load_json("docs/today.json", {})
    page = {"date": TEHRAN.strftime("%Y-%m-%d"), "generated_at_utc": NOW.strftime("%Y-%m-%d %H:%M UTC"),
            "generated_at_tehran": TEHRAN.strftime("%Y-%m-%d %H:%M"), "run_url": RUN_URL, "status": "error",
            "message": "", "candidates": [], "short": None, "archive": prev.get("archive", [])[:14]}
    try:
        # 1) news
        cands = []
        for hrs in (CFG["window_hours"], CFG["fallback_window_hours"]):
            cands = news.filter_history(news.fetch_feeds(CFG, hrs), hist)
            log(f"{len(cands)} new candidates in {hrs}h")
            if len(cands) >= 5:
                break
        if not cands:
            page.update(status="no_story", message="هیچ خبر تازه‌ای در ۷۲ ساعت گذشته پیدا نشد."); return page, 0
        covered = CFG["already_covered"] + [h["title"] for h in hist[-40:]]
        cov_keys = [news.title_key(c) for c in covered]
        cands = [c for c in cands if not any(news.similar(news.title_key(c["title"]), k) for k in cov_keys)]
        ranked = writer.rank(cands, covered, CFG["models"])
        ranked = [r for r in ranked if r.get("score", 0) >= 40] or ranked
        ranked = [r for r in ranked if not (r.get("searchable_name") and any(
            r["searchable_name"].lower().split(":")[0].strip() in c.lower() for c in covered if len(r["searchable_name"]) > 3))] or ranked
        page["candidates"] = [{k: r.get(k) for k in ("title", "source", "link", "published", "age_h", "score", "why", "searchable_name")}
                              for r in ranked[:3]]
        if not ranked:
            page.update(status="no_story", message="خبر مناسبی برای کانال پیدا نشد."); return page, 0
        # 2) first story whose article we can actually read
        story = article = None
        for r in ranked[:6]:
            a = news.fetch_article(r["link"])
            log("article", r["title"][:70], "->", bool(a))
            if a:
                story, article = r, a; break
        if not story:
            raise RuntimeError("Could not read any of the top stories' articles")
        story["resolved"] = article["url"]
        # 3) script
        sc = writer.write_script(story, article, CFG["related_longs"], CFG["models"])
        lines = [{"text": l["text"].strip(), "visual": l.get("visual", "")} for l in sc.get("lines", []) if l.get("text")]
        if not (4 <= len(lines) <= 10):
            raise RuntimeError(f"Script has {len(lines)} lines")
        if words(lines) < 98:
            try:
                ex = writer.expand(article, lines, CFG["models"])
                nl = [{"text": l["text"].strip(), "visual": l.get("visual", "")} for l in ex.get("lines", []) if l.get("text")]
                if words(nl) > words(lines) and 5 <= len(nl) <= 10:
                    log(f"expanded {words(lines)} -> {words(nl)} words"); lines = nl
            except Exception as e:  # noqa
                log("expand skipped:", e)
        chk = {}
        try:
            chk = writer.fact_check(article, lines, CFG["models"])
            fixed = chk.get("lines") or []
            if not chk.get("ok", True) and len(fixed) == len(lines):
                for l, t in zip(lines, fixed):
                    if isinstance(t, str) and t.strip():
                        l["text"] = t.strip()
                log("fact-check fixed:", chk.get("problems"))
        except Exception as e:  # noqa
            log("fact-check skipped:", e)
        endq = str(sc.get("end_question") or "").strip()
        if not lines[-1]["text"].rstrip().endswith("?"):
            q = endq if endq.endswith("?") else "What do you think it was really for?"
            lines.append({"text": q, "visual": lines[0].get("visual", "")})
        if not endq.endswith("?") or len(endq) > 40:
            endq = lines[-1]["text"] if len(lines[-1]["text"]) <= 40 else "What do you think?"
        title = clean_title(sc.get("title", story["title"]))
        rel = pick_related(story["title"] + " " + article["text"][:3000])
        # 4) voice (aim 45-55 s)
        allL = lines + [{"text": CTA, "visual": ""}]
        T, engine = tts.synth(allL, work, speed=0.92)
        total = sum(l["dur"] for l in T) + 0.2 * len(T) + 1.15
        log(f"duration {total:.1f}s, {words(lines)} words, voice={engine}")
        if total > 58.5:
            T, engine = tts.synth(allL, work, speed=0.92 * total / 55.0)
            total = sum(l["dur"] for l in T) + 0.2 * len(T) + 1.15
            log(f"re-timed duration {total:.1f}s")
        # 5) visuals
        extra = [q for q in [story.get("searchable_name", ""), sc.get("tag", "").title()] if q]
        imgs, credits = images.gather(lines, extra, work + "/img", article)
        rthumb = os.path.join(work, "related.jpg")
        for q in ("maxresdefault", "hqdefault"):
            try:
                rr = requests.get(f"https://i.ytimg.com/vi/{rel['id']}/{q}.jpg", timeout=20)
                if rr.status_code == 200 and len(rr.content) > 5000:
                    open(rthumb, "wb").write(rr.content); break
            except Exception:  # noqa
                pass
        # 6) render
        stamp = TEHRAN.strftime("%Y%m%d")
        fname = f"AncientMachines-Short-{stamp}.mp4"
        tag = f"short-{stamp}-r{RUN_NO}"
        overlay = [str(x).upper()[:22] for x in (sc.get("overlay") or [])][:2] or [title.upper()[:22]]
        meta = {"overlay": overlay, "tag": str(sc.get("tag", "")).upper()[:18], "end_question": endq,
                "related_title": rel["title"], "related_thumb": rthumb if os.path.exists(rthumb) else ""}
        dur, poster = render.render(T, imgs, meta, f"out/{fname}", work)
        shutil.copy(poster, "docs/poster.jpg")
        size_mb = round(os.path.getsize(f"out/{fname}") / 1e6, 1)
        # 7) packaging
        src_line = f"Source: {story['source']}, {article['url']}"
        desc = (sc.get("description") or "").strip()
        if article["url"] not in desc:
            desc += "\n" + src_line
        desc += f"\nFull case file: https://youtu.be/{rel['id']}"
        if credits:
            desc += "\nImages: " + "; ".join(c["credit"].replace("Photo: ", "") for c in credits)
        if any(i["ai"] for i in imgs):
            desc += "\nSome visuals are AI illustrations."
        hashtags = " ".join(h if h.startswith("#") else "#" + h for h in as_list(sc.get("hashtags"), sep=r"[\s,]+") or ["#archaeology", "#Shorts"])
        if "#Shorts" not in hashtags:
            hashtags += " #Shorts"
        desc += "\n" + hashtags
        tags = [t.strip().lstrip("#") for t in as_list(sc.get("tags")) if len(t.strip()) > 1][:15]
        pin = re.split(r"full case file", str(sc.get("pinned_comment") or ""), flags=re.I)[0].strip()
        pin = (pin or endq) + f" Full case file: {rel['title']} (link above)"
        yt_title = f"{title} #Shorts"
        video_url = f"https://github.com/{REPO}/releases/download/{tag}/{fname}"
        release_url = f"https://github.com/{REPO}/releases/tag/{tag}"
        page.update(status="ok", message="", short={
            "title": yt_title, "title_plain": title, "hook": lines[0]["text"], "overlay": overlay,
            "script": [l["text"] for l in T], "description": desc, "tags": tags, "tags_csv": ", ".join(tags),
            "pinned_comment": pin, "end_question": endq,
            "related_video": {"id": rel["id"], "title": rel["title"], "url": f"https://youtu.be/{rel['id']}"},
            "source": {"name": story["source"], "url": article["url"], "headline": story["title"], "published": story["published"]},
            "duration_s": round(dur, 1), "size_mb": size_mb, "voice": engine, "credits": credits,
            "visuals": ["ai" if i["ai"] else "photo" for i in imgs], "fact_check": [p for p in as_list(chk.get("problems")) if p not in [l["text"] for l in lines]][:5],
            "video_url": video_url, "release_url": release_url, "poster": "poster.jpg", "file": fname,
            "model": llm.USAGE["model_used"]})
        page["archive"] = [{"date": page["date"], "title": yt_title, "release_url": release_url, "video_url": video_url}] + \
                          [a for a in page["archive"] if a.get("release_url") != release_url][:13]
        hist.append({"date": page["date"], "title": story["title"], "title_key": news.title_key(story["title"]),
                     "link": story["link"], "resolved": article["url"], "yt_title": yt_title})
        json.dump(hist[-300:], open(HIST_F, "w"), indent=1, ensure_ascii=False)
        notes = (f"**{yt_title}**\n\nHook: {lines[0]['text']}\n\nSource: [{story['source']}]({article['url']})\n\n"
                 f"Duration {dur:.1f}s · voice {engine} · model {llm.USAGE['model_used']}\n\nPage: https://ghasemiarash813.github.io/am-short-factory/")
        open("out/notes.md", "w").write(notes)
        open("out/release.env", "w").write(f'TAG="{tag}"\nFILE="{fname}"\nTITLE="{yt_title.replace(chr(34), "")}"\n')
        return page, 0
    except Exception as e:  # noqa
        traceback.print_exc()
        page.update(status="error", message=f"{type(e).__name__}: {e}"[:400])
        if prev.get("short"):
            page["last_ok"] = {"date": prev.get("date"), "short": prev["short"]}
        elif prev.get("last_ok"):
            page["last_ok"] = prev["last_ok"]
        return page, 1


if __name__ == "__main__":
    page, code = main()
    page["llm_calls"] = llm.USAGE["calls"]; page["llm_errors"] = llm.USAGE["errors"][-5:]
    json.dump(page, open("docs/today.json", "w"), indent=1, ensure_ascii=False)
    log("status", page["status"], page.get("message", ""))
    sys.exit(code)
