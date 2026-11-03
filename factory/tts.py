"""Voiceover: the channel's own Kokoro 'narrator' voice (kokoro-onnx + assets/narrator.npy), edge-tts fallback."""
import os, subprocess, asyncio
import numpy as np
import soundfile as sf

MODELS = os.environ.get("KOKORO_DIR", "models")
_k = None


def log(*a):
    print("[tts]", *a, flush=True)


def _word_times(text, d):
    ws = text.split()
    wt = np.array([len(w) + 2 for w in ws], float)
    c = np.cumsum(wt) / wt.sum() * d
    s = np.concatenate([[0], c[:-1]])
    return [[float(s[j]), float(c[j]) - 0.03, w] for j, w in enumerate(ws)]


def kokoro_line(text, path, speed):
    global _k
    from kokoro_onnx import Kokoro
    if _k is None:
        _k = Kokoro(os.path.join(MODELS, "kokoro-v1.0.onnx"), os.path.join(MODELS, "voices-v1.0.bin"))
    v = np.load("assets/narrator.npy")
    a, sr = _k.create(text, voice=v, speed=speed, lang="en-us")
    a = np.concatenate([a, np.zeros(int(sr * 0.05))])
    sf.write(path, a, sr)
    return len(a) / sr


def edge_line(text, path, speed):
    import edge_tts
    rate = f"{int(round((speed - 1) * 100)):+d}%"
    mp3 = path.replace(".wav", ".mp3")
    asyncio.run(edge_tts.Communicate(text, "en-US-ChristopherNeural", rate=rate).save(mp3))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "24000", "-ac", "1", path], check=True)
    a, sr = sf.read(path)
    return len(a) / sr


def synth(lines, workdir, speed=0.92):
    for engine, fn, sp in (("kokoro-narrator", kokoro_line, speed), ("edge-tts", edge_line, speed + 0.02)):
        try:
            out = []
            for i, l in enumerate(lines):
                p = os.path.join(workdir, f"a{i}.wav")
                d = fn(l["text"], p, sp)
                l = dict(l); l["dur"] = d; l["words"] = _word_times(l["text"], d - 0.05); l["wav"] = p
                out.append(l)
                log(engine, i, round(d, 2), l["text"][:60])
            return out, engine
        except Exception as e:  # noqa
            log(engine, "failed:", repr(e))
    raise RuntimeError("all TTS engines failed")
