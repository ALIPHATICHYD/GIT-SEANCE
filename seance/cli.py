"""seance: summon, mourn, and remember the people who wrote your code."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

from . import __version__, git, ofrenda as altar, spirit, theatre as t, tribunal
from .llm import DEFAULT_BACKEND, DEFAULT_HOST, DEFAULT_MODEL, Medium, MediumError, OtariMedium
from .otari import Otari, OtariError, pick_panel


def _rel(path: str) -> str:
    root = git.repo_root(os.path.dirname(os.path.abspath(path)) or ".")
    return os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")


def _speak(medium, messages: list[dict]) -> str:
    try:
        return t.possess(medium.channel(messages))
    except MediumError as e:
        t.out(t.blood(f"\n  The candles gutter out. {e}"))
        sys.exit(2)


def _receipt(medium) -> None:
    r = getattr(medium, "last", None)
    if r is not None:
        t.out(t.dim(f"  ☎ otari: {r.line()}"))


def _read_letters(h, root: str, medium) -> None:
    """Let the ghost read the PRs, issues and links its commits point to, through Otari's fetch."""
    client = getattr(medium, "client", None)
    if client is None:
        return
    found = spirit.find_letters(h, git.web_remote(root))
    if not found:
        t.out(t.dim("  no letters were left behind in these commits"))
        return
    t.out(t.dim(f"  opening {len(found)} letter(s) through the Otari gateway ..."))
    h.letters = spirit.read_letters(found, lambda u: client.fetch(u))
    for i, le in enumerate(h.letters, 1):
        t.out(t.dim(f"    [letter {i}] {le.url}  {le.title[:60]}"))
    for le in found:
        if le.error:
            t.out(t.dim(f"    (could not read {le.url}: {le.error})"))


def _report_citations(text: str, known: set[str], quiet: bool = False) -> None:
    cites = spirit.verify(text, known)
    if not cites and quiet:
        return
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
        (f"channeling {medium.model} through the Otari switchboard ..." if getattr(medium, "backend", "") == "otari"
         else f"channeling {medium.model} through the veil, entirely on this machine ..."),
    ])
    if getattr(medium, "backend", "") == "otari" and not getattr(args, "no_letters", False):
        _read_letters(h, root, medium)
    t.out()
    t.out(t.dim(f"  >> {b.text.strip()}"))
    t.out(t.dim(f"  evidence: [{git.short(c.sha)}] {c.subject}"))
    t.out()

    messages = spirit.summon_messages(h, args.question)
    reply = _speak(medium, messages)
    t.out()
    _report_citations(reply, h.known_shas)
    _receipt(medium)

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
        _receipt(medium)


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
    _report_citations(text, {r.first.sha, r.last.sha}, quiet=True)

    slug = re.sub(r"[^a-z0-9]+", "-", r.spirit.name.lower()).strip("-") or "spirit"
    base = args.output or f"ofrenda-{slug}"
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(text.strip() + "\n")
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(altar.render(r, text, medium.model))
    t.out(t.moss(f"\n  The altar is set: {base}.md and {base}.html"))


def _client(medium) -> Otari:
    return getattr(medium, "client", None) or Otari()


def cmd_tribunal(args, medium) -> None:
    m = re.match(r"^(.+):(\d+)$", args.target)
    if not m:
        sys.exit("tribunal needs FILE:LINE, for example: seance tribunal src/app.py:42")
    client = _client(medium)
    path, line = m.group(1), int(m.group(2))
    root = git.repo_root(os.path.dirname(os.path.abspath(path)) or ".")
    h = spirit.gather(_rel(path), line, cwd=root)
    models = [x.strip() for x in (args.models or os.environ.get("SEANCE_TRIBUNAL", "")).split(",") if x.strip()]
    if not models:
        t.ritual(["asking the switchboard which open-weight mediums are awake ..."])
        try:
            models = pick_panel(client.open_weight_models(), args.size)
        except OtariError as e:
            t.out(t.blood(f"  {e}"))
            sys.exit(2)
        if not models:
            sys.exit("  no open-weight chat models are reachable with this key. Name some with --models.")

    t.out(t.marigold(t.CANDLES))
    t.ritual([
        f"convening a tribunal over {h.path}:{h.line} ...",
        f"the accused hand: {h.blame.author}, in commit {git.short(h.commit.sha)}",
        f"{len(models)} mediums, one Otari key: " + ", ".join(models),
    ])
    if not args.no_letters:
        _read_letters(h, root, OtariMedium(client=client))
    t.out(t.dim(f"\n  >> {h.blame.text.strip()}\n"))
    t.ritual(["every medium hears the same evidence, at the same time ..."])
    heard = tribunal.convene(models, spirit.summon_messages(h, args.question), h.known_shas, root, client)

    for i, x in enumerate(heard, 1):
        colour = t.moss if x.verdict.startswith("honest") else (t.blood if x.lies or x.error else t.marigold)
        t.out()
        t.out(t.bold(f"  {i}. {x.model}") + "  " + colour(x.verdict.upper()))
        if x.error:
            t.out(t.blood(f"     {x.error}"))
            continue
        excerpt = " ".join(x.text.split())
        t.out(t.ghost(f"     “{excerpt[:260]}{'…' if len(excerpt) > 260 else ''}”"))
        t.out(t.dim(f"     sealed {x.sealed} · unseen {x.unseen} · lies {x.lies}"))
        if x.receipt:
            t.out(t.dim(f"     ☎ {x.receipt.line()} · whole answer in {x.seconds:.1f}s"))

    winner = next((x for x in heard if not x.error and not x.lies and x.citations), None)
    t.out()
    if winner:
        t.out(t.moss(f"  ⚖ The honest medium is {winner.model}."))
    else:
        t.out(t.blood("  ⚖ No medium could be trusted this time."))
    total = sum(x.cost or 0 for x in heard)
    if any(x.cost is not None for x in heard):
        t.out(t.dim(f"  the whole tribunal cost ${total:.6f}"))
    out = args.output or f"tribunal-{re.sub(r'[^A-Za-z0-9]+', '-', h.path).strip('-')}-{h.line}.md"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(tribunal.report(h, args.question, heard) + "\n")
    t.out(t.moss(f"  the record is kept in {out}"))


