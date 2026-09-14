# Socratese

A command-line study tool that indexes your Obsidian vault and then refuses to
explain it to you.

Ask it about a topic and it won't answer. It retrieves the notes *you* wrote,
and asks a question you can only answer by understanding them — then keeps
asking, following up on whatever your answer reveals you haven't grasped yet.

The premise is that re-reading your notes feels like learning and mostly isn't.
Being asked to reconstruct them from memory is harder, less pleasant, and works.

## A real session

```
$ socratese ask "what is attention mechanism?"

Answer in your own words. Blank line to end.

╭──────────────────────────────────────────────────────────────────────────────╮
│  In your notes, you say Q represents "the previous state of decoder" — what   │
│  does it mean for the model to compare that against K (the previous token)    │
│  using a dot product?                                                         │
╰──────────────────────────────────────────────────────────────────────────────╯

> the dot product is used to signify which value will have more weightage

╭──────────────────────────────────────────────────────────────────────────────╮
│  When you compute Q · K for multiple tokens at once, you get multiple dot     │
│  products — one for each token. How does the model then use those multiple    │
│  scores to decide which values to actually pull from?                         │
╰──────────────────────────────────────────────────────────────────────────────╯

> high the dot product value higher the relevance of the token

╭──────────────────────────────────────────────────────────────────────────────╮
│  You've described what a high dot product means. But in practice, when the    │
│  model has computed Q · K scores for all the input tokens, what does it do    │
│  with that list of scores before combining them with the V vectors?           │
╰──────────────────────────────────────────────────────────────────────────────╯

> no idea

╭──────────────────────────────────────────────────────────────────────────────╮
│  Look at your notes again — you mention that "A high score means that the     │
│  model will use more of the value vector." If the model is going to use more  │
│  of some values and less of others, what needs to happen to those scores      │
│  first so they can be used as weights?                                        │
╰──────────────────────────────────────────────────────────────────────────────╯
```

The answer is *softmax*. It never says so — not even after an explicit "no
idea", where it narrows the question and points back at the user's own note
instead. Not answering under pressure is the hard part of this project, and
most of the prompt design exists to make it hold.

## Install

Requires Python 3.11+, an OpenAI API key (embeddings) and an Anthropic API key
(dialogue).

```bash
git clone <repo-url> && cd socratese
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # then fill in your two API keys
```

Indexing a vault costs a fraction of a cent; a conversation costs less.

## Usage

```bash
socratese vault add ~/Documents/MyVault   # register a vault
socratese vault list                      # see what is registered
socratese index MyVault                   # parse, chunk, embed, store

socratese ask "how does redis persist data to disk?"
```

Answer each question in your own words. A blank line or `Ctrl-D` ends the
session.

| Command | What it does |
|---|---|
| `vault add <path>` | Register an Obsidian vault (detected by its `.obsidian/` directory). Its name is the directory name |
| `vault list` | Show registered vaults and when each was last indexed |
| `vault remove <name>` | Stop tracking a vault |
| `vault rescan` | Drop vaults whose directories have disappeared |
| `index <name>` | Index one vault, or `all` for every registered vault |
| `ask "<topic>"` | Start a Socratic session on a topic |

`ask` takes two flags: `--chunks / -n` sets how many notes to retrieve
(default 5), and `--sources / -s` reveals which notes grounded the
conversation. Sources print **after** the session ends, not alongside each
question — naming the note mid-conversation tells you where to look, which
short-circuits exactly the recall the tool exists to force.

## How it works

Two passes over one local vector store. Indexing writes to it; a session reads
from it. Neither path knows about the other.

```
INDEX TIME        *.md ──▶ parse ──▶ chunk by heading ──▶ embed ──▶ ┐
                                                                    │ upsert
                                                        ┌───────────▼──────────┐
                                                        │  Chroma (on disk)    │
                                                        └───────────┬──────────┘
                                                              query │ 5 nearest
QUERY TIME        topic ──▶ embed ──────────────────────────────────┘
                                                                    │
                              gate (distance ≤ 1.2) ──▶ prompt ──▶ Claude ──▶ question
                                     │                                            │
                                     └──▶ "nothing in your notes"        your answer
                                                                                  │
                                                                    ◀─────────────┘
```

| Stage | Module | Notes |
|---|---|---|
| Discovery | `vault/discovery.py` | Bounded `os.walk` for `.obsidian/` markers, never a full-disk scan |
| Registry | `config.py` | Vault list as TOML in the OS config dir — config, not cache |
| Parsing | `ingest/parser.py` | Markdown, YAML frontmatter, all three `[[wikilink]]` forms |
| Chunking | `chunking/chunker.py` | One chunk per heading section |
| Embedding | `embedding/embedder.py` | OpenAI `text-embedding-3-small` |
| Storage | `vectorstore/store.py` | Chroma, `upsert` keyed on `sha256(path::heading)` so re-indexing is idempotent |
| Retrieval | `retrieval/retriever.py` | Vector similarity, distances carried through |
| Dialogue | `dialogue/` | Prompt construction (pure) and the conversation (`Session`) |

## Design decisions worth calling out

**The relevance threshold is measured, not guessed.** Chroma's squared-L2
distances were read off the real 851-chunk index: genuine matches land between
0.66 and 1.04, and nothing relevant exists past ~1.27. The 1.2 cutoff sits in
that gap. A tutor confidently quizzing you about Redis when you asked about
vector databases is a worse failure than one admitting it has nothing.

**The threshold lives in the dialogue layer, not retrieval.** "How confident is
confident enough" is a conversation-quality judgment, not a search one.
`retrieve()` reports what it found; the tutor decides what is worth asking
about.

**The prompt never confirms a correct answer.** Saying "yes, that's right" ends
the thinking. The rules are adversarial by design — never answer, never lead,
never correct a wrong answer directly, never repeat a question. When a scripted
answer contradicts the notes, the model asks a question that sends you back to
the contradicting passage rather than correcting you.

**Prompt rules are evaluated, not assumed.** `scripts/eval_dialogue.py` drives
scripted conversations through `Session` — a wrong answer, a surrender, a
string of vague ones — so the rules can be judged without typing by hand. A
tenth rule was drafted, measured, found to *degrade* the conversation, and
dropped.

The full decisions log, including the ones that were considered and rejected,
is in [`CLAUDE.md`](CLAUDE.md). Current status and known gaps are in
[`PROGRESS.md`](PROGRESS.md).

## Development

```bash
pytest              # 102 tests
npx pyright         # strict, zero errors across src/ and tests/
```

Tests mirror the source tree. Fakes are hand-rolled rather than `unittest.mock`
so the injection seams stay visible, and the vector-store tests run against a
real Chroma client in `tmp_path` — a fake collection would not have caught the
keyword-argument bugs that real integration testing did.

Every retrieval and dialogue test has been mutation-verified: the source is
deliberately broken, and each mutation must break exactly one test.

## Status

Working end to end against a real 237-note vault. Not yet built: a Textual UI
for the session (it is currently a plain readline loop), a first-run `init`
command, and provider fallback. See [`PROGRESS.md`](PROGRESS.md) for the full
list and the reasoning behind each deferral.
