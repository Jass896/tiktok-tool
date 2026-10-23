#!/usr/bin/env python3
"""TikTok Affiliate Tool – Befehle:

  python run.py rank                    Produkt-Ranking anzeigen
  python run.py make [--count 3]        Videos erstellen (ohne Versand)
  python run.py daily                   Videos erstellen + versenden + Verlauf speichern (für den Zeitplan)
  python run.py telegram-setup          Telegram-Chat-ID finden und Testnachricht senden
  python run.py tiktok-login            Einmalig TikTok verbinden (nur für Versandmodus tiktok_inbox)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from tool import deliver
from tool.config import OUTPUT_DIR, load_config
from tool.products import load_history, load_products, pick_products, save_history, score_products
from tool.render import render_video
from tool.script import make_script
from tool.tts import synthesize


def cmd_rank(cfg, args) -> None:
    ranked = score_products(load_products(cfg), cfg, load_history())
    print(f"{'#':>2}  {'Score':>7}  {'Prov.€':>6}  {'Preis':>6}  {'Verk.':>6}  T  Vid  Produkt")
    for i, p in enumerate(ranked, 1):
        sp = p.score_parts
        flag = "" if p.score > 0 else ("  (inaktiv)" if not p.active else "  (Pause/Limit)")
        print(f"{i:>2}  {p.score:>7.2f}  {sp['provision_eur']:>6.2f}  {p.price:>6.2f}  {p.sold:>6}  "
              f"{p.trend}  {sp['videos_bisher']:>3}  {p.name}{flag}")


def make_videos(cfg, count: int, tts_engine: str, only: str | None = None) -> list[dict]:
    history = load_history()
    ranked = score_products(load_products(cfg), cfg, history)
    chosen = [p for p in ranked if p.id == only] if only else pick_products(ranked, count)
    if not chosen:
        print("Keine passenden Produkte (alle inaktiv, in Pause oder am Limit). Neue Produkte in die Liste eintragen!")
        return []

    day_dir = OUTPUT_DIR / datetime.now().strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    voice_cfg = cfg["stimme"]
    results = []
    for i, product in enumerate(chosen, 1):
        print(f"\n▶ [{i}/{len(chosen)}] {product.name}  (Score {product.score:.2f})")
        used = [h["angle"] for h in history if h.get("product_id") == product.id]
        script = make_script(product, cfg, used)
        print(f"  Aufhänger: {script.angle} · Text: {script.source}")
        print(f"  Hook: {script.hook}")

        stem = f"{datetime.now().strftime('%H%M')}_{i}_{product.id}"
        work = Path(tempfile.mkdtemp(prefix="ttv_"))
        try:
            voice = work / "voice.mp3"
            words, dur = synthesize(script.voiceover, voice_cfg["stimme"], voice_cfg["tempo"], voice, tts_engine)
            print(f"  Voiceover: {dur:.1f} s, {len(words)} Wörter")
            video = render_video(product, script, voice, words, dur, work, day_dir / f"{stem}.mp4", cfg)
        finally:
            shutil.rmtree(work, ignore_errors=True)

        (day_dir / f"{stem}.txt").write_text(
            f"PRODUKT: {product.name}\nHOOK: {script.hook}\n\nCAPTION:\n{script.caption}\n\nVOICEOVER:\n{script.voiceover}\n",
            encoding="utf-8",
        )
        size = video.stat().st_size / 1e6
        print(f"  ✔ {video.relative_to(OUTPUT_DIR.parent)}  ({size:.1f} MB)")
        results.append({"product": product, "script": script, "video": video})
    return results


def deliver_videos(cfg, results: list[dict]) -> list[str]:
    mode = cfg["versand"]["modus"]
    affiliate = cfg.general.get("affiliate_aktiv")
    channels: list[str] = []
    token = None

    if mode == "app":
        if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
            names = "\n".join(f"• {r['product'].name}" for r in results)
            deliver.telegram_send_text(f"🎬 {len(results)} neue Video(s) in ShopClips:\n{names}")
            channels.append("telegram_hinweis")
        return channels

    for i, r in enumerate(results):
        p, s, video = r["product"], r["script"], r["video"]
        when = r["post_time"]
        steps = ["Video speichern & in TikTok hochladen" if mode != "tiktok_inbox" and mode != "beides"
                 else "TikTok öffnen → Posteingang → Entwurf bearbeiten",
                 "Caption aus der nächsten Nachricht kopieren"]
        if affiliate:
            steps += [f"Link hinzufügen → Produkte → „{p.name}“ wählen",
                      "Inhaltsoffenlegung / Werbung einschalten"]
        info = (f"🎬 Video {i + 1}/{len(results)} · {p.name}\n⏰ Posten um ca. {when}\n\n"
                + "\n".join(f"{n}. {t}" for n, t in enumerate(steps, 1)))

        if mode in ("tiktok_inbox", "beides"):
            try:
                token = token or deliver.tiktok_access_token()
                pid = deliver.tiktok_upload_to_inbox(video, token)
                print(f"  ✔ In TikTok-Posteingang geladen ({pid})")
                channels.append("tiktok_inbox")
            except Exception as exc:
                print(f"  ✖ TikTok-Upload fehlgeschlagen: {exc}")
                if mode == "tiktok_inbox":
                    raise

        if mode in ("telegram", "beides"):
            if mode == "telegram":
                deliver.telegram_send_video(video, info)
            else:
                deliver.telegram_send_text(info)
            deliver.telegram_send_text(s.caption)
            print("  ✔ Per Telegram gesendet")
            channels.append("telegram")
    return channels


def cmd_make(cfg, args) -> None:
    make_videos(cfg, args.count or cfg.general["videos_pro_tag"], args.tts, args.product)


def cmd_daily(cfg, args) -> None:
    results = make_videos(cfg, args.count or cfg.general["videos_pro_tag"], args.tts)
    if not results:
        if cfg["versand"]["modus"] != "keiner" and os.environ.get("TELEGRAM_BOT_TOKEN") \
                and os.environ.get("TELEGRAM_CHAT_ID"):
            deliver.telegram_send_text("⚠ Heute keine Videos: alle Produkte sind inaktiv, in Pause oder am Limit. "
                                       "Bitte neue Produkte in die Liste eintragen.")
        return
    times = cfg.general.get("postzeiten", []) or ["heute"]
    for i, r in enumerate(results):
        r["post_time"] = times[i % len(times)]

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Manifest für die App (wird vom Workflow in den Branch "videos" veröffentlicht)
    manifest = [{
        "file": r["video"].name,
        "date": r["video"].parent.name,
        "created": now,
        "product_id": r["product"].id,
        "product": r["product"].name,
        "hook": r["script"].hook,
        "caption": r["script"].caption,
        "post_time": r["post_time"],
        "affiliate": bool(cfg.general.get("affiliate_aktiv")),
        "text_source": r["script"].source,
    } for r in results]
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    channels = [] if cfg["versand"]["modus"] == "keiner" else deliver_videos(cfg, results)

    history = load_history()
    for r in results:
        history.append({
            "created": now,
            "product_id": r["product"].id,
            "product": r["product"].name,
            "angle": r["script"].angle,
            "hook": r["script"].hook,
            "text_source": r["script"].source,
            "video": r["video"].name,
            "delivered": sorted(set(channels)),
        })
    save_history(history)
    print(f"\nFertig: {len(results)} Video(s).")


def cmd_telegram_setup(cfg, args) -> None:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        sys.exit("Bitte zuerst TELEGRAM_BOT_TOKEN setzen (siehe README).")
    chats = deliver.telegram_find_chat_id()
    if not chats:
        sys.exit("Keine Nachricht gefunden. Schreib deinem Bot in Telegram zuerst irgendwas (z. B. /start) und starte das hier neu.")
    for cid, name in chats:
        print(f"Chat-ID: {cid}  ({name})")
    os.environ.setdefault("TELEGRAM_CHAT_ID", str(chats[0][0]))
    deliver.telegram_send_text("✅ Verbindung klappt! Hier kommen ab jetzt deine TikTok-Videos an.")
    print("Testnachricht gesendet. Trag die Chat-ID als Secret TELEGRAM_CHAT_ID ein.")


def cmd_tiktok_login(cfg, args) -> None:
    key, secret = os.environ.get("TIKTOK_CLIENT_KEY"), os.environ.get("TIKTOK_CLIENT_SECRET")
    redirect = os.environ.get("TIKTOK_REDIRECT_URI")
    if not (key and secret and redirect):
        sys.exit("Bitte TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET und TIKTOK_REDIRECT_URI setzen (siehe README).")
    url, state = deliver.tiktok_auth_url(key, redirect)
    print("1) Öffne diesen Link, melde dich an und erlaube den Zugriff:\n\n" + url)
    print("\n2) Danach landest du auf deiner Redirect-Seite. Kopier die KOMPLETTE Adresse aus der Adresszeile.")
    pasted = input("\nAdresse hier einfügen: ").strip()
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(pasted).query)
    if q.get("state", [""])[0] != state:
        sys.exit("State passt nicht – bitte den neuesten Link verwenden.")
    tokens = deliver.tiktok_exchange_code(key, secret, q["code"][0], redirect)
    print("\n✅ Verbunden! Trag das als GitHub-Secret TIKTOK_REFRESH_TOKEN ein:\n")
    print(tokens["refresh_token"])
    print(f"\n(gültig ca. {int(tokens.get('refresh_expires_in', 0)) // 86400} Tage)")


def main() -> None:
    ap = argparse.ArgumentParser(description="TikTok Affiliate Tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rank")
    for name in ("make", "daily"):
        sp = sub.add_parser(name)
        sp.add_argument("--count", type=int, default=0)
        sp.add_argument("--tts", default="edge", choices=["edge", "stumm"],
                        help="stumm = Testton statt Stimme (offline testen)")
        if name == "make":
            sp.add_argument("--product", help="nur dieses Produkt (id) rendern")
    sub.add_parser("telegram-setup")
    sub.add_parser("tiktok-login")
    args = ap.parse_args()

    cfg = load_config()
    {"rank": cmd_rank, "make": cmd_make, "daily": cmd_daily,
     "telegram-setup": cmd_telegram_setup, "tiktok-login": cmd_tiktok_login}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
