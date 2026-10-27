# 👻 git-seance

**Summon the ghost who wrote that line of code.** `git-seance` reads your `git blame`, your log, and every past life of a line, then lets a small open-weight model running on your own machine speak as the person who wrote it. The ghost has to cite its commits before it accuses anyone, and the CLI checks every hash it mentions against git. Spirits lie. Git does not.

Built for the DEV Hacktoberfest 2026 "Ghost in the Machine" challenge.

```
      )        )        )
     (_)      (_)      (_)
     |~|      |~|      |~|
    _|_|______|_|______|_|_

  lighting candles over lantern/printer.py:9 ...
  reading the blame ... the hand that wrote this belonged to Marcus Bell
  the line was born 6 years ago, in commit 8637131
  3 commits have disturbed it since
  channeling gemma3:4b through the veil, entirely on this machine ...

  >> time.sleep(0.3)  # do not remove
```

## Three rituals

| Command | What it does |
| --- | --- |
| `seance summon FILE:LINE` | Raises the author of one line and lets you question them. Follow-up questions keep the séance going. |
| `seance graveyard` | Tombstones for contributors who have gone quiet, with how many of their lines still run in `HEAD`, epitaphs carved by the model, and "the crypt" of lines nobody has dared to touch. |
| `seance ofrenda NAME` | A Día de los Muertos altar for a contributor: their first words, their last words, what they left us, and offerings for the altar. Saved as Markdown and as an offline HTML page. |

If the line you summon was written by *you*, the ghost knows. It will not tell you until the end.

## Run it

You need Python 3.10+, git, and a local model. The default is Gemma 3 through [Ollama](https://ollama.com):

```bash
ollama pull gemma3:4b
pipx install git+https://github.com/ALIPHATICHYD/git-seance   # or: pip install .
cd some/repo
seance graveyard
seance summon src/app.py:42
seance ofrenda "edna"
```

Try it on the bundled haunted house, a fictional repo with a few ghosts in it:

```bash
python demo/haunted_house.py /tmp/haunted-house
cd /tmp/haunted-house
seance summon lantern/printer.py:9
seance summon lantern/till.py:1      # who wrote MAGIC = 37?
```

### Other models and servers

```bash
seance --model gemma3:12b summon app.py:10                   # a bigger spirit
seance --backend openai --host http://localhost:8080 ...     # llama.cpp llama-server, LM Studio, vLLM
export SEANCE_MODEL=gemma3:1b                                # set a default
```

`--plain` (or `NO_COLOR`, or piping the output) turns off the colors and the flicker.

## How it works

1. **Evidence, from git only.** `git blame --line-porcelain` finds the commit and author. `git log -L` follows the line's life, and `git log -S` finds its *past lives*: times the same text was added or deleted before, such as a "pointless" sleep that someone removed and then sheepishly reverted. The author's other commit messages become the ghost's voice.
2. **A strict séance prompt.** The model speaks in the first person as the author, has to cite hashes in `[brackets]`, and is told to say "my memory fades" instead of inventing a motive.
3. **The hash check.** Every hex string in the reply is checked: sealed (it was in the evidence), real but unseen, or a lie.
4. **Nothing leaves the machine.** The only network call goes to your local model server. No API keys, no telemetry, no dependencies outside the standard library.

## Why open weights

Your source code and your teammates' commit history are exactly the kind of thing you should not paste into somebody else's cloud. A 4B open-weight model runs on a laptop, works on a plane, and will still work after any hosted API is gone. See the write-up for the long version.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests build the haunted house, check blame, past lives, the summoner twist, the census, the hash check, and the Ollama streaming client against a fake local server.

## License

MIT