def cmd_mediums(args, medium) -> None:
    client = _client(medium)
    t.ritual(["listening for open-weight mediums on the switchboard ..."])
    try:
        models = client.open_weight_models()
    except OtariError as e:
        t.out(t.blood(f"  {e}"))
        sys.exit(2)
    t.out()
    models = sorted(models, key=lambda m: (m.get("in") is None, m.get("in") or 0, m["id"]))
    for m in models[: args.limit]:
        price = f"${m['in']:.2f} / ${m['out']:.2f} per M tokens" if m.get("in") is not None and m.get("out") is not None else ""
        t.out(f"  {t.marigold(m['id']):<50} {t.dim(price)}")
    if len(models) > args.limit:
        t.out(t.dim(f"  ... and {len(models) - args.limit} more (--limit {len(models)} to see them all)"))
    t.out(t.dim(f"\n  {len(models)} open-weight medium(s) awake, cheapest first. A tribunal would call: {', '.join(pick_panel(models)) or 'nobody'}"))
    try:
        b = client.budget()
        left = b.get("remaining_usd")
        if left is not None:
            t.out(t.dim(f"  the offering bowl for this key holds ${left:.2f} more"))
        elif b.get("budgets_enforced") is False:
            t.out(t.dim("  this key has no budget, so the spirits can spend freely"))
    except OtariError:
        pass


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="seance", description="Summon the ghosts in your git history with a local open-weight model.")
    p.add_argument("--version", action="version", version=f"git-seance {__version__}")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"local model to channel (default {DEFAULT_MODEL})")
    p.add_argument("--backend", default=DEFAULT_BACKEND, choices=["ollama", "openai", "otari"],
                   help="ollama, any OpenAI-compatible local server, or otari (Mozilla AI's gateway, needs OTARI_API_KEY)")
    p.add_argument("--otari", action="store_true", help="shorthand for --backend otari")
    p.add_argument("--host", default=DEFAULT_HOST, help="server URL (default localhost)")
    p.add_argument("--plain", action="store_true", help="no colors, no flicker, no delays")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("summon", help="summon the ghost who wrote a line")
    s.add_argument("target", help="FILE:LINE")
    s.add_argument("-q", "--question", default="Why do you haunt this line? Why does it exist?")
    s.add_argument("--once", action="store_true", help="one answer, no follow-up questions")
    s.add_argument("--no-letters", action="store_true", help="with otari: do not read the PRs and links the commits mention")
    s.set_defaults(fn=cmd_summon)

    tr = sub.add_parser("tribunal", help="summon one ghost through several open-weight models via Otari; git judges who lies")
    tr.add_argument("target", help="FILE:LINE")
    tr.add_argument("-q", "--question", default="Why do you haunt this line? Why does it exist?")
    tr.add_argument("--models", help="comma-separated Otari model ids (default: SEANCE_TRIBUNAL, else picked from the catalog)")
    tr.add_argument("--size", type=int, default=3, help="how many mediums to pick when none are named (default 3)")
    tr.add_argument("--no-letters", action="store_true", help="do not read the PRs and links the commits mention")
    tr.add_argument("-o", "--output", help="where to keep the Markdown record")
    tr.set_defaults(fn=cmd_tribunal, otari_only=True)

    md = sub.add_parser("mediums", help="list the open-weight models your Otari key can reach, and its budget")
    md.add_argument("--limit", type=int, default=25)
    md.set_defaults(fn=cmd_mediums, otari_only=True)

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
    if args.otari or getattr(args, "otari_only", False):
        args.backend = "otari"
    if args.backend == "otari":
        model = args.model if args.model != DEFAULT_MODEL else ""
        medium = OtariMedium(model=model, ritual=args.cmd)
    else:
        medium = Medium(model=args.model, backend=args.backend, host=args.host)
    try:
        args.fn(args, medium)
    except git.GitError as e:
        t.out(t.blood(f"  The spirits are silent: {e}"))
        sys.exit(1)
    except KeyboardInterrupt:
        t.out(t.dim("\n  séance interrupted."))
        sys.exit(130)
