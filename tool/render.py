"""Baut das 9:16-Video: Produktbilder mit Zoom/Schwenk, Wort-für-Wort-Untertitel, Hook, Musik."""
from __future__ import annotations

import hashlib
import math
import random
import subprocess
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .config import ASSETS_DIR, OUTPUT_DIR, Config
from .products import Product
from .script import VideoScript
from .tts import Word

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg-Fehler:\n{res.stderr[-1500:]}")


# ---------------------------------------------------------------- Bilder

def load_images(product: Product) -> list[Image.Image]:
    """Bilder aus assets/products/<id>/ und/oder den Bild-Links der Produktliste."""
    images: list[Image.Image] = []
    folder = ASSETS_DIR / "products" / product.id
    if folder.is_dir():
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in IMAGE_EXT:
                images.append(Image.open(f))

    cache = OUTPUT_DIR / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for url in product.images:
        target = cache / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".img")
        try:
            if not target.exists():
                r = requests.get(url, headers=UA, timeout=30)
                r.raise_for_status()
                target.write_bytes(r.content)
            images.append(Image.open(BytesIO(target.read_bytes())))
        except Exception as exc:
            print(f"  ⚠ Bild nicht ladbar ({url[:60]}…): {exc}")

    images = [ImageOps.exif_transpose(im).convert("RGB") for im in images]
    if not images:
        raise RuntimeError(
            f"Keine Bilder für '{product.name}'. Lege Bilder in assets/products/{product.id}/ "
            "oder trage Bild-Links in die Spalte 'bilder' ein."
        )
    return images


def compose_frame(img: Image.Image, w: int, h: int) -> Image.Image:
    """Produkt mittig mit Schatten, Hintergrund = unscharfe, abgedunkelte Version des Bildes."""
    bg = ImageOps.fit(img, (w, h), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(45))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)

    box_w, box_h = int(w * 0.86), int(h * 0.46)
    fg = ImageOps.contain(img, (box_w, box_h), Image.LANCZOS)
    radius = 42
    mask = Image.new("L", fg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *fg.size], radius, fill=255)

    cx, cy = w // 2, int(h * 0.46)
    x, y = cx - fg.width // 2, cy - fg.height // 2

    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [x + 10, y + 24, x + fg.width + 10, y + fg.height + 24], radius, fill=(0, 0, 0, 150)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(28))

    frame = bg.convert("RGBA")
    frame.alpha_composite(shadow)
    frame.paste(fg, (x, y), mask)
    return frame.convert("RGB")


# ---------------------------------------------------------------- Bewegte Segmente

MOVES = ["zoom_in", "pan_right", "zoom_out", "pan_left"]


def _zoompan(move: str, frames: int) -> str:
    n = max(frames - 1, 1)
    p = f"(on/{n})"
    center_x, center_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if move == "zoom_in":
        z, x, y = f"1+0.12*{p}", center_x, center_y
    elif move == "zoom_out":
        z, x, y = f"1.12-0.12*{p}", center_x, center_y
    elif move == "pan_right":
        z, x, y = "1.10", f"(iw-iw/zoom)*{p}", center_y
    else:  # pan_left
        z, x, y = "1.10", f"(iw-iw/zoom)*(1-{p})", center_y
    return f"zoompan=z='{z}':x='{x}':y='{y}':d=1"


def render_segment(frame_png: Path, out: Path, dur: float, move: str, cfg: Config) -> None:
    v = cfg["video"]
    w, h, fps = v["breite"], v["hoehe"], v["fps"]
    frames = max(int(round(dur * fps)), 2)
    vf = (
        f"scale={int(w * 1.5)}:{int(h * 1.5)},"
        f"{_zoompan(move, frames)}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p"
    )
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(fps), "-i", str(frame_png),
        "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out),
    ])


# ---------------------------------------------------------------- Untertitel (ASS)

