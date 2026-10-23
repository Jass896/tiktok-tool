"""Erstellt Hook, Voiceover-Text, Bildschirm-Titel und Caption für ein Produkt.

Mit ANTHROPIC_API_KEY schreibt Claude die Texte (kostet Bruchteile eines Cents pro Video),
ohne Key werden eingebaute Vorlagen verwendet.
"""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass

import requests

from .config import Config
from .products import Product

# Verschiedene Aufhänger, damit nicht jedes Video gleich klingt
ANGLES = [
    ("problem", "Starte mit einem nervigen Alltagsproblem und zeig das Produkt als Lösung."),
    ("ungläubig", "Starte ungläubig, als hättest du nicht erwartet, dass das Ding so gut ist."),
    ("gründe", "Nenne knapp 3 Gründe, warum man das Produkt haben will."),
    ("geheimtipp", "Tu so, als wäre es ein Geheimtipp, den kaum jemand kennt."),
    ("vorher-nachher", "Beschreibe den Unterschied vorher/nachher im Alltag."),
]


@dataclass
class VideoScript:
    angle: str
    hook: str            # großer Text oben in den ersten Sekunden (ohne Emojis)
    voiceover: str       # gesprochener Text
    end_text: str        # kurzer Text am Ende (Call-to-Action)
    caption: str         # TikTok-Beschreibung inkl. Hashtags
    source: str          # "claude" oder "vorlage"


def _choose_angle(used: list[str]) -> tuple[str, str]:
    unused = [a for a in ANGLES if a[0] not in used]
    return random.choice(unused or ANGLES)


def _cta(cfg: Config) -> tuple[str, str]:
    """(gesprochener CTA, End-Text)"""
    if cfg.general.get("affiliate_aktiv"):
        return ("Den Link findest du direkt im Video.", "Link im Video")
    return ("Folg mir für mehr solche Finds.", "Folg für mehr Finds")


def _caption_tail(cfg: Config, product: Product, tags: list[str]) -> str:
    base = cfg["skript"].get("basis_hashtags", [])
    cat = "#" + re.sub(r"[^a-zäöüß0-9]", "", product.category.lower()) if product.category else ""
    all_tags = []
    for t in [*tags, cat, *base]:
        t = t.strip()
        if t and not t.startswith("#"):
            t = "#" + t
        if t and t.lower() not in (x.lower() for x in all_tags):
            all_tags.append(t)
    tail = " ".join(all_tags[:7])
    if cfg.general.get("affiliate_aktiv"):
        tail = "#Werbung " + tail
    return tail


# ---------------------------------------------------------------- Claude

SYSTEM_PROMPT = """Du schreibst Skripte für kurze TikTok-Produktvideos (Hochformat, Produktbilder + Voiceover).
Regeln:
- Sprache: {sprache}.
- Der Voiceover ist ca. {sekunden} Sekunden lang gesprochen (ungefähr {woerter} Wörter), kurze Sätze, natürlich gesprochen, keine Aufzählungszeichen.
- Erster Satz = starker Hook, der zum Weiterschauen zwingt.
- Erfinde KEINE Eigenschaften, Zahlen, Testergebnisse oder Preise. Nutze nur die angegebenen Vorteile.
- Keine Heilversprechen, keine Garantien, keine Superlative wie "das beste der Welt".
- Der letzte Satz ist exakt: "{cta}"
- "hook" ist ein Bildschirm-Text mit höchstens 6 Wörtern, OHNE Emojis.
- "caption" ist die TikTok-Beschreibung: 1–2 kurze Sätze, gerne 1–2 Emojis, OHNE Hashtags.
- "hashtags": 3 passende, eher spezifische Hashtags ohne #.
Antworte NUR mit JSON: {{"hook": "...", "voiceover": "...", "caption": "...", "hashtags": ["...", "...", "..."]}}"""


