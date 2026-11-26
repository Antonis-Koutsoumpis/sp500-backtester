"""Copy the data for the web app (GitHub Pages, folder docs/).

Writes docs/data/index_prices.csv, docs/data/metadata.json, docs/data/indices.json
(the index list from indices.py) and docs/data/bear_markets.json (bear_markets.py). The daily GitHub Action runs this after
update_data.py, so the web app uses the same data as the Streamlit app.

Run:  python scripts/export_web.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from indices import CURRENCY_SYMBOL, INDICES  # noqa: E402
from bear_markets import BEAR_MARKETS  # noqa: E402

OUT = ROOT / "docs" / "data"
OUT.mkdir(parents=True, exist_ok=True)
shutil.copyfile(ROOT / "data" / "index_prices.csv", OUT / "index_prices.csv")
meta = ROOT / "data" / "metadata.json"
if meta.exists():
    shutil.copyfile(meta, OUT / "metadata.json")
(OUT / "indices.json").write_text(json.dumps(
    {"indices": INDICES, "currency_symbol": CURRENCY_SYMBOL}, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "bear_markets.json").write_text(json.dumps(
    [dict(zip(["peak", "trough", "decline", "label", "cause"], b)) for b in BEAR_MARKETS],
    ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {OUT}")
