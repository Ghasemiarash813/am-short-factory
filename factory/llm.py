"""GitHub Models (free, keyless inside Actions via GITHUB_TOKEN with permissions: models: read)."""
import json, os, re, time
import requests

ENDPOINT = "https://models.github.ai/inference/chat/completions"
USAGE = {"calls": 0, "model_used": None, "errors": []}


def log(*a):
    print("[llm]", *a, flush=True)


def chat_json(system, user, models, max_tokens=1800, temperature=0.4):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_MODELS_TOKEN")
    if not token:
        raise RuntimeError("No GITHUB_TOKEN for GitHub Models")
    last = None
    for model in models:
        for attempt in range(4):
            try:
                r = requests.post(ENDPOINT, timeout=120, headers={
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json",
                    "Accept": "application/json"},
                    json={"model": model, "temperature": temperature, "max_tokens": max_tokens,
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                USAGE["calls"] += 1
                if r.status_code == 429:
                    wait = min(int(float(r.headers.get("retry-after", "20"))), 90)
                    log(f"{model} rate-limited, waiting {wait}s; body: {r.text[:200]}")
                    USAGE["errors"].append(f"{model} 429")
                    if wait >= 90 and attempt >= 1:
                        break
                    time.sleep(wait)
                    continue
                if r.status_code >= 400:
                    last = f"{model} HTTP {r.status_code}: {r.text[:300]}"
                    log(last); USAGE["errors"].append(last[:160])
                    break
                txt = r.json()["choices"][0]["message"]["content"]
                txt = re.sub(r"^```(json)?|```$", "", txt.strip()).strip()
                USAGE["model_used"] = model
                return json.loads(txt)
            except json.JSONDecodeError as e:
                last = f"{model} bad JSON: {e}"; log(last)
                time.sleep(3)
            except Exception as e:  # noqa
                last = f"{model} error: {e}"; log(last)
                time.sleep(5)
    raise RuntimeError(f"All models failed. Last: {last}")