def _claude_script(product: Product, cfg: Config, angle: tuple[str, str]) -> dict:
    sk = cfg["skript"]
    spoken_cta, _ = _cta(cfg)
    seconds = sk.get("dauer_sekunden", 22)
    system = SYSTEM_PROMPT.format(
        sprache=sk.get("sprache", "Deutsch"),
        sekunden=seconds,
        woerter=int(seconds * 2.6),
        cta=spoken_cta,
    )
    user = (
        f"Produkt: {product.name}\n"
        f"Kategorie: {product.category or '-'}\n"
        f"Vorteile: {'; '.join(product.features) or '-'}\n"
        f"Aufhänger-Stil: {angle[1]}"
    )
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": sk.get("modell", "claude-haiku-5-5"),
            "max_tokens": 700,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json()["content"] if b.get("type") == "text")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"Keine JSON-Antwort: {text[:200]}")
    data = json.loads(match.group(0))
    for key in ("hook", "voiceover", "caption"):
        if not str(data.get(key, "")).strip():
            raise ValueError(f"Feld {key} fehlt")
    return data


# ---------------------------------------------------------------- Vorlagen

HOOKS = {
    "problem": ["Das nervt dich auch?", "Schluss mit dem Stress", "Endlich gelöst"],
    "ungläubig": ["Ich hab's nicht geglaubt", "Warum hat mir das keiner gesagt?", "Ehrlich jetzt?"],
    "gründe": ["3 Gründe für das Ding", "Darum lieben es alle", "Kurz erklärt"],
    "geheimtipp": ["Kennt fast niemand", "Mein Geheimtipp", "Psst, Geheimtipp"],
    "vorher-nachher": ["Vorher vs. nachher", "So einfach geht's jetzt", "Kleiner Unterschied, großer Effekt"],
}

OPENERS = {
    "problem": "Kennst du das? Ständig dieselbe Nerverei. Genau dafür gibt's das hier: {name}.",
    "ungläubig": "{name}. Ich hab echt nicht gedacht, dass das Ding so praktisch ist.",
    "gründe": "Drei Gründe, warum gerade alle das hier kaufen: {name}.",
    "geheimtipp": "Das hier kennt fast niemand: {name}.",
    "vorher-nachher": "Vorher hat mich das jedes Mal genervt. Jetzt hab ich das hier: {name}.",
}


def _template_script(product: Product, cfg: Config, angle: tuple[str, str]) -> dict:
    spoken_cta, _ = _cta(cfg)
    key = angle[0]
    feats = product.features[:3] or ["es ist super praktisch", "es sieht richtig gut aus"]
    body = []
    connectors = ["Erstens:", "Dazu kommt:", "Und das Beste:"] if key == "gründe" else ["", "Außerdem:", "Und:"]
    for c, f in zip(connectors, feats):
        f = f[0].upper() + f[1:]
        body.append(f"{c} {f}.".strip())
    voice = " ".join([OPENERS[key].format(name=product.name), *body, spoken_cta])
    return {
        "hook": random.choice(HOOKS[key]),
        "voiceover": re.sub(r"\s+", " ", voice),
        "caption": f"{product.name} – {feats[0]} 👀",
        "hashtags": [],
    }


# ---------------------------------------------------------------- öffentlich

def make_script(product: Product, cfg: Config, used_angles: list[str]) -> VideoScript:
    angle = _choose_angle(used_angles)
    source = "vorlage"
    data = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            data = _claude_script(product, cfg, angle)
            source = "claude"
        except Exception as exc:  # Netzwerk, Kontingent, Format …
            print(f"  ⚠ Claude-Skript fehlgeschlagen ({exc}) – nutze Vorlage")
    if data is None:
        data = _template_script(product, cfg, angle)

    _, end_text = _cta(cfg)
    hook = re.sub(r"[^\w\s?!.,'’\-äöüÄÖÜß]", "", data["hook"]).strip()
    caption = f"{data['caption'].strip()}\n\n{_caption_tail(cfg, product, data.get('hashtags', []))}"
    return VideoScript(
        angle=angle[0],
        hook=hook,
        voiceover=data["voiceover"].strip(),
        end_text=end_text,
        caption=caption,
        source=source,
    )
