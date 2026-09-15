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
socratese index MyVault                   # parse, chunk, embed, store
socratese                                 # open the app
```

`socratese` on its own opens a terminal app. Type `/ask <topic>` to start,
answer each question in your own words, and `/end` when you are done. Slash
commands complete as you type.

| In the app | What it does |
|---|---|
| `/ask <topic>` | Start a session on a topic |
| `/resume` | List recent sessions; `/resume <id>` continues one where you left it |
| `/vaults` | Pick which vaults sessions search (or `/vaults work personal`) |
| `/add <path>` | Track a new Obsidian vault |
| `/index <name>` | Index a vault, with progress |
| `/sources` | Reveal which notes the current session drew on |
| `/end`, `/quit` | End the session; leave the app |

The app inherits your terminal's colours and background rather than painting
its own, and re-wraps when you resize.

Every command also exists as a plain subcommand for scripting — `socratese ask
"<topic>"`, `socratese resume 3`, `socratese index all`, and the `vault`
group — so the app is a convenience, not a requirement.

`ask` takes `--vault / -v` to limit a session to named vaults, `--chunks / -n`
for how many notes to draw on, and `--sources / -s` to reveal them at the end.
Sources print **after** the session, not alongside each question — naming the
note mid-conversation tells you where to look, which short-circuits exactly
the recall the tool exists to force.

### When it circles

Sometimes your notes don't actually contain what the tutor is driving at. It
cannot tell — it will keep rephrasing the same question. The app detects this
(four consecutive questions orbiting the same terms) and says so:

```
These last few questions are all circling 'changed'.
Your notes may not settle what it is driving at. /end to stop and see them.
```

On exit after a stall, the grounding notes are listed under *worth re-reading
— and possibly filling in*. An incomplete note is a useful thing to learn; six
turns of interrogation about something you never wrote down is not.

### Sessions are kept

The last ten sessions are stored locally, including your answers and the
notes each one drew on. `/resume` picks one up exactly where you left it —
same notes, same conversation — even if you have re-indexed since. A session
you abandoned mid-question resumes on that question.

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
| Retrieval | `retrieval/retriever.py` | Vector similarity, distances carried through, filterable by vault |
| Dialogue | `dialogue/` | Prompt construction (pure), the conversation (`Session`), stall detection |
| Setup | `tutor.py` | The one sequence both UIs share: which vaults, what to retrieve, did anything clear the gate |
| History | `history/` | SQLite, last ten sessions, raw messages for replay — separate from the disposable index |
| App | `tui/` | Textual; every network call on a worker thread |

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

**Stall detection is code, not prompt.** Three attempts to make the model
notice it was circling — and stop — were measured against real transcripts.
None worked; one made things worse. The model follows concrete per-turn rules
("never answer") well and conditional meta-rules ("notice X, then change mode")
poorly. So the noticing is a deterministic sliding-window heuristic in
`dialogue/stall.py`, and the app does the intervening.

**Session history is SQLite, separate from the vector store.** The index is
disposable — re-run `index` and it's back. Transcripts aren't. They must not
share a store that a re-index could wipe, and the questions asked of history
("my last ten", "which notes do I keep failing on") are relational anyway.

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
pytest              # 245 tests, including the app driven headlessly
npx pyright         # strict, zero errors across src/ and tests/
```

Tests mirror the source tree. Fakes are hand-rolled rather than `unittest.mock`
so the injection seams stay visible, and the vector-store tests run against a
real Chroma client in `tmp_path` — a fake collection would not have caught the
keyword-argument bugs that real integration testing did.

Every retrieval and dialogue test has been mutation-verified: the source is
deliberately broken, and each mutation must break exactly one test.

## Status

Working end to end against a real 237-note vault, in the app and from the
command line. Not yet built: a `review` command over session history (the
tables are designed for it), a first-run `init`, and provider fallback. See
[`PROGRESS.md`](PROGRESS.md) for the full list and the reasoning behind each
deferral.
