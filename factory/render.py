"""1080x1920 Short renderer in the Ancient Machines look (port of the channel's PIL+ffmpeg Shorts renderer)."""
import json, os, subprocess, textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, GAP, UH = 1080, 1920, 30, 0.2, 2400
GOLD, WHITE = (255, 214, 64), (255, 255, 255)


def _font(cands, size):
    for c in cands:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default(size)


NIMBUS = ["/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf", "/usr/share/fonts/truetype/urw-base35/NimbusSans-Bold.t1",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
DEJAVU = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
DEJAVU_R = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def log(*a):
    print("[render]", *a, flush=True)


def make_music(T, path, seed=7):
    sr = 44100; n = int(sr * T); out = np.zeros(n); rng = np.random.default_rng(seed)
    A = 49.0; t = np.arange(n) / sr
    for h, amp in [(1, 0.5), (2, 0.25), (3, 0.12), (1.5, 0.18), (4, 0.05)]:
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * t / (23 + h * 7) + h)
        out += amp * lfo * np.sin(2 * np.pi * A * h * t + 0.3 * np.sin(2 * np.pi * 0.05 * t))
    out *= 0.35
    ch = [[0, 3, 7], [-4, 0, 3], [-7, -4, 0], [-5, -1, 2]]
    seg = 12.0; k = 0; pos = 0
    while pos < T:
        L = int(min(seg + 4, T - pos) * sr); s0 = int(pos * sr); tt = np.arange(L) / sr
        env = np.minimum(1, tt / 4) * np.minimum(1, (L / sr - tt) / 4)
        for st in ch[k % 4]:
            f = 220 * 2 ** (st / 12)
            for det in (-4, 0, 4):
                out[s0:s0 + L] += 0.035 * env * np.sin(2 * np.pi * f * 2 ** (det / 1200) * tt)
        if rng.random() < 0.5:
            f = 880 * 2 ** (ch[k % 4][rng.integers(0, 3)] / 12)
            out[s0:s0 + L] += 0.012 * env * np.sin(2 * np.pi * f * tt) * (0.5 + 0.5 * np.sin(2 * np.pi * tt * 0.3))
        for b in np.arange(0, seg, 2.0):
            p = s0 + int(b * sr); D = int(0.6 * sr)
            if p + D < n:
                td = np.arange(D) / sr
                out[p:p + D] += 0.18 * np.sin(2 * np.pi * (48 * np.exp(-td * 4)) * td) * np.exp(-td * 7)
        pos += seg; k += 1
    dl = int(0.13 * sr)
    for i in range(4):
        out[dl * (i + 1):] += out[:-dl * (i + 1)] * (0.3 / (i + 1))
    f = int(4 * sr); out[:f] *= np.linspace(0, 1, f); out[-2 * f:] *= np.linspace(1, 0, 2 * f)
    out = out / np.max(np.abs(out)) * 0.85
    import wave
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((out * 32767).astype(np.int16).tobytes()); w.close()


