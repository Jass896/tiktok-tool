"""Bereitet den Branch "videos" für die App vor.

Aufruf (im Workflow):  python -m tool.publish <ordner>
<ordner> enthält den bisherigen Stand des Branches (index.json + v/<datum>/*.mp4).
Neue Videos aus output/manifest.json werden hinzugefügt, alte nach X Tagen entfernt.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from .config import OUTPUT_DIR, load_config


def main(target: Path) -> None:
    cfg = load_config()
    keep_days = cfg.raw.get("app", {}).get("videos_behalten_tage", 4)
    index_file = target / "index.json"
    index = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else []

    manifest_file = OUTPUT_DIR / "manifest.json"
    new = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else []
    known = {e["path"] for e in index}
    new = [e for e in new if f"v/{e['date']}/{e['file']}" not in known]
    for entry in new:
        src = OUTPUT_DIR / entry["date"] / entry["file"]
        dest = target / "v" / entry["date"] / entry["file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        entry["path"] = f"v/{entry['date']}/{entry['file']}"
        entry["size"] = dest.stat().st_size
        index.append(entry)

    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    kept = [e for e in index if e["date"] > cutoff and (target / e["path"]).exists()]
    for folder in (target / "v").glob("*") if (target / "v").exists() else []:
        if folder.name <= cutoff:
            shutil.rmtree(folder)

    kept.sort(key=lambda e: (e["created"], e["file"]), reverse=True)
    index_file.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"App-Videos: {len(new)} neu, {len(kept)} insgesamt (behalten: {keep_days} Tage)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