def _t(sec: float) -> str:
    sec = max(sec, 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _chunks(words: list[Word], max_words: int = 3) -> list[list[Word]]:
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w.text[-1:] in ".!?,:;":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(script: VideoScript, words: list[Word], total: float, cfg: Config) -> str:
    v = cfg["video"]
    w, h = v["breite"], v["hoehe"]
    font = v.get("schrift", "DejaVu Sans")
    hl = v.get("markierung_farbe", "&H0000E5FF&")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,2,70,70,{int(h * 0.255)},1
Style: Hook,{font},76,&H00111111,&H00111111,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,3,22,0,8,90,90,{int(h * 0.105)},1
Style: End,{font},92,&H00111111,&H00111111,&H0000E5FF,&H00000000,-1,0,0,0,100,100,0,0,3,26,0,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    # Hook oben in den ersten Sekunden (ist auch das Vorschaubild)
    hook_end = min(3.2, total * 0.4)
    events.append(f"Dialogue: 2,{_t(0)},{_t(hook_end)},Hook,,0,0,0,,{{\\fad(0,250)}}{_esc(script.hook)}")

    # Wort-für-Wort-Untertitel
    chunks = _chunks(words)
    for ci, chunk in enumerate(chunks):
        chunk_end = chunk[-1].end + 0.12
        if ci + 1 < len(chunks):
            chunk_end = min(chunk_end + 0.25, chunks[ci + 1][0].start)
        for wi, word in enumerate(chunk):
            start = word.start
            end = chunk[wi + 1].start if wi + 1 < len(chunk) else chunk_end
            if end <= start:
                continue
            parts = []
            for j, other in enumerate(chunk):
                txt = _esc(other.text)
                parts.append(f"{{\\c{hl}}}{txt}{{\\c&H00FFFFFF&}}" if j == wi else txt)
            pop = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            events.append(f"Dialogue: 1,{_t(start)},{_t(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")

    # Call-to-Action am Ende
    end_start = max(total - 2.2, hook_end)
    events.append(
        f"Dialogue: 3,{_t(end_start)},{_t(total)},End,,0,0,0,,"
        f"{{\\fad(150,0)\\fscx80\\fscy80\\t(0,160,\\fscx100\\fscy100)}}{_esc(script.end_text)}"
    )
    return header + "\n".join(events) + "\n"


# ---------------------------------------------------------------- Musik

def pick_music() -> Path | None:
    folder = ASSETS_DIR / "music"
    tracks = [p for p in folder.glob("*") if p.suffix.lower() in {".mp3", ".m4a", ".wav", ".ogg"}] if folder.is_dir() else []
    return random.choice(tracks) if tracks else None


# ---------------------------------------------------------------- Gesamtvideo

def render_video(
    product: Product, script: VideoScript, voice: Path, words: list[Word], voice_dur: float,
    workdir: Path, out: Path, cfg: Config,
) -> Path:
    v = cfg["video"]
    w, h = v["breite"], v["hoehe"]
    total = round(voice_dur + 0.9, 2)

    # 1) Standbilder vorbereiten
    images = load_images(product)
    frames = []
    for i, img in enumerate(images[:6]):
        p = workdir / f"frame_{i}.png"
        compose_frame(img, w, h).save(p)
        frames.append(p)

    # 2) Schnitte alle ~2,4 s, Bilder & Bewegungen abwechseln
    n_seg = max(len(frames), math.ceil(total / 2.4))
    seg_dur = total / n_seg
    seg_list = workdir / "segments.txt"
    lines = []
    start_move = random.randrange(len(MOVES))
    for i in range(n_seg):
        seg = workdir / f"seg_{i:02d}.mp4"
        render_segment(frames[i % len(frames)], seg, seg_dur + 0.04, MOVES[(start_move + i) % len(MOVES)], cfg)
        lines.append(f"file '{seg.name}'")
    seg_list.write_text("\n".join(lines) + "\n")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", seg_list.name,
          "-c", "copy", "slides.mp4"], cwd=workdir)

    # 3) Untertitel
    (workdir / "subs.ass").write_text(build_ass(script, words, total, cfg), encoding="utf-8")

    # 4) Zusammenfügen: Bild + Untertitel + Stimme (+ Musik)
    music = pick_music()
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", "slides.mp4", "-i", str(voice.resolve())]
    if music:
        vol = v.get("musik_lautstaerke", 0.12)
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]
        af = (f"[1:a]apad,atrim=0:{total}[vo];"
              f"[2:a]volume={vol},atrim=0:{total},afade=t=out:st={total - 1}:d=1[mu];"
              f"[vo][mu]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        af = f"[1:a]apad,atrim=0:{total}[a]"
    cmd += [
        "-filter_complex", f"[0:v]ass=subs.ass[v];{af}",
        "-map", "[v]", "-map", "[a]", "-t", str(total),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(v["fps"]),
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(out.resolve()),
    ]
    _run(cmd, cwd=workdir)
    return out
