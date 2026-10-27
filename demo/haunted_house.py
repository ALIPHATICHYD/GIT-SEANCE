"""Builds a small, fictional, haunted repository to hold a séance in.

    python demo/haunted_house.py /tmp/haunted-house
    cd /tmp/haunted-house && seance graveyard

Every person here is invented. The repo's own git identity is set to
"You", so summoning a line you wrote three years ago has a twist.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap

EDNA = ("Edna Voss", "edna@lanternworks.example")
MARCUS = ("Marcus Bell", "marcus@lanternworks.example")
YOU = ("You", "you@lanternworks.example")
PRIYA = ("Priya Raman", "priya@lanternworks.example")

PRINTER = textwrap.dedent("""\
        \"\"\"Talks to the receipt printer in the basement.\"\"\"
        import time

        RETRIES = 3


        def wake(port):
            port.write(b"\\x1b@")
            time.sleep(0.3)  # do not remove


        def print_receipt(port, lines):
            wake(port)
            for line in lines:
                port.write(line.encode() + b"\\n")
        """)

# (author, date, message, edits): each edit is (path, old, new) or (path, None, full_text)
HISTORY = [
    (EDNA, "2019-10-29T23:41:00", "lantern: first light", [
        ("lantern/__init__.py", None, '"""Lantern: point of sale for the night shift."""\n'),
        ("lantern/printer.py", None, PRINTER.replace("    time.sleep(0.3)  # do not remove\n", "")),
    ]),
    (EDNA, "2019-11-02T02:13:00",
     "wait for the printer to wake up\n\nIt is always cold in the basement after midnight and the printer\n"
     "swallows the first bytes it hears. 300ms is enough. 200ms is not.\nI tried. Do not remove.",
     [("lantern/printer.py", "    port.write(b\"\\x1b@\")\n", "    port.write(b\"\\x1b@\")\n    time.sleep(0.3)  # do not remove\n")]),
    (EDNA, "2020-03-13T01:02:00", "add till totals. counting coins by candlelight", [
        ("lantern/till.py", None, "def total(items):\n    return round(sum(price for _, price in items), 2)\n"),
    ]),
    (MARCUS, "2020-06-09T10:15:00", "remove pointless sleep in printer wake", [
        ("lantern/printer.py", "    time.sleep(0.3)  # do not remove\n", ""),
    ]),
    (MARCUS, "2020-06-09T22:47:00",
     "Revert \"remove pointless sleep in printer wake\"\n\nThe printer screamed. Every receipt came out blank.\nEdna was right. I am putting it back and I am not touching it again.",
     [("lantern/printer.py", "    port.write(b\"\\x1b@\")\n", "    port.write(b\"\\x1b@\")\n    time.sleep(0.3)  # do not remove\n")]),
    (MARCUS, "2021-02-01T14:30:00", "till: handle refunds", [
        ("lantern/till.py", "def total(items):\n", "def total(items, refunds=()):\n"),
        ("lantern/till.py", "    return round(sum(price for _, price in items), 2)\n",
         "    return round(sum(p for _, p in items) - sum(refunds), 2)\n"),
    ]),
    (EDNA, "2021-10-31T23:58:00", "leave the light on for whoever comes next", [
        ("lantern/__init__.py", None, '"""Lantern: point of sale for the night shift."""\n\nLIGHT_ON = True\n'),
    ]),
    (YOU, "2023-10-30T03:12:00", "fix it (do not ask)", [
        ("lantern/till.py", None,
         "MAGIC = 37  # ???\n\n\ndef total(items, refunds=()):\n    return round(sum(p for _, p in items) - sum(refunds), 2) % (MAGIC * 1000)\n"),
    ]),
    (PRIYA, "2026-09-14T11:05:00", "docs: explain the till", [
        ("README.md", None, "# Lantern\n\nPoint of sale for the night shift. Nobody remembers why it works.\n"),
    ]),
    (PRIYA, "2026-10-20T16:40:00", "printer: bump retries", [
        ("lantern/printer.py", "RETRIES = 3\n", "RETRIES = 5\n"),
    ]),
]


def git(cwd, *args, env=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, env=env, capture_output=True)


def build(dest: str) -> str:
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "config", "user.name", YOU[0])
    git(dest, "config", "user.email", YOU[1])
    git(dest, "config", "commit.gpgsign", "false")
    for (name, email), date, message, edits in HISTORY:
        for path, old, new in edits:
            full = os.path.join(dest, path)
            os.makedirs(os.path.dirname(full) or dest, exist_ok=True)
            if old is None:
                text = textwrap.dedent(new)
            else:
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
                assert old in text, f"{path}: {old!r} not found"
                text = text.replace(old, new, 1)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(text)
            git(dest, "add", path)
        env = dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=date + "+0000",
                   GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=date + "+0000")
        git(dest, "commit", "-q", "-m", message, env=env)
    return dest


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "haunted-house"))
