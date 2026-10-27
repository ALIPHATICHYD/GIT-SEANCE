"""Everything the spirits know comes from here: plain `git` plumbing, no network."""

from __future__ import annotations

import os
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone


class GitError(RuntimeError):
    pass


def run(args: list[str], cwd: str = ".", check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def repo_root(cwd: str = ".") -> str:
    return run(["rev-parse", "--show-toplevel"], cwd).strip()


def commit_exists(sha: str, cwd: str = ".") -> bool:
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=cwd,
        capture_output=True,
    )
    return proc.returncode == 0


def short(sha: str) -> str:
    return sha[:7]


def when(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


@dataclass
class BlameLine:
    sha: str
    author: str
    email: str
    time: int
    summary: str
    orig_path: str
    orig_line: int
    final_line: int
    text: str

    @property
    def uncommitted(self) -> bool:
        return set(self.sha) == {"0"}


def _parse_porcelain(out: str) -> list[BlameLine]:
    """Parse `git blame --line-porcelain` output into BlameLines."""
    lines: list[BlameLine] = []
    cur: dict = {}
    for raw in out.splitlines():
        if raw.startswith("\t"):
            lines.append(
                BlameLine(
                    sha=cur["sha"],
                    author=cur.get("author", "?"),
                    email=cur.get("author-mail", "").strip("<>"),
                    time=int(cur.get("author-time", 0)),
                    summary=cur.get("summary", ""),
                    orig_path=cur.get("filename", ""),
                    orig_line=cur["orig"],
                    final_line=cur["final"],
                    text=raw[1:],
                )
            )
            cur = {}
            continue
        head, _, rest = raw.partition(" ")
        if len(head) == 40 and all(c in "0123456789abcdef" for c in head) and "sha" not in cur:
            parts = rest.split()
            cur["sha"], cur["orig"], cur["final"] = head, int(parts[0]), int(parts[1])
        else:
            cur[head] = rest
    return lines


def blame(path: str, start: int | None = None, end: int | None = None, cwd: str = ".") -> list[BlameLine]:
    args = ["blame", "--line-porcelain", "-w"]
    if start is not None:
        args += ["-L", f"{start},{end or start}"]
    args += ["--", path]
    return _parse_porcelain(run(args, cwd))


@dataclass
class Commit:
    sha: str
    author: str
    email: str
    time: int
    subject: str
    body: str

    @property
    def message(self) -> str:
        return (self.subject + "\n\n" + self.body).strip()


_FMT = "%H%x1f%an%x1f%ae%x1f%at%x1f%s%x1f%b%x1e"


def _parse_commits(out: str) -> list[Commit]:
    commits = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, an, ae, at, s, b = rec.split("\x1f")
        commits.append(Commit(sha, an, ae, int(at), s, b.strip()))
    return commits


def commit(sha: str, cwd: str = ".") -> Commit:
    return _parse_commits(run(["show", "-s", f"--format={_FMT}", sha], cwd))[0]


def commit_diff(sha: str, path: str | None = None, max_lines: int = 80, cwd: str = ".") -> str:
    args = ["show", "--format=", "--no-color", "-U2", sha]
    if path:
        args += ["--", path]
    out = run(args, cwd, check=False).splitlines()
    if len(out) > max_lines:
        out = out[:max_lines] + [f"... ({len(out) - max_lines} more lines lost to the void)"]
    return "\n".join(out)


def line_history(path: str, line: int, limit: int = 8, cwd: str = ".") -> list[Commit]:
    """Every commit that touched this line, newest first (git log -L)."""
    out = run(
        ["log", f"-L{line},{line}:{path}", "-s", f"-n{limit}", f"--format={_FMT}"],
        cwd,
        check=False,
    )
    return _parse_commits(out)


def past_lives(text: str, path: str, limit: int = 8, cwd: str = ".") -> list[Commit]:
    """Commits that added or removed this exact text, even before the line's current life (git log -S)."""
    if not text.strip():
        return []
    out = run(["log", f"-S{text.strip()}", f"-n{limit}", f"--format={_FMT}", "--", path], cwd, check=False)
    return _parse_commits(out)


def author_commits(email: str, limit: int | None = None, cwd: str = ".") -> list[Commit]:
    args = ["log", f"--author=<{email}>", f"--format={_FMT}"]
    if limit:
        args.insert(1, f"-n{limit}")
    return _parse_commits(run(args, cwd, check=False))


def latest_commit_time(cwd: str = ".") -> int:
    out = run(["log", "-1", "--format=%at"], cwd, check=False).strip()
    return int(out) if out else 0


def current_user_email(cwd: str = ".") -> str:
    return run(["config", "user.email"], cwd, check=False).strip().lower()


def read_context(path: str, line: int, radius: int = 6, cwd: str = ".") -> list[tuple[int, str]]:
    full = os.path.join(repo_root(cwd), path) if not os.path.isabs(path) else path
    with open(full, encoding="utf-8", errors="replace") as fh:
        src = fh.read().splitlines()
    lo, hi = max(1, line - radius), min(len(src), line + radius)
    return [(n, src[n - 1]) for n in range(lo, hi + 1)]


@dataclass
class Spirit:
    """A contributor, living or departed, and what they left behind."""

    name: str
    email: str
    first: int = 0
    last: int = 0
    commits: int = 0
    surviving_lines: int = 0
    last_words: str = ""
    files: Counter = field(default_factory=Counter)

    def departed(self, now: int, days: int) -> bool:
        return now - self.last > days * 86400


def tracked_files(cwd: str = ".", paths: list[str] | None = None) -> list[str]:
    out = run(["ls-files", "-z", "--", *(paths or [])], cwd)
    return [p for p in out.split("\0") if p]


def census(cwd: str = ".", paths: list[str] | None = None, max_files: int = 400) -> dict[str, Spirit]:
    """Count every contributor's commits and how many of their lines still haunt HEAD."""
    spirits: dict[str, Spirit] = {}
    log = run(["log", "--format=%x1e%an%x1f%ae%x1f%at%x1f%s", "--name-only"], cwd, check=False)
    for rec in log.split("\x1e"):
        if not rec.strip():
            continue
        head, *names = rec.strip("\n").split("\n")
        an, ae, at, subject = head.split("\x1f", 3)
        key = ae.lower()
        sp = spirits.setdefault(key, Spirit(an, key, first=int(at), last=int(at), last_words=subject))
        sp.commits += 1
        t = int(at)
        if t > sp.last:
            sp.last, sp.last_words, sp.name = t, subject, an
        sp.first = min(sp.first, t)
        sp.files.update(n for n in names if n.strip())

    counts: dict[str, int] = defaultdict(int)
    root = repo_root(cwd)
    for path in tracked_files(cwd, paths)[:max_files]:
        full = os.path.join(root, path)
        try:
            if os.path.getsize(full) > 512_000:
                continue
            with open(full, "rb") as fh:
                if b"\0" in fh.read(4096):
                    continue
        except OSError:
            continue
        for bl in blame(path, cwd=root):
            if not bl.uncommitted:
                counts[bl.email.lower()] += 1
    for key, n in counts.items():
        if key in spirits:
            spirits[key].surviving_lines = n
    return spirits


def oldest_lines(cwd: str = ".", paths: list[str] | None = None, top: int = 5, max_files: int = 400) -> list[tuple[str, BlameLine]]:
    """The lines that have gone longest without being disturbed."""
    found: list[tuple[str, BlameLine]] = []
    root = repo_root(cwd)
    for path in tracked_files(cwd, paths)[:max_files]:
        try:
            with open(os.path.join(root, path), "rb") as fh:
                if b"\0" in fh.read(4096):
                    continue
        except OSError:
            continue
        for bl in blame(path, cwd=root):
            if bl.text.strip() and not bl.uncommitted:
                found.append((path, bl))
    found.sort(key=lambda pb: pb[1].time)
    return found[:top]
