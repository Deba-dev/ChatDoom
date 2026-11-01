# Writes the overlay pages to tests/out so overlay_page.test.cjs can check them.  Run from the project folder:  python tests/make_overlay_pages.py
import os, sys
sys.path.insert(0, os.getcwd())
from app.overlay_html import page
out = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(out, exist_ok=True)
for m in ("alert", "chat", "music", "meme", "widgets"):
    open(os.path.join(out, m + ".html"), "w", encoding="utf-8").write(page(m))
print("pages written to", out)
