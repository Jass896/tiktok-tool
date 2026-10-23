"""Voiceover mit den kostenlosen Microsoft-Edge-Stimmen (edge-tts) inkl. Wort-Zeitstempeln."""
from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Word:
    text: str
    start: float
    end: float


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def estimate_words(text: str, duration: float, offset: float = 0.0) -> list[Word]:
    """Fallback: verteilt Wörter nach Buchstabenanzahl über die Dauer."""
    tokens = text.split()
    weights = [len(re.sub(r"\W", "", t)) + 2 for t in tokens]
    total = sum(weights) or 1
    t = offset
    words = []
    for tok, w in zip(tokens, weights):
        d = duration * w / total
        words.append(Word(tok, t, t + d))
        t += d
    return words


async def _edge(text: str, voice: str, rate: str, out: Path) -> list[Word]:
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words: list[Word] = []
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                words.append(Word(chunk["text"], start, start + chunk["duration"] / 10_000_000))
    return words


def _attach_punctuation(spoken: list[Word], text: str) -> list[Word]:
    """edge-tts liefert Wörter ohne Satzzeichen – hängt sie wieder an (für schönere Untertitel)."""
    tokens = text.split()
    result, ti = [], 0
    for w in spoken:
        clean = re.sub(r"\W", "", w.text).lower()
        found = None
        for j in range(ti, min(ti + 4, len(tokens))):
            if re.sub(r"\W", "", tokens[j]).lower() == clean:
                found = j
                break
        if found is not None:
            result.append(Word(tokens[found].strip("\"„“"), w.start, w.end))
            ti = found + 1
        else:
            result.append(w)
    return result


def synthesize(text: str, voice: str, rate: str, out: Path, engine: str = "edge") -> tuple[list[Word], float]:
    """Gibt (Wörter mit Zeiten, Dauer in Sekunden) zurück."""
    if engine == "stumm":  # nur zum Testen ohne Internet
        dur = max(4.0, len(text.split()) / 2.7)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             f"sine=frequency=220:duration={dur}", "-af", "volume=0.05", str(out)],
            check=True,
        )
        return estimate_words(text, dur), dur

    words = asyncio.run(_edge(text, voice, rate, out))
    duration = audio_duration(out)
    if not words:
        words = estimate_words(text, duration)
    else:
        words = _attach_punctuation(words, text)
    return words, duration
