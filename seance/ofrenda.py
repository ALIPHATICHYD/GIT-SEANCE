"""Renders a remembrance as a single, offline HTML ofrenda. No CDNs, no trackers."""

from __future__ import annotations

import html
import re

from . import git

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ofrenda for {name}</title>
<style>
  :root {{ --night:#1b1026; --paper:#2a1838; --marigold:#ff9f1c; --rose:#e84a76; --bone:#f6ead7; --candle:#ffd36e; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:radial-gradient(ellipse at top, #3a1f4d 0%, var(--night) 60%); color:var(--bone);
         font:17px/1.6 Georgia, "Times New Roman", serif; min-height:100vh; }}
  .picado {{ display:flex; justify-content:center; gap:4px; padding-top:8px; }}
  .picado span {{ width:64px; height:54px; clip-path:polygon(0 0,100% 0,100% 78%,88% 100%,75% 78%,62% 100%,50% 78%,38% 100%,25% 78%,12% 100%,0 78%);
                  opacity:.9; }}
  .picado span:nth-child(4n+1) {{ background:var(--rose); }} .picado span:nth-child(4n+2) {{ background:var(--marigold); }}
  .picado span:nth-child(4n+3) {{ background:#7bc96f; }} .picado span:nth-child(4n) {{ background:#5fa8e8; }}
  main {{ max-width:720px; margin:0 auto; padding:24px 16px 64px; }}
  .portrait {{ text-align:center; margin:24px 0 8px; }}
  .portrait .frame {{ display:inline-block; padding:18px 28px; border:3px solid var(--marigold); border-radius:50% / 40%;
                      background:var(--paper); box-shadow:0 0 40px rgba(255,159,28,.35); }}
  .portrait .name {{ font-size:28px; color:var(--candle); }}
  .portrait .dates {{ font-size:14px; opacity:.75; font-family:ui-monospace, Menlo, monospace; }}
  .stats {{ display:flex; flex-wrap:wrap; justify-content:center; gap:10px; margin:16px 0 28px; }}
  .stats div {{ background:var(--paper); border:1px solid #4b2d60; border-radius:10px; padding:8px 14px; font-size:14px; }}
  .stats b {{ color:var(--marigold); font-size:18px; display:block; }}
  h2 {{ color:var(--marigold); font-weight:normal; border-bottom:1px dashed #6b4380; padding-bottom:4px; margin-top:32px; }}
  blockquote {{ border-left:3px solid var(--rose); margin:12px 0; padding:4px 16px; font-style:italic; background:rgba(255,255,255,.03); }}
  code {{ font-family:ui-monospace, Menlo, monospace; font-size:14px; background:rgba(255,255,255,.08); padding:1px 5px; border-radius:4px; }}
  li {{ margin:4px 0; }}
  .candles {{ text-align:center; font-size:30px; letter-spacing:18px; margin-top:40px; }}
  .candles span {{ display:inline-block; animation:flicker 2.4s infinite alternate; }}
  .candles span:nth-child(2) {{ animation-delay:.7s; }} .candles span:nth-child(3) {{ animation-delay:1.3s; }}
  @keyframes flicker {{ 0% {{ opacity:1; transform:scale(1); }} 50% {{ opacity:.75; transform:scale(.96) rotate(-2deg); }} 100% {{ opacity:1; transform:scale(1.03); }} }}
  @media (prefers-reduced-motion: reduce) {{ .candles span {{ animation:none; }} }}
  footer {{ text-align:center; font-size:13px; opacity:.6; margin-top:28px; }}
</style>
</head>
<body>
<div class="picado">{picado}</div>
<main>
  <div class="portrait"><div class="frame">
    <div class="name">{name}</div>
    <div class="dates">{first} – {last}</div>
  </div></div>
  <div class="stats">
    <div><b>{commits}</b>commits</div>
    <div><b>{lines}</b>lines still running</div>
    <div><b>{night}</b>written after 10pm</div>
    <div><b>{day}</b>favorite day</div>
  </div>
  {body}
  <div class="candles"><span>🕯️</span><span>🌼</span><span>🕯️</span></div>
  <footer>Remembered by git-seance with a local open-weight model ({model}). Nothing left this machine.</footer>
</main>
</body>
</html>
"""


def _inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def markdown(md: str) -> str:
    """Just enough Markdown for a remembrance: headings, quotes, lists, paragraphs."""
    out, para, items, quote = [], [], [], []

    def flush():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            items.clear()
        if quote:
            out.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            quote.clear()

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("#"):
            flush()
            level = min(3, max(2, len(s) - len(s.lstrip("#"))))
            out.append(f"<h{level}>{_inline(s.lstrip('#').strip())}</h{level}>")
        elif s.startswith(">"):
            if para or items:
                flush()
            quote.append(s.lstrip("> ").strip())
        elif re.match(r"^[-*•]\s+", s):
            if para or quote:
                flush()
            items.append(re.sub(r"^[-*•]\s+", "", s))
        else:
            if items or quote:
                flush()
            para.append(s)
    flush()
    return "\n  ".join(out)


def render(r, text: str, model: str = "") -> str:
    sp = r.spirit
    return PAGE.format(
        name=html.escape(sp.name),
        first=f"{git.when(sp.first):%b %Y}",
        last=f"{git.when(sp.last):%b %Y}",
        commits=sp.commits,
        lines=sp.surviving_lines,
        night=f"{r.night_share:.0%}",
        day=r.busiest_day,
        body=markdown(text),
        picado="<span></span>" * 9,
        model=html.escape(model or "open weights"),
    )
