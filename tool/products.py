"""Produktliste laden, bewerten und auswählen.

Score = erwartete Provision pro Verkauf
        × Nachfrage (Verkaufszahl, logarithmisch)
        × Trend (1–5 aus deiner Liste)
        × Preis-Faktor (Spontankauf-Bereich)
        × Frische (wie oft/kürzlich schon gepostet)
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import HISTORY_FILE, ROOT, Config


@dataclass
class Product:
    id: str
    name: str
    price: float
    commission_pct: float
    sold: int
    trend: int
    category: str
    features: list[str]
    images: list[str]
    active: bool
    note: str = ""
    score: float = 0.0
    score_parts: dict = field(default_factory=dict)

    @property
    def commission_eur(self) -> float:
        return self.price * self.commission_pct / 100


def _num(value: str, default: float = 0.0) -> float:
    value = (value or "").strip().replace("€", "").replace("%", "").replace(" ", "")
    if not value:
        return default
    # deutsches Format 1.234,56 → 1234.56
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".")
    else:
        value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return default


def _slug(text: str) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40] or "produkt"


def _split(value: str, sep: str) -> list[str]:
    return [p.strip() for p in (value or "").split(sep) if p.strip()]


def load_products(cfg: Config) -> list[Product]:
    url = cfg.general.get("produkte_url", "").strip()
    if url:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        text = resp.text
    else:
        text = (ROOT / cfg.general["produkte_datei"]).read_text(encoding="utf-8-sig")

    products: list[Product] = []
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        name = row.get("name", "")
        if not name:
            continue
        active = row.get("aktiv", "ja").lower() not in ("nein", "no", "0", "false", "x")
        products.append(
            Product(
                id=row.get("id") or _slug(name),
                name=name,
                price=_num(row.get("preis_eur", "")),
                commission_pct=_num(row.get("provision_prozent", "")),
                sold=int(_num(row.get("verkauft", ""))),
                trend=int(min(5, max(1, _num(row.get("trend", ""), 3)))),
                category=row.get("kategorie", ""),
                features=_split(row.get("vorteile", ""), ";"),
                images=_split(row.get("bilder", ""), "|"),
                active=active,
                note=row.get("notiz", ""),
            )
        )
    return products


# ---------------------------------------------------------------- Verlauf

def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def save_history(history: list[dict]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- Bewertung

def score_products(products: list[Product], cfg: Config, history: list[dict]) -> list[Product]:
    sc = cfg["produktbewertung"]
    g = cfg.general
    now = datetime.now(timezone.utc)
    cooldown = timedelta(days=g.get("wiederholung_nach_tagen", 4))
    max_videos = g.get("max_videos_pro_produkt", 4)

    for p in products:
        posts = [h for h in history if h.get("product_id") == p.id]
        last = max((datetime.fromisoformat(h["created"]) for h in posts), default=None)

        earning = p.commission_eur
        demand = math.log10(max(p.sold, 0) + 10)            # 10 → 1.0, 1000 → 3.0
        trend = 0.6 + 0.2 * p.trend                          # 1 → 0.8, 5 → 1.6
        if p.price < sc["preis_ideal_min"]:
            price_fit = sc["faktor_zu_billig"]
        elif p.price > sc["preis_ideal_max"]:
            price_fit = sc["faktor_zu_teuer"]
        else:
            price_fit = 1.0
        if len(posts) >= max_videos:
            freshness = 0.0
        elif last and now - last < cooldown:
            freshness = 0.0
        else:
            freshness = 1.0 / (1 + 0.35 * len(posts))      # neue Produkte bevorzugen

        if not p.active or p.price <= 0:
            freshness = 0.0

        p.score = round(earning * demand * trend * price_fit * freshness, 3)
        p.score_parts = {
            "provision_eur": round(earning, 2),
            "nachfrage": round(demand, 2),
            "trend": round(trend, 2),
            "preis": price_fit,
            "frische": round(freshness, 2),
            "videos_bisher": len(posts),
        }
    return sorted(products, key=lambda p: p.score, reverse=True)


def pick_products(products: list[Product], count: int) -> list[Product]:
    return [p for p in products if p.score > 0][:count]
