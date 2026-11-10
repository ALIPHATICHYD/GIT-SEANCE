# 👻 git-seance

**Summon the ghost who wrote that line of code.** `git-seance` reads your `git blame`, your log, and every past life of a line, then lets a small open-weight model running on your own machine speak as the person who wrote it. The ghost has to cite its commits before it accuses anyone, and the CLI checks every hash it mentions against git. Spirits lie. Git does not.

Built for the DEV Hacktoberfest 2026 "Ghost in the Machine" challenge, and finished for Mozilla's **Developers Wilding** hackathon with [Otari](https://otari.ai) as its gateway: one key, many open-weight spirits, and a tribunal where git decides which model lies.

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
| `seance tribunal FILE:LINE` | **New, through Otari.** Summons the same ghost through several open-weight models at once. Git checks every hash each one cites, and the tribunal names the honest medium, with what each answer cost. |
| `seance mediums` | **New, through Otari.** Lists the open-weight models your Otari key can reach, and how much your key's budget has left. |
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

## Through Otari: the switchboard

[Otari](https://github.com/mozilla-ai/otari) is Mozilla AI's open-source AI gateway. When your laptop can't run a model, or you want to compare several, git-seance can channel through it:

```bash
export OTARI_API_KEY=tk-...                                   # https://otari.ai/dashboard/#/keys
export OTARI_BASE_URL=https://eu.api.otari.ai/api/v1          # only for EU accounts
seance mediums                                                # who is awake?
seance --otari summon lantern/printer.py:9                    # default: openai/gpt-oss-120b
seance --otari --model google/gemma-3-27b-it summon app.py:42
seance tribunal lantern/printer.py:9 --models openai/gpt-oss-120b,qwen/qwen3-32b,google/gemma-3-27b-it
```

What Otari adds to the séance:

- **One key, many open-weight mediums.** It uses Otari's OpenAI-compatible `/chat/completions` with catalog ids like `openai/gpt-oss-120b`. `seance mediums` reads the catalog and keeps only `open_weights` models.
- **The receipt.** After every answer the CLI prints the `Otari-Provider`, `Otari-Model`, `Otari-Attempt-Count`, `Otari-Fallback` and `Otari-Request-ID` headers, plus `usage.cost_usd`, so you see which provider really answered and what the séance cost.
- **Routing and fallback.** Make a routing policy in the Otari dashboard (for example `seance`: Gemma first, gpt-oss on failure) and pass `--model seance`. When a fallback fires, the receipt says so.
- **Letters from the other side.** URLs and `#123` references in the line's commits are read through Otari's gateway fetcher (`POST /fetch`), and the ghost may cite them as `[letter N]`. Turn it off with `--no-letters`.
- **The tribunal.** Every medium gets the same evidence at the same time. Each cited hash is sealed (in the evidence), real but unseen, or a lie. The ranking goes honesty first, then cost, then speed, and the full record is saved as Markdown.
- **Spend you can read back.** Every request is tagged `app=git-seance, ritual=summon|tribunal|...`, so the Otari dashboard groups spend by ritual. `seance mediums` shows what your key's budget has left (`GET /key/budget`).

Your code never leaves your machine unless you choose `--otari`. Ollama stays the default.

## How it works

1. **Evidence, from git only.** `git blame --line-porcelain` finds the commit and author. `git log -L` follows the line's life, and `git log -S` finds its *past lives*: times the same text was added or deleted before, such as a "pointless" sleep that someone removed and then sheepishly reverted. The author's other commit messages become the ghost's voice.
2. **A strict séance prompt.** The model speaks in the first person as the author, has to cite hashes in `[brackets]`, and is told to say "my memory fades" instead of inventing a motive.
3. **The hash check.** Every hex string in the reply is checked: sealed (it was in the evidence), real but unseen, or a lie.
4. **Nothing leaves the machine by default.** With Ollama, the only network call goes to your local model server. With `--otari`, the evidence goes to the Otari gateway you chose, and nothing else. No telemetry, no dependencies outside the standard library.

## Why open weights

Your source code and your teammates' commit history are exactly the kind of thing you should not paste into somebody else's cloud. A 4B open-weight model runs on a laptop, works on a plane, and will still work after any hosted API is gone. See the write-up for the long version.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests build the haunted house, check blame, past lives, the summoner twist, the census, the hash check, and the Ollama streaming client against a fake local server. `tests/test_otari.py` runs the Otari backend, letters, tribunal and catalog against a fake Otari gateway, so no key is needed.

## License

MIT
