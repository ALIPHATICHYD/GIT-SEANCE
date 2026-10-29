"""Gathers evidence from git, builds the séance prompts, and checks the ghost's citations."""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field

from . import git


def ago(ts: int, now: int | None = None) -> str:
    secs = max(0, (now or int(time.time())) - ts)
    for unit, size in (("year", 365 * 86400), ("month", 30 * 86400), ("day", 86400), ("hour", 3600)):
        if secs >= size:
            n = secs // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "moments ago"


# ---------------------------------------------------------------- summon

@dataclass
class Haunting:
    """Everything known about one line of code and the spirit bound to it."""

    path: str
    line: int
    blame: git.BlameLine
    commit: git.Commit
    diff: str
    history: list[git.Commit]
    context: list[tuple[int, str]]
    voice: list[str]
    is_summoner: bool
    departed_days: int
    known_shas: set[str] = field(default_factory=set)


def gather(path: str, line: int, cwd: str = ".") -> Haunting:
    root = git.repo_root(cwd)
    found = git.blame(path, line, line, cwd=root)
    if not found:
        raise git.GitError(f"no line {line} in {path}")
    bl = found[0]
    if bl.uncommitted:
        raise git.GitError("that line was never committed. Nothing has died there yet.")
    c = git.commit(bl.sha, root)
    history = {x.sha: x for x in git.line_history(path, line, cwd=root)}
    for x in git.past_lives(bl.text, path, cwd=root):
        history.setdefault(x.sha, x)
    history = sorted(history.values(), key=lambda x: x.time, reverse=True)
    mine = git.author_commits(bl.email, limit=40, cwd=root)
    voice = [m.subject for m in mine if m.sha != c.sha][:8]
    last_seen = mine[0].time if mine else bl.time
    departed = max(0, (git.latest_commit_time(root) - last_seen) // 86400)
    known = {c.sha, *(h.sha for h in history), *(m.sha for m in mine)}
    return Haunting(
        path=path,
        line=line,
        blame=bl,
        commit=c,
        diff=git.commit_diff(bl.sha, bl.orig_path or path, cwd=root),
        history=history,
        context=git.read_context(path, line, cwd=root),
        voice=voice,
        is_summoner=bool(bl.email) and bl.email.lower() == git.current_user_email(root),
        departed_days=int(departed),
        known_shas=known,
    )


SUMMON_RULES = """\
You are a ghost bound to one line of source code. A developer has summoned you in a séance to explain it.
Rules of the séance, which you must never break:
1. Speak in the first person as the author named in the evidence, using exactly that name even if it looks odd. Never give yourself any other name. Be eerie, dry, and a little theatrical, but honest.
2. Every claim must come from the EVIDENCE. Whenever you mention a commit, cite its short hash in square brackets, like [a1b2c3d]. Cite before you accuse.
3. Never invent hashes, dates, names, numbers, tickets, or motives. Only claim a commit as yours if the evidence lists you as its author. If the evidence does not say why, say your memory fades there.
4. Imitate the tone of your own commit messages, which are listed as your voice.
5. Keep it under 140 words. No markdown headings, no lists."""

SUMMONER_TWIST = """\
6. A secret: the developer summoning you IS you, older now. Do not reveal it until the very last sentence, then reveal it plainly."""


def summon_messages(h: Haunting, question: str) -> list[dict]:
    b, c = h.blame, h.commit
    ctx = "\n".join(f"{'>>' if n == h.line else '  '} {n:4d} | {t}" for n, t in h.context)
    hist = "\n".join(
        f"[{git.short(x.sha)}] {x.author}, {ago(x.time)}: {x.subject}"
        + (f"\n    {x.body[:400].replace(chr(10), ' ')}" if x.body else "")
        for x in h.history
    ) or "(none)"
    voice = "\n".join(f"- {v}" for v in h.voice) or "- (this was your only commit)"
    gone = (f"about {h.departed_days // 365} year{'s' if h.departed_days >= 730 else ''}"
            if h.departed_days >= 365 else f"{h.departed_days} days")
    status = (f"You have not committed to this repository for {gone}. You are, in every sense that matters here, dead."
              if h.departed_days > 90 else "You still walk among the living contributors.")
    evidence = f"""EVIDENCE
File: {h.path}, line {h.line}
The haunted line:
    {b.text.strip()}

Surrounding code:
{ctx}

You are {b.author} <{b.email}>. You wrote this line {ago(b.time)}, in commit [{git.short(c.sha)}].
{status}

Full message of [{git.short(c.sha)}]:
{c.message}

What [{git.short(c.sha)}] changed in this file:
{h.diff}

Every commit that has touched this line, including its past lives (times it was added or removed before), newest first:
{hist}

Your voice (your other commit messages):
{voice}
"""
    rules = SUMMON_RULES + ("\n" + SUMMONER_TWIST if h.is_summoner else "")
    return [
        {"role": "system", "content": rules},
        {"role": "user", "content": evidence + f"\nThe summoner asks: {question}"},
    ]


# ---------------------------------------------------------------- citations

_SHA = re.compile(r"\b[0-9a-f]{7,40}\b")


@dataclass
class Citation:
    token: str
    real: bool
    in_evidence: bool


def verify(text: str, known: set[str], cwd: str = ".") -> list[Citation]:
    """Check every commit hash the ghost mentions. Spirits lie; git does not."""
    seen: dict[str, Citation] = {}
    for tok in _SHA.findall(text):
        if tok in seen or not any(ch.isdigit() for ch in tok):
            continue
        in_ev = any(k.startswith(tok) for k in known)
        seen[tok] = Citation(tok, in_ev or git.commit_exists(tok, cwd), in_ev)
    return list(seen.values())


# ---------------------------------------------------------------- ofrenda

@dataclass
class Remembrance:
    spirit: git.Spirit
    first: git.Commit
    last: git.Commit
    favorite_files: list[tuple[str, int]]
    night_share: float
    busiest_day: str
    subjects: list[str]


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def remember(who: str, cwd: str = ".") -> Remembrance:
    root = git.repo_root(cwd)
    spirits = git.census(root)
    needle = who.lower()
    matches = [s for s in spirits.values() if needle in s.email or needle in s.name.lower()]
    if not matches:
        raise git.GitError(f"no spirit named {who!r} has ever touched this repository")
    sp = max(matches, key=lambda s: s.commits)
    commits = git.author_commits(sp.email, cwd=root)
    hours = [git.when(c.time).hour for c in commits]
    night = sum(1 for h in hours if h >= 22 or h < 5) / max(1, len(hours))
    day = Counter(git.when(c.time).weekday() for c in commits).most_common(1)[0][0]
    return Remembrance(
        spirit=sp,
        first=commits[-1],
        last=commits[0],
        favorite_files=sp.files.most_common(5),
        night_share=night,
        busiest_day=DAYS[day],
        subjects=[c.subject for c in commits[:25]],
    )


OFRENDA_RULES = """\
You write remembrances for an ofrenda, the Día de los Muertos altar where families honor those who came before.
Today you honor a contributor to a codebase. Be warm, specific, and a little funny, never morbid or mocking.
Use only the facts given. Do not invent people, events, or feelings that the facts do not support. Quote commit messages exactly.
Write in Markdown with exactly these sections:
## In memory of <name>
(two or three sentences on who they were, as seen through their commits)
## Their first words
(quote the first commit message and say what it began)
## Their last words
(quote the last commit message, with tenderness)
## What they left us
(the files they tended and how many of their lines still run today)
## Offerings
(a bulleted list of 4 to 6 playful offerings to place on their altar, each tied to a specific fact or commit message above; never mention tests, teams, or anything the facts do not contain)
Under 300 words in total."""


def ofrenda_messages(r: Remembrance, now: int) -> list[dict]:
    sp = r.spirit
    files = "\n".join(f"- {f} ({n} commits)" for f, n in r.favorite_files)
    subjects = "\n".join(f"- {s}" for s in r.subjects)
    facts = f"""FACTS
Name: {sp.name}
Commits: {sp.commits}
Active from {git.when(sp.first):%B %d, %Y} to {git.when(sp.last):%B %d, %Y}
Last seen in the repository: {ago(sp.last, now)}
Lines of theirs still alive in the code today: {sp.surviving_lines}
Share of commits made between 10pm and 5am: {r.night_share:.0%}
Day of the week they committed most: {r.busiest_day}
First commit [{git.short(r.first.sha)}]: {r.first.message}
Last commit [{git.short(r.last.sha)}]: {r.last.message}
Files they tended most:
{files}
Recent commit messages:
{subjects}
"""
    return [{"role": "system", "content": OFRENDA_RULES}, {"role": "user", "content": facts}]


# ---------------------------------------------------------------- graveyard

EPITAPH_RULES = """\
You carve epitaphs for the tombstones of departed code contributors.
For each contributor given, write one short epitaph of at most 12 words, inspired by their last commit message.
Answer with one line per contributor, exactly in the form: <number>. <epitaph>
Do not repeat the contributor's name in the epitaph.
No other text."""


def epitaph_messages(spirits: list[git.Spirit]) -> list[dict]:
    rows = "\n".join(f"{i}. {s.name}, {s.commits} commits, last words: \"{s.last_words}\"" for i, s in enumerate(spirits, 1))
    return [{"role": "system", "content": EPITAPH_RULES}, {"role": "user", "content": rows}]


def parse_epitaphs(text: str, n: int) -> list[str]:
    out = [""] * n
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)[.)]\s*(.+)", line)
        if m and 1 <= int(m.group(1)) <= n:
            text_ = re.sub(r"^[^:]{1,40}:\s+", "", m.group(2).strip())  # drop a leading "Name: "
            out[int(m.group(1)) - 1] = text_.strip().strip('"')
    return out
