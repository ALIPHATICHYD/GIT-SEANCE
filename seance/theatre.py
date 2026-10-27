"""Candlelight for the terminal. Turns itself off for pipes, NO_COLOR, and --plain."""

from __future__ import annotations

import os
import random
import sys
import time
from typing import Iterable

ENABLED = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
SLOW = ENABLED


def configure(plain: bool) -> None:
    global ENABLED, SLOW
    if plain:
        ENABLED = SLOW = False


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if ENABLED else s


def dim(s: str) -> str: return _c("2", s)
def ghost(s: str) -> str: return _c("38;5;153", s)
def blood(s: str) -> str: return _c("38;5;160", s)
def marigold(s: str) -> str: return _c("38;5;214", s)
def moss(s: str) -> str: return _c("38;5;71", s)
def bold(s: str) -> str: return _c("1", s)


CANDLES = r"""
      )        )        )
     (_)      (_)      (_)
     |~|      |~|      |~|
    _|_|______|_|______|_|_
"""


def out(s: str = "") -> None:
    print(s, flush=True)


def pause(seconds: float) -> None:
    if SLOW:
        time.sleep(seconds)


def ritual(steps: Iterable[str]) -> None:
    """Print the incantation lines slowly, like a medium warming up."""
    for step in steps:
        out(dim(f"  {step}"))
        pause(0.45)


def possess(tokens: Iterable[str]) -> str:
    """Stream the spirit's words with a typewriter flicker. Returns the full text."""
    words: list[str] = []
    for tok in tokens:
        words.append(tok)
        if not SLOW:
            sys.stdout.write(tok)
            continue
        for ch in tok:
            if ch.isalpha() and random.random() < 0.012:
                sys.stdout.write(ghost(random.choice("▒░▓")))
                sys.stdout.flush()
                time.sleep(0.06)
                sys.stdout.write("\b")
            sys.stdout.write(ghost(ch))
            sys.stdout.flush()
            time.sleep(0.018 if ch != "." else 0.25)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return "".join(words)


def tombstone(name: str, years: str, lines: int, epitaph: str, width: int = 34) -> list[str]:
    def row(s: str) -> str:
        s = s[: width - 4]
        return " │ " + s.center(width - 4) + " │"
    words, wrapped, cur = epitaph.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width - 6:
            wrapped.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        wrapped.append(cur)
    body = [" ╭" + "─" * (width - 2) + "╮", row("R.I.P."), row(name), row(years), row("")]
    body += [row(w) for w in wrapped] or [row("")]
    body += [row(""), row(f"{lines} lines still haunt HEAD"), " ┴" + "─" * (width - 2) + "┴"]
    return body
