"""Story ranking, script writing and fact-check prompts (Ancient Machines viral playbook rules)."""
import json
from llm import chat_json

NICHE = ("ancient technology and mechanisms, pyramids, ancient Egypt, tombs and sarcophagi, lost cities, megaliths, "
         "ancient astronomy and alignments, mysterious artifacts, shipwrecks with cargo, geoglyphs, ancient metalwork, "
         "scans/robots/AI/satellites revealing hidden structures, ancient medicine and tools")

RANK_SYS = f"""You pick the single best NEWSJACK story for the YouTube Shorts channel "Ancient Machines" (ancient mysteries, archaeology, ancient tech; audience likes ancient-aliens debates but the channel only reports real evidence).
Good stories: a fresh discovery/finding published in the last 48 hours in this niche: {NICHE}.
Prefer: one big visual OBJECT or PLACE with a searchable name (site, pharaoh, object name, country), a clear "this shouldn't exist / we never knew" tension, credible sources (Live Science, Smithsonian, Phys.org, ScienceDaily, Archaeology Magazine, Reuters, AP, BBC, NatGeo, antiquities ministries, universities, Gizmodo/Arkeonews/Heritage Daily citing an official statement).
Reject: not ancient/archaeology (space-only, animals, modern history, WWII, art market, politics), opinion pieces, listicles/explainers about old finds, evergreen features, dinosaurs/fossils without humans, anything already covered (list given).
Return JSON: {{"ranked":[{{"id":<int>,"score":<0-100>,"why":"<=20 words","searchable_name":"<name people search>"}}]}} with your top 6 best-first (fewer if few qualify; score <40 means it does not really fit)."""

SCRIPT_SYS = """You write one YouTube Short (narration + packaging) for the channel "Ancient Machines" from ONE news article. Hard rules:
- FACTS ONLY FROM THE ARTICLE. No invented numbers, names, dates, places or quotes. If the article hedges ("may", "possibly", "researchers think"), you hedge too. Never claim aliens; you may only ask an open debate question.
- Spoken narration: 6-8 lines, 105-125 words TOTAL (about 45-55 seconds with the closing call to action that is added automatically - do NOT write a CTA).
- Line 1 starts the hook immediately, <=12 words, formula: "Scientists just [found/confirmed] [thing] - and it changes [famous place/idea]." or "This [age]-year-old [object] [does something unexpected]..." Name the object/place in line 1. Never open with "Hey", "Did you know", "Part 2" or any setup.
- Put the most surprising fact (the reveal) at about 60% of the script. Answer the question the hook raises.
- The LAST line MUST be a short debatable question ending with "?" (pattern: "<option A>, <option B>... or something else?"), max 12 words, about THIS story's object.
- Write numbers as words when spoken naturally ("two thousand five hundred years"), plain words, short sentences, no emojis, no hashtags in narration.
- Each line gets "visual": a 2-4 word Wikimedia Commons search query for a REAL photo that fits that line: prefer the named site, region, museum or object type (e.g. "Saqqara necropolis", "Tanis Egypt", "Roman sarcophagus", "Nile delta satellite"). No people's names unless famous historical figures.
- title: <=50 characters BEFORE " #Shorts", searchable name in the first 3 words, plain words with clear tension (e.g. "Buto: Egypt's Buried Complex Seen From Space"). Do not include #Shorts yourself.
- overlay: 2 short uppercase lines shown on the first frame, max 6 words total, naming the object and what is wrong with it (e.g. ["BURIED COMPLEX", "UNDER THE NILE"]).
- tag: 1-2 uppercase words for the place/country (e.g. "EGYPT").
- description: 3-5 sentences: first sentence starts with the searchable name; summarize the facts with hedges; then a line "Source: <source name>, <url>". Do not mention AI. Max 900 chars.
- tags: a JSON ARRAY of 10-15 YouTube tags (lowercase words/phrases, no #), e.g. ["archaeology","ancient egypt","buto"].
- hashtags: a JSON ARRAY of 3 hashtags, e.g. ["#archaeology","#egypt","#Shorts"].
- pinned_comment: the debate question + one extra true detail from the article (do NOT add links or video titles).
- end_question: <=34 characters version of the debate question for the end card.
- facts: list of {"claim": "...", "quote": "exact supporting sentence from the article"} for every factual claim you used.
Return JSON with keys: title, overlay, tag, lines (list of {"text","visual"}), description, tags, hashtags, pinned_comment, end_question, related_video_id, facts."""

CHECK_SYS = """You are a strict fact-checker for a 50-second YouTube Short. Compare every narration line with the article.
A line FAILS if it states a number, date, place, name, or certainty that the article does not support, or drops a hedge the article uses, or claims aliens. Style is not your concern.
If anything fails, rewrite ONLY the failing lines minimally so they are fully supported (keep similar length, keep the same number of lines).
Return JSON: {"ok": true|false, "problems": ["..."], "lines": ["line 1 text", "line 2 text", ...]} (lines = the full corrected list, same count as given)."""


def rank(cands, covered, models):
    lines = []
    for i, c in enumerate(cands[:40]):
        lines.append(f'{i}. [{c["source"]}, {c["age_h"]}h ago] {c["title"]} :: {c["summary"][:150]}')
    user = "Already covered (do not pick the same story):\n- " + "\n- ".join(covered[-40:]) + "\n\nCandidates:\n" + "\n".join(lines)
    res = chat_json(RANK_SYS, user, models, max_tokens=900, temperature=0.2)
    out = []
    for r in res.get("ranked", []):
        try:
            i = int(r["id"])
        except Exception:  # noqa
            continue
        if 0 <= i < len(cands):
            c = dict(cands[i]); c.update(score=r.get("score", 0), why=r.get("why", ""), searchable_name=r.get("searchable_name", ""))
            out.append(c)
    return out


def write_script(story, article, longs, models):
    longs_txt = "\n".join(f'- {l["id"]}: "{l["title"]}" (topics: {l["topics"]})' for l in longs)
    user = (f"Source: {story['source']} | published {story['published']} | URL: {article['url']}\n"
            f"Headline: {story['title']}\n\nRelated long-form videos:\n{longs_txt}\n\nARTICLE TEXT:\n{article['text'][:9000]}")
    return chat_json(SCRIPT_SYS, user, models, max_tokens=2200, temperature=0.5)


def fact_check(article, lines, models):
    user = "ARTICLE:\n" + article["text"][:9000] + "\n\nNARRATION LINES:\n" + json.dumps([l["text"] for l in lines], ensure_ascii=False)
    return chat_json(CHECK_SYS, user, models, max_tokens=1500, temperature=0.0)


EXPAND_SYS = """You lengthen a YouTube Short narration. Keep the same facts style and order, using ONLY facts from the article (add 1-3 more true details from it). Target 110-125 words total in 7-8 lines. Line 1 stays the hook (<=12 words). The last line stays a debatable question ending with "?". No CTA. Return JSON {"lines":[{"text":"...","visual":"2-4 word Wikimedia Commons query"}]}."""


def expand(article, lines, models):
    user = "ARTICLE:\n" + article["text"][:9000] + "\n\nCURRENT LINES:\n" + json.dumps(lines, ensure_ascii=False)
    return chat_json(EXPAND_SYS, user, models, max_tokens=1400, temperature=0.4)
