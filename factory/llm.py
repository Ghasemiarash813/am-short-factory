"""LLM access. GitHub Models was retired on 30 Jul 2026, so the factory runs its own free model:
Qwen3-4B-Instruct-2507 (GGUF, Apache-2.0) served by llama.cpp's llama-server on the Actions runner
(OpenAI-compatible API at http://127.0.0.1:8080). No keys, no secrets.
Optional: set repo variable LLM_ENDPOINT (+ secret LLM_API_KEY) to use any OpenAI-compatible API instead."""
import json, os, re, time
import requests

LOCAL = "http://127.0.0.1:8080/v1/chat/completions"
USAGE = {"calls": 0, "model_used": None, "errors": [], "endpoint": None}


def log(*a):
    print("[llm]", *a, flush=True)


def _endpoints():
    eps = []
    if os.environ.get("LLM_ENDPOINT"):
        eps.append((os.environ["LLM_ENDPOINT"], os.environ.get("LLM_API_KEY", ""), os.environ.get("LLM_MODEL", "gpt-4o-mini")))
    eps.append((LOCAL, "", "local"))
    return eps


def chat_json(system, user, models=None, max_tokens=1800, temperature=0.4):
    last = None
    for ep, key, model in _endpoints():
        for attempt in range(3):
            try:
                t0 = time.time()
                h = {"Content-Type": "application/json"}
                if key:
                    h["Authorization"] = f"Bearer {key}"
                r = requests.post(ep, timeout=1200, headers=h, json={
                    "model": model, "temperature": temperature, "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                USAGE["calls"] += 1
                if r.status_code == 429:
                    time.sleep(min(int(float(r.headers.get("retry-after", "20"))), 90)); continue
                if r.status_code >= 400:
                    last = f"{ep} HTTP {r.status_code}: {r.text[:300]}"; log(last); USAGE["errors"].append(last[:160]); break
                j = r.json()
                txt = (j["choices"][0]["message"].get("content") or "").strip()
                txt = re.sub(r"^```(json)?|```$", "", txt).strip()
                m = re.search(r"\{.*\}", txt, re.S)
                out = json.loads(m.group(0) if m else txt)
                u = j.get("usage", {})
                log(f"{model} ok in {time.time()-t0:.0f}s, tokens in/out {u.get('prompt_tokens')}/{u.get('completion_tokens')}")
                USAGE["model_used"] = j.get("model") or model; USAGE["endpoint"] = ep
                return out
            except json.JSONDecodeError as e:
                last = f"{model} bad JSON: {e}"; log(last, txt[:200])
            except Exception as e:  # noqa
                last = f"{model} error: {e}"; log(last); time.sleep(5)
    raise RuntimeError(f"LLM failed. Last: {last}")
