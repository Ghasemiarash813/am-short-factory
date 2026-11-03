# Ancient Machines — Short Factory (free, automatic)

Every day at ~03:07 UTC (06:37 Tehran) GitHub Actions:
1. pulls fresh archaeology / ancient-tech news (Live Science, Smithsonian, Phys.org, ScienceDaily, Archaeology Magazine, Heritage Daily, Arkeonews, Google News RSS) from the last 48 h (72 h fallback) and drops stories already covered (`data/history.json`);
2. ranks them and writes a ~45–55 s NEWSJACK Short script + title/description/tags/pinned comment with a **self-hosted free model** (Qwen3-4B-Instruct-2507, Apache-2.0, run by llama.cpp on the Actions runner — GitHub Models was retired on 30 Jul 2026), then fact-checks it against the article. Optional: set repo variable `LLM_ENDPOINT`/`LLM_MODEL` + secret `LLM_API_KEY` to use any OpenAI-compatible API instead;
3. voices it with the channel's own Kokoro *narrator* voice (`assets/narrator.npy`, edge-tts fallback), finds freely-licensed Wikimedia Commons photos (credited on screen and in the description; channel B-roll labelled "AI visual" as fallback) and renders a 1080×1920 Short in the channel look;
4. attaches the MP4 to a GitHub Release (last 14 kept) and publishes the Persian dashboard on GitHub Pages: https://ghasemiarash813.github.io/am-short-factory/ (Siri guide: `/siri.html`).

Run now: Actions → *Short Factory* → *Run workflow*. Edit feeds / related long-forms in `factory/config.json`.
Uploading to YouTube stays manual (download → YouTube app → paste title/description/tags → set Related video).
No secrets are stored in this repo.