def render(T, imgs, meta, out_mp4, workdir, preview=False):
    """T: lines with dur/words/wav (last one = CTA, shown on END card). imgs: one dict per non-CTA line."""
    t0 = 0.15
    for s in T:
        s["start"] = t0; t0 += s["dur"] + GAP
    TOTAL = T[-1]["start"] + T[-1]["dur"] + 1.0
    n_body = len(T) - 1
    for i in range(n_body):
        T[i]["img"] = imgs[i]["path"]; T[i]["ai"] = imgs[i]["ai"]; T[i]["credit"] = imgs[i].get("credit", "")
    T[-1]["img"] = "END"

    cache = {}

    def up(path):
        if path not in cache:
            im = Image.open(path).convert("RGB")
            sc = max(UH / im.height, (UH * W / H + 2) / im.width)
            im = im.resize((int(im.width * sc + 0.999), int(im.height * sc + 0.999)), Image.LANCZOS)
            o = (im.height - UH) // 2
            cache[path] = im.crop((0, o, im.width, o + UH))
        return cache[path]

    def ease(x):
        return x * x * (3 - 2 * x)

    # motion per segment: wide images pan, others zoom
    for i in range(n_body):
        im = up(T[i]["img"]); wide = im.width > UH * W / H * 1.35
        if wide:
            T[i].update(pan="lr" if i % 2 == 0 else "rl", z0=1.0, z1=1.06)
        else:
            T[i].update(pan="in", z0=1.0 if i % 2 == 0 else 1.18, z1=1.18 if i % 2 == 0 else 1.0)

    def frame_img(s, p):
        im = up(s["img"]); iw = im.width
        z = s["z0"] + (s["z1"] - s["z0"]) * ease(p)
        h = UH / z; w = h * W / H; cy = UH / 2
        if s["pan"] in ("lr", "rl"):
            a, b = (0.2, 0.8) if s["pan"] == "lr" else (0.8, 0.2)
            q = a + (b - a) * ease(p); cx = w / 2 + (iw - w) * q
        else:
            cx = 0.5 * iw
        cx = min(max(cx, w / 2), iw - w / 2); cy = min(max(cy, h / 2), UH - h / 2)
        return im.resize((W, H), Image.BILINEAR, box=(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))

    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
    vig = np.clip(1 - 0.55 * np.clip(r - 0.35, 0, 1) ** 1.5, 0, 1)
    grad = np.clip((yy - H * 0.55) / (H * 0.45), 0, 1) * 0.35
    mult = (vig * (1 - grad))[..., None].astype(np.float32)

    F = _font(NIMBUS, 92); FS = _font(NIMBUS, 40); FE = _font(DEJAVU, 74); FH = _font(NIMBUS, 112)
    FT = _font(NIMBUS, 36); FQ = _font(DEJAVU, 46); FC = _font(DEJAVU_R, 24)

    chunks = []
    for s in T[:-1] + [T[-1]]:
        ws = s["words"]; cur = []
        for i, (a, b, tx) in enumerate(ws):
            cur.append((s["start"] + a, s["start"] + b, tx))
            if len(cur) >= 3 or tx[-1:] in ",.:?!" or i + 1 == len(ws) or (len(cur) >= 2 and len("".join(c[2] for c in cur)) > 12):
                chunks.append(cur); cur = []
    for i, c in enumerate(chunks):
        end = chunks[i + 1][0][0] if i + 1 < len(chunks) else c[-1][1] + 0.3
        chunks[i] = (c, c[0][0], min(end, c[-1][1] + 0.6))

    def draw_caption(d, t):
        if t < 1.7:
            return
        for words, a, b in chunks:
            if a <= t < b:
                toks = [w[2].upper().rstrip(",") for w in words]
                sp = d.textlength(" ", font=F); widths = [d.textlength(x, font=F) for x in toks]
                lines = [[]]; lw = 0
                for k, wd in enumerate(widths):
                    if lines[-1] and lw + sp + wd > 940:
                        lines.append([]); lw = 0
                    lw += (sp if lines[-1] else 0) + wd; lines[-1].append(k)
                y = 1300 - (len(lines) - 1) * 55
                for ln in lines:
                    tw = sum(widths[k] for k in ln) + sp * (len(ln) - 1); x = (W - tw) / 2
                    for k in ln:
                        active = words[k][0] <= t < words[k][1] + 0.05
                        d.text((x, y), toks[k], font=F, fill=GOLD if active else WHITE, stroke_width=9, stroke_fill=(0, 0, 0))
                        x += widths[k] + sp
                    y += 110
                return

    logo = Image.open("assets/logo.png").convert("RGBA").resize((360, 360), Image.LANCZOS)
    thumb = None
    if meta.get("related_thumb") and os.path.exists(meta["related_thumb"]):
        thumb = Image.open(meta["related_thumb"]).convert("RGB").resize((1000, 563), Image.LANCZOS)

    def end_card():
        bg = up(T[0]["img"]); h = UH; w = h * W / H; cx = bg.width * 0.5
        im = bg.resize((W, H), Image.BILINEAR, box=(cx - w / 2, 0, cx + w / 2, h)).filter(ImageFilter.GaussianBlur(18))
        im = Image.fromarray((np.asarray(im).astype(np.float32) * 0.33).astype(np.uint8))
        im.paste(logo, (W // 2 - 180, 420), logo); d = ImageDraw.Draw(im)
        for i, tx in enumerate(["FULL CASE FILE \u2193", "LINK BELOW", "ANCIENT MACHINES"]):
            tw = d.textlength(tx, font=FE)
            d.text(((W - tw) / 2, 850 + i * 100), tx, font=FE, fill=GOLD if i != 1 else WHITE, stroke_width=6, stroke_fill=(0, 0, 0))
        tx = "Case file: " + meta.get("related_title", "Ancient Machines")
        f = FS
        while d.textlength(tx, font=f) > 1000 and f.size > 24:
            f = _font(NIMBUS, f.size - 2)
        tw = d.textlength(tx, font=f); d.text(((W - tw) / 2, 1180), tx, font=f, fill=(235, 235, 235))
        q = meta.get("end_question", "What do you think?")
        qlines = textwrap.wrap(q, 26)[:2] + ["Comment below."]
        for i, tx in enumerate(qlines):
            tw = d.textlength(tx, font=FQ)
            d.text(((W - tw) / 2, 1290 + i * 64), tx, font=FQ, fill=WHITE, stroke_width=4, stroke_fill=(0, 0, 0))
        return im

    tag = ("NEW  |  " + meta.get("tag", "")).strip(" |")

    def overlays(d, t, s):
        y = 215; x0 = W / 2 - d.textlength(tag, font=FT) / 2; nw = d.textlength("NEW", font=FT)
        d.rounded_rectangle((x0 - 12, y - 6, x0 + nw + 12, y + 44), 8, fill=(200, 30, 30))
        d.text((x0, y), "NEW", font=FT, fill=WHITE)
        d.text((x0 + nw + 16, y), tag[3:].lstrip(), font=FT, fill=WHITE, stroke_width=3, stroke_fill=(0, 0, 0))
        lab = "AI visual" if s.get("ai") else "Archive photo"
        tw = d.textlength(lab, font=FT); xx = W - tw - 50; yy2 = 300
        d.rounded_rectangle((xx - 14, yy2 - 6, xx + tw + 14, yy2 + 44), 8, outline=(220, 220, 220), width=2)
        d.text((xx, yy2), lab, font=FT, fill=(230, 230, 230), stroke_width=2, stroke_fill=(0, 0, 0))
        if s.get("credit"):
            cr = s["credit"]; fc = FC
            while d.textlength(cr, font=fc) > 1000 and fc.size > 16:
                fc = _font(DEJAVU_R, fc.size - 1)
            tw = d.textlength(cr, font=fc)
            d.text(((W - tw) / 2, 1835), cr, font=fc, fill=(215, 215, 215), stroke_width=2, stroke_fill=(0, 0, 0))
        if t < 1.7:
            sc = min(1, 0.85 + t / 0.15 * 0.15) if t < 0.15 else 1
            f = FH if sc >= 1 else _font(NIMBUS, int(112 * sc))
            for k, tx in enumerate(meta.get("overlay", [])[:2]):
                ff = f
                while d.textlength(tx, font=ff) > 1000 and ff.size > 50:
                    ff = _font(NIMBUS, ff.size - 4)
                tw = d.textlength(tx, font=ff)
                d.text(((W - tw) / 2, 900 + k * 135), tx, font=ff, fill=GOLD if k == 1 else WHITE, stroke_width=11, stroke_fill=(0, 0, 0))

    def seg_at(t):
        idx = 0
        for i, s in enumerate(T):
            if t >= s["start"] - 1e-4:
                idx = i
        return idx

    endc = [None]

    def base(i, t):
        s = T[i]
        if s["img"] == "END":
            if endc[0] is None:
                endc[0] = end_card()
            return np.asarray(endc[0]).astype(np.float32), True
        s_end = T[i + 1]["start"] if i + 1 < len(T) else TOTAL
        st = s["start"] if i > 0 else 0
        p = (t - st) / (s_end - st + 0.3)
        return np.asarray(frame_img(s, min(max(p, 0), 1))).astype(np.float32), False

    def compose(t):
        i = seg_at(t); a, isend = base(i, t)
        if not isend:
            a = a * mult
        if i > 0 and t - T[i]["start"] < 0.3:
            b, be = base(i - 1, t)
            if not be:
                b = b * mult
            k = (t - T[i]["start"]) / 0.3; a = a * k + b * (1 - k)
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im)
        if isend and thumb is not None and t - T[i]["start"] < 0.7:
            im.paste(thumb, (40, 560)); d = ImageDraw.Draw(im); d.rectangle((40, 560, 1040, 1123), outline=GOLD, width=6)
        if not isend:
            tx = "ANCIENT MACHINES"; tw = d.textlength(tx, font=FS)
            d.text(((W - tw) / 2, 150), tx, font=FS, fill=(230, 200, 120), stroke_width=3, stroke_fill=(0, 0, 0))
            overlays(d, t, T[i])
            draw_caption(d, t)
        return im

    poster = os.path.join(workdir, "poster.jpg")
    compose(0.6).save(poster, quality=85)
    if preview:
        for j, tt in enumerate([0.6, T[min(2, n_body - 1)]["start"] + 1.5, T[-1]["start"] + 0.2, T[-1]["start"] + 1.5]):
            compose(tt).resize((540, 960)).save(os.path.join(workdir, f"prev{j}.jpg"))
        return TOTAL, poster

    N = int(TOTAL * FPS)
    vid = os.path.join(workdir, "video.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                           "-pix_fmt", "yuv420p", vid], stdin=subprocess.PIPE)
    for f in range(N):
        t = f / FPS
        im = compose(t)
        if f < 6:
            im = Image.fromarray((np.asarray(im).astype(np.float32) * (0.4 + 0.1 * f)).astype(np.uint8))
        ff.stdin.write(im.tobytes())
        if f % 300 == 0:
            log(f, "/", N)
    ff.stdin.close(); ff.wait()

    music = os.path.join(workdir, "music.wav"); make_music(TOTAL, music)
    inputs, filt, labels = [], [], []
    for i, s in enumerate(T):
        inputs += ["-i", s["wav"]]; ms = int(s["start"] * 1000)
        filt.append(f"[{i}:a]aresample=44100,adelay={ms}|{ms}[v{i}]"); labels.append(f"[v{i}]")
    inputs += ["-i", music]; m = len(T)
    fc = ";".join(filt) + f";{''.join(labels)}amix=inputs={len(T)}:normalize=0[vo];[{m}:a]volume=0.16[m];" \
         f"[vo][m]amix=inputs=2:normalize=0:duration=longest,atrim=0:{TOTAL:.3f},loudnorm=I=-14:TP=-1.5[o]"
    audio = os.path.join(workdir, "audio.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + inputs + ["-filter_complex", fc, "-map", "[o]", "-ar", "48000", audio], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    return TOTAL, poster
