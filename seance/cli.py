"""seance: summon, mourn, and remember the people who wrote your code."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

from . import __version__, git, ofrenda as altar, spirit, theatre as t
from .llm import DEFAULT_BACKEND, DEFAULT_HOST, DEFAULT_MODEL, Medium, MediumError


def _rel(path: str) -> str:
    root = git.repo_root(os.path.dirname(os.path.abspath(path)) or ".")
    return os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")


def _speak(medium, messages: list[dict]) -> str:
    try:
        return t.possess(medium.channel(messages))
    except MediumError as e:
        t.out(t.blood(f"\n  The candles gutter out. {e}"))
        sys.exit(2)


def _report_citations(text: str, known: set[str]) -> None:
    cites = spirit.verify(text, known)
    if not cites:
        t.out(t.dim("  (the spirit cited nothing, so trust it accordingly)"))
        return
    for c in cites:
        if c.in_evidence:
            t.out(t.moss(f"  ✓ [{c.token}] is sealed in git history"))
        elif c.real:
            t.out(t.marigold(f"  ~ [{c.token}] is a real commit, but not one the spirit was shown"))
        else:
            t.out(t.blood(f"  ✗ [{c.token}] does not exist. The spirit is lying."))


def cmd_summon(args, medium) -> None:
    m = re.match(r"^(.+):(\d+)$", args.target)
    if not m:
        sys.exit("summon needs FILE:LINE, for example: seance summon src/app.py:42")
    path, line = m.group(1), int(m.group(2))
    root = git.repo_root(os.path.dirname(os.path.abspath(path)) or ".")
    h = spirit.gather(_rel(path), line, cwd=root)
    b, c = h.blame, h.commit

    t.out(t.marigold(t.CANDLES))
    t.ritual([
        f"lighting candles over {h.path}:{h.line} ...",
        f"reading the blame ... the hand that wrote this belonged to {b.author}",
        f"the line was born {spirit.ago(b.time)}, in commit {git.short(c.sha)}",
        f"it has lived {len(h.history)} lives in the log" if len(h.history) > 1 else "nothing has disturbed it since",
        f"channeling {medium.model} through the veil, entirely on this machine ...",
    ])
    t.out()
    t.out(t.dim(f"  >> {b.text.strip()}"))
    t.out(t.dim(f"  evidence: [{git.short(c.sha)}] {c.subject}"))
    t.out()

    messages = spirit.summon_messages(h, args.question)
    reply = _speak(medium, messages)
    t.out()
    _report_citations(reply, h.known_shas)

    if args.once or not sys.stdin.isatty():
        return
    messages.append({"role": "assistant", "content": reply})
    while True:
        try:
            q = input(t.dim("\n  ask the spirit (enter to release it) › ")).strip()
        except (EOFError, KeyboardInterrupt):
            q = ""
        if not q:
            t.out(t.dim("  the candles go out. the spirit returns to the log."))
            return
        messages.append({"role": "user", "content": q})
        t.out()
        reply = _speak(medium, messages)
        messages.append({"role": "assistant", "content": reply})
        t.out()
        _report_citations(reply, h.known_shas)


def cmd_graveyard(args, medium) -> None:
    root = git.repo_root(".")
    t.ritual(["walking the rows of the commit log ...", "counting which lines still breathe in HEAD ..."])
    spirits = git.census(root, args.path or None)
    now = git.latest_commit_time(root)
    departed = sorted((s for s in spirits.values() if s.departed(now, args.days)),
                      key=lambda s: s.surviving_lines, reverse=True)[: args.limit]
    living = len(spirits) - len([s for s in spirits.values() if s.departed(now, args.days)])

    t.out()
    if not departed:
        t.out(t.moss(f"  No one has been gone longer than {args.days} days. The graveyard is empty, for now."))
    else:
        epitaphs = [s.last_words for s in departed]
        if not args.no_epitaphs:
            t.out(t.dim(f"  asking {medium.model} to carve epitaphs ...\n"))
            try:
                text = "".join(medium.channel(spirit.epitaph_messages(departed)))
                epitaphs = [e or s.last_words for e, s in zip(spirit.parse_epitaphs(text, len(departed)), departed)]
            except MediumError as e:
                t.out(t.blood(f"  ({e} Carving their last commit messages instead.)\n"))
        me = git.current_user_email(root)
        for s, ep in zip(departed, epitaphs):
            years = f"{git.when(s.first):%Y} – {git.when(s.last):%Y}"
            for row in t.tombstone(s.name, years, s.surviving_lines, ep):
                t.out(t.ghost(row))
            if s.email == me:
                t.out(t.blood("   ...wait. this grave has your name on it."))
            t.out(t.dim(f"   last words: “{s.last_words}”  ({spirit.ago(s.last, now)})"))
            t.out()

    t.out(t.bold("  The crypt: lines no one has dared to touch"))
    for path, bl in git.oldest_lines(root, args.path or None, top=5):
        t.out(f"  {t.marigold(f'{path}:{bl.final_line}')}  {t.dim(spirit.ago(bl.time))}  {bl.author}")
        t.out(t.dim(f"      {bl.text.strip()[:90]}"))
    t.out()
    t.out(t.dim(f"  {living} living contributor(s), {len(spirits) - living} departed."))
    t.out(t.dim("  Summon one with: seance summon FILE:LINE"))


def cmd_ofrenda(args, medium) -> None:
    root = git.repo_root(".")
    t.ritual(["arranging marigolds ...", "gathering their commits, first and last ..."])
    r = spirit.remember(args.who, root)
    now = int(time.time())
    t.out(t.marigold(f"\n  🌼 An ofrenda for {r.spirit.name} 🌼\n"))
    text = _speak(medium, spirit.ofrenda_messages(r, now))
    _report_citations(text, {r.first.sha, r.last.sha})

    slug = re.sub(r"[^a-z0-9]+", "-", r.spirit.name.lower()).strip("-") or "spirit"
    base = args.output or f"ofrenda-{slug}"
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(text.strip() + "\n")
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(altar.render(r, text, medium.model))
    t.out(t.moss(f"\n  The altar is set: {base}.md and {base}.html"))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="seance", description="Summon the ghosts in your git history with a local open-weight model.")
    p.add_argument("--version", action="version", version=f"git-seance {__version__}")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"local model to channel (default {DEFAULT_MODEL})")
    p.add_argument("--backend", default=DEFAULT_BACKEND, choices=["ollama", "openai"],
                   help="ollama, or any OpenAI-compatible local server such as llama.cpp")
    p.add_argument("--host", default=DEFAULT_HOST, help="server URL (default localhost)")
    p.add_argument("--plain", action="store_true", help="no colors, no flicker, no delays")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("summon", help="summon the ghost who wrote a line")
    s.add_argument("target", help="FILE:LINE")
    s.add_argument("-q", "--question", default="Why do you haunt this line? Why does it exist?")
    s.add_argument("--once", action="store_true", help="one answer, no follow-up questions")
    s.set_defaults(fn=cmd_summon)

    g = sub.add_parser("graveyard", help="tombstones for contributors who have gone quiet")
    g.add_argument("path", nargs="*", help="limit to these paths")
    g.add_argument("--days", type=int, default=365, help="silent this long counts as departed (default 365)")
    g.add_argument("--limit", type=int, default=6)
    g.add_argument("--no-epitaphs", action="store_true", help="skip the model, carve last commit messages")
    g.set_defaults(fn=cmd_graveyard)

    o = sub.add_parser("ofrenda", help="build a Día de los Muertos altar for a contributor")
    o.add_argument("who", help="name or email (partial match is fine)")
    o.add_argument("-o", "--output", help="output path without extension")
    o.set_defaults(fn=cmd_ofrenda)

    args = p.parse_args(argv)
    t.configure(args.plain)
    medium = Medium(model=args.model, backend=args.backend, host=args.host)
    try:
        args.fn(args, medium)
    except git.GitError as e:
        t.out(t.blood(f"  The spirits are silent: {e}"))
        sys.exit(1)
    except KeyboardInterrupt:
        t.out(t.dim("\n  séance interrupted."))
        sys.exit(130)
