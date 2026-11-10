"""The tribunal: summon one ghost through several open-weight mediums and see which one lies.

Every medium gets the same evidence and the same question through one Otari key.
Git then judges them: a cited hash is sealed (it was in the evidence), real but
unseen, or a lie. Honesty first, then cost, then speed.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import git, spirit
from .llm import MediumError, OtariMedium


@dataclass
class Testimony:
    model: str
    text: str = ""
    error: str = ""
    seconds: float = 0.0
    receipt: object = None
    citations: list[spirit.Citation] = field(default_factory=list)

    @property
    def sealed(self) -> int:
        return sum(1 for c in self.citations if c.in_evidence)

    @property
    def unseen(self) -> int:
        return sum(1 for c in self.citations if c.real and not c.in_evidence)

    @property
    def lies(self) -> int:
        return sum(1 for c in self.citations if not c.real)

    @property
    def cost(self) -> float | None:
        return getattr(self.receipt, "cost_usd", None)

    @property
    def score(self) -> int:
        """Truth is worth a point, a real-but-unseen hash costs one, a lie costs five. Silence earns nothing."""
        if self.error:
            return -99
        return self.sealed - self.unseen - 5 * self.lies

    @property
    def verdict(self) -> str:
        if self.error:
            return "did not answer"
        if self.lies:
            return "LIAR"
        if not self.citations:
            return "silent (cited nothing)"
        if self.unseen:
            return "honest, but wandered"
        return "honest"


def hear(model: str, messages: list[dict], known: set[str], cwd: str, client=None) -> Testimony:
    t = Testimony(model)
    medium = OtariMedium(model=model, ritual="tribunal", client=client)
    start = time.monotonic()
    try:
        t.text = "".join(medium.channel(messages)).strip()
    except MediumError as e:
        t.error = str(e)
    t.seconds = time.monotonic() - start
    t.receipt = medium.last
    if t.text:
        t.citations = spirit.verify(t.text, known, cwd=cwd)
    return t


def convene(models: list[str], messages: list[dict], known: set[str], cwd: str, client=None) -> list[Testimony]:
    """Hear every medium at once; rank by honesty, then cost, then speed."""
    with ThreadPoolExecutor(max_workers=max(1, len(models))) as pool:
        heard = list(pool.map(lambda m: hear(m, messages, known, cwd, client), models))
    return sorted(heard, key=lambda t: (-t.score, t.cost if t.cost is not None else 9e9, t.seconds))


def report(h: spirit.Haunting, question: str, heard: list[Testimony]) -> str:
    """The tribunal's record, as Markdown."""
    rows = []
    for i, t in enumerate(heard, 1):
        r = t.receipt
        served = f"{getattr(r, 'model', '') or t.model}" + (f" @ {r.provider}" if r and r.provider else "")
        cost = f"${t.cost:.6f}" if t.cost is not None else "n/a"
        rows.append(f"| {i} | `{t.model}` | {served} | {t.verdict} | {t.sealed} | {t.unseen} | {t.lies} | {cost} | {t.seconds:.1f}s |")
    body = []
    for t in heard:
        body.append(f"### `{t.model}`: {t.verdict}\n")
        if t.error:
            body.append(f"> {t.error}\n")
            continue
        body.append("> " + t.text.replace("\n", "\n> ") + "\n")
        for c in t.citations:
            mark = "sealed in git history" if c.in_evidence else ("real, but not in the evidence" if c.real else "**does not exist**")
            body.append(f"- `[{c.token}]` {mark}")
        if t.receipt and getattr(t.receipt, "request_id", ""):
            body.append(f"- Otari request `{t.receipt.request_id}`")
        body.append("")
    winner = next((t for t in heard if not t.error and not t.lies and t.citations), None)
    return "\n".join([
        f"# Séance tribunal: `{h.path}:{h.line}`",
        "",
        f"The line: `{h.blame.text.strip()}`  ",
        f"Written by **{h.blame.author}** in [{git.short(h.commit.sha)}] {h.commit.subject}  ",
        f"Question: *{question}*",
        "",
        f"Every medium got the same evidence through one [Otari](https://otari.ai) key. Git checked every hash.",
        "",
        "| # | Asked | Served by | Verdict | Sealed | Unseen | Lies | Cost | Time |",
        "|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"**The honest medium:** `{winner.model}`" if winner else "**No medium was trustworthy this time.**",
        "",
        "## Testimony",
        "",
        *body,
    ])
