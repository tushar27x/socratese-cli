# Socratese — Progress

Last updated: 2026-09-15 (textual-tui branch)

Status/continuity doc for picking this project back up in a new session.
For *why* decisions were made, see `CLAUDE.md` section 5 (the living
architecture decisions log) — this file is just "what's built, what's
next," not the reasoning.

## Done

**Vault management layer — fully built and tested.**

- `src/socratese/vault/models.py` — `Vault` dataclass (`name`, `path`,
  `last_indexed`). `to_toml_dict()`/`from_toml_dict()` for TOML
  (de)serialization. No `is_default` field (dropped — see CLAUDE.md
  decisions log; `vault set-default` was never built, doesn't exist).
- `src/socratese/config.py` — `get_config_path()` (via
  `platformdirs.user_config_dir()`), `load_vaults()`, `save_vaults()`.
  Reads/writes the whole `[[vaults]]` TOML file at once; no partial edits.
- `src/socratese/vault/discovery.py` — `find_vaults(root, max_depth=6)`.
  Bounded `os.walk()` scan for `.obsidian` directories, prunes into
  matched vaults and `SKIP_DIRS` (`.git`, `node_modules`, `venv`, etc.),
  explicit `onerror` handler for permission errors. This `SKIP_DIRS` is
  scoped to *finding* vaults on disk only — don't confuse with
  `ingest/parser.py`'s separate, differently-scoped `SKIP_DIRS` below.
- `src/socratese/cli/vault.py` — `socratese vault {list,add,remove,rescan}`,
  wired into `cli/main.py` via `app.add_typer(vault_app, name="vault")`.
  Rich for output; `Console(soft_wrap=True)` (needed — default wrapping
  broke on long paths, see git history for why).
- Tracked vault: `learning` at `/home/tushar27x/notes/obsidian/learning`
  (341 raw `.md` files on disk; 237 count as real indexable notes after
  excluding `.trash/`, `.obsidian/`, and Excalidraw files — see below).

**Phase 1: vault parsing & chunking — fully built and tested.**

- `src/socratese/ingest/models.py` — `Note` dataclass (`path`, `title`,
  `frontmatter`, `wikilinks`, `content`).
- `src/socratese/ingest/parser.py` — `parse_note()`/`parse_vault()`.
  Uses `python-frontmatter` for YAML frontmatter (main dependency, not
  dev-only — the shipped CLI needs it at runtime). `WIKILINK_RE` regex
  handles all three Obsidian link forms: `[[Target]]`,
  `[[Target|Display]]`, `[[Target#Heading]]` — captures the target only,
  discards display text/heading anchor via `[^\]]*` before the closing
  `]]`. `parse_vault()` walks via `os.walk()` with directory pruning
  (mirrors `discovery.py`'s idiom), using its own local `SKIP_DIRS =
  {".trash", ".obsidian"}` — a genuinely separate constant from
  `discovery.py`'s, since this one is about excluding content *inside*
  an already-found vault, not finding vaults on disk. Also skips any
  `*.excalidraw.md` filename outright (Obsidian Excalidraw plugin
  drawings — see decisions log for why).
- `src/socratese/chunking/models.py` — `Chunk` dataclass (`note_path`,
  `note_title`, `heading`, `content`, `frontmatter`). Self-contained —
  carries note metadata directly rather than requiring a lookup back
  into `Note`, since retrieval later needs to display "came from X.md
  under heading Y" without a second fetch.
- `src/socratese/chunking/chunker.py` — `chunk_note()`/`chunk_notes()`.
  Splits by markdown heading (`#`–`######`), one chunk per section.
  Content before the first heading becomes its own chunk with
  `heading=""`. Empty/whitespace-only sections (heading-based *and*
  heading-less notes) produce no chunk at all now — fixed after a real
  vault note (`AI/Vector Database.md`: frontmatter tags, no body) proved
  the original "empty note → one empty chunk" behavior wrong; OpenAI's
  embeddings API rejects empty-string input outright.
  **Known gap, deliberately deferred:** no general max-chunk-size
  fallback (e.g. paragraph-boundary splitting) for an oversized
  heading section. Considered and explicitly rejected building this for
  the Excalidraw case specifically — see decisions log; still an open
  gap for some *other* future oversized section if one ever turns up.

**Phase 2: embeddings & vector store — fully built, tested, and proven
against the real vault.**

- `src/socratese/embedding/embedder.py` — `get_client()`/`embed_chunks()`.
  OpenAI `text-embedding-3-small` (model name overridable via
  `EMBEDDING_MODEL` env var, falls back to the hardcoded default).
  `client: OpenAI | None = None` param on `embed_chunks()` for test
  injection — no real API calls in tests.
- `src/socratese/vectorstore/store.py` — `get_collection()`,
  `chunk_id()`, `add_chunks()`, `query()`. Chroma `PersistentClient`,
  stored at `platformdirs.user_data_dir("socratese")` (data dir, not
  config — this is a rebuildable index, unlike the vault list). `upsert`
  (not `add`) keyed on a stable `sha256(note_path::heading)` id, so
  re-indexing an unchanged vault overwrites in place instead of
  duplicating.
- `src/socratese/cli/index.py` — `socratese index <vault_name>` (flat
  command, `all` indexes every tracked vault). `index_vault()` does one
  vault's parse → chunk → embed → store; `index()` is the thin CLI
  wrapper. Wraps the embedding step in `try/except openai.APIError` /
  `finally: save_vaults(vaults)` so a failed API call doesn't lose
  `last_indexed` progress from vaults already processed earlier in the
  same run. Wired into `cli/main.py` via `app.command("index")(index)`
  — flat, not a subgroup (deliberate call: no planned `index
  status`/`index clear` subcommands yet).

**`socratese index learning` has been run successfully for real** —
237 notes, 851 chunks, embedded via OpenAI and stored in the local Chroma
collection. Verified independently of the CLI's own success message:
`vault list` shows a real `last_indexed` timestamp, and the Chroma
collection's `.count()` returns exactly 851, matching. Getting here took
three real bugs found only by running against actual data (not caught by
any fixture-based test) — worth knowing the shape of these for next time:
1. `parser.py` wasn't excluding `.trash/`/`.obsidian/` — was about to
   index deleted notes.
2. `chunker.py`'s heading-less branch had no empty-content guard — a
   real frontmatter-only stub note produced an empty-string chunk, which
   OpenAI's embeddings API flatly rejects (400, not a rate limit).
3. `*.excalidraw.md` files (Obsidian Excalidraw plugin drawings, stored
   as markdown with a `compressed-json` canvas-data blob) tokenize far
   denser than prose (~1 token/char vs ~4) — a 12KB file blew past the
   8192-token embedding limit. Fixed by excluding the file type entirely
   (see decisions log for the tradeoff considered and rejected).

**Phase 3: retrieval — built and tested, verified against the real vault.**

- `src/socratese/embedding/embedder.py` — added `embed_text(text,
  client=None) -> list[float]` alongside the existing `embed_chunks()`.
  Separate function rather than reusing `embed_chunks()`, because that
  one takes `Chunk` objects and reads `.content` off each; a search query
  has no `note_path`/`heading`, so fabricating a `Chunk` to reuse it
  would be the wrong shape. Returns one flat vector, not a list of them.
- `src/socratese/retrieval/models.py` — `RetrievedChunk` dataclass
  (`note_path`, `note_title`, `heading`, `content`, `distance`). Note
  the filename is `models.py`, plural, matching `ingest/`, `chunking/`
  and `vault/`. Deliberately *not* reusing `Chunk`: `frontmatter` is
  never written to Chroma's metadata, so a `Chunk` here would always
  carry an empty dict that lies about what's available.
- `src/socratese/retrieval/retriever.py` — `retrieve(query, n_results=5,
  client=None, collection=None) -> list[RetrievedChunk]`. Embeds the
  query, hands the vector to `store.query()`, maps the result dicts onto
  the dataclass (including `str` → `Path` for `note_path`). The
  `client`/`collection` params exist as injection seams, matching the
  convention at every other seam in the codebase — they're what let
  `test_retriever.py` avoid monkeypatching entirely.
- `src/socratese/vectorstore/store.py` — `query()` now carries Chroma's
  `distances` through in each result dict instead of discarding them.
  They were already in `Collection.query()`'s default `include`, so this
  cost nothing. Watch the plural: the key Chroma returns is `distances`
  (a list per query embedding); the key we build is singular `distance`.
- **No CLI command for retrieval**, deliberately. Retrieved chunks are an
  intermediate that feeds Phase 4's Socratic prompt, not useful one-shot
  output. A Typer command now would be UI for a feature that doesn't
  exist yet.

**Retrieval quality, measured against the real 851-chunk index** (not a
fixture — this is the number that decides Phase 4's design):

| distance | meaning |
|---|---|
| 0.66 – 1.04 | genuine match |
| ~1.27+ | nothing relevant exists in the vault |

Chroma's default space is **squared L2**, so lower is closer and the
value is *not* a 0-1 similarity. OpenAI embeddings are unit-normalized,
so L2 and cosine rank identically — switching the collection to cosine
would only make the number prettier and would cost a full re-index, so
it wasn't done. Real examples: "how does redis persist data to disk?"
→ `Redis Persistence` at 0.665; "how does the attention mechanism work?"
→ `Transformer Architecture` at 0.986. By contrast "what is a vector
database?" returned nothing below 1.270, and the top hits were *Redis
RDB snapshot* chunks — because `AI/Vector Database.md` is the 47-byte
frontmatter-only stub from the Phase 1 bug story, so it produces zero
chunks and the index contains nothing on that topic at all. Retrieval
was correct; the corpus was empty. **A ~1.2 threshold is therefore a
usable "I have nothing for you" signal** — an important Phase 4 input,
since a tutor that questions you about Redis when you asked about vector
databases is a worse failure than one that admits the gap.

Conclusion: **plain vector similarity is good enough.** Hybrid keyword
search and re-ranking (CLAUDE.md phase notes) stay stretch goals.

**Phase 4: Socratic dialogue generation — core built and tested, proven
against the real vault. No CLI surface yet.**

- `src/socratese/dialogue/prompt.py` — `SYSTEM_PROMPT`, `format_chunks()`,
  `build_user_turn()`. Pure string building, no I/O, so the prompt is
  testable with zero mocking (see decisions log for why this is split from
  `socratic.py`). Chunks render as `<excerpt source="Title — Heading">`
  blocks; the heading-less case renders the title alone, with no dangling
  em dash.
- `src/socratese/dialogue/socratic.py` — `get_client()` /
  `ask_questions(topic, chunks, client=None) -> str` *(since removed —
  `Session` subsumed it; see Phase 5/6 below)*. Filters chunks by
  `RELEVANCE_THRESHOLD = 1.2` (inclusive `<=`), then makes one Anthropic
  call. Returns `"No relevant notes found."` when nothing passes the gate —
  **note this is a plain `str`, indistinguishable by type from a real
  question**; see "Not built yet" below.
- Model: `claude-haiku-4-5`, overridable via `DIALOGUE_MODEL`. Read inside
  the function, not at module import, so a `.env` value actually applies.
- `load_dotenv()` in `cli/main.py` was moved above the `socratese` imports.
  It ran *after* them, so `embedder.py`'s module-level
  `os.environ.get("EMBEDDING_MODEL")` had already been evaluated and the
  variable could never be set from `.env`. Latent, not yet biting — the
  default was the wanted value — but it would have silently swallowed the
  new `DIALOGUE_MODEL` too.

**First real question generated** (Claude Opus 5, before the switch to
Haiku — kept verbatim as the quality baseline any prompt change has to
beat, since it can't be reconstructed once Haiku is the default):

> Topic: "how does redis persist data to disk?" — top hit `Redis
> Persistence` at 0.665
>
> *"Your notes say the child writes a point-in-time copy while the parent
> keeps serving — so what becomes of writes the parent accepts after the
> fork but before the child finishes, and which of the listed advantages
> depends on that answer?"*

Assessed against the three failure modes CLAUDE.md names: **did not lead**
(strip the preamble and you still cannot answer it without recalling
copy-on-write), **stayed inside the excerpts**, **did not answer**. Two
rule violations worth knowing: it opened with a preamble restating the
notes (rule 1 says none — the model folded it inside the question sentence),
and it asked two linked questions rather than one. The second "violation"
is arguably the best part of the output, since it forces a connection
across two retrieved chunks — the rule may be wrong, not the model.
**Prompt not yet tuned on this; sample size is one, and it is an Opus
sample, not a Haiku one.**

**Phase 5 (partial): `ask` command and multi-turn dialogue — built, tested,
and used against the real vault.**

- `src/socratese/cli/ask.py` — `socratese ask "<topic>"`, wired flat in
  `cli/main.py` alongside `index`. Retrieves, opens a `Session`, then loops on
  `console.input()` until a blank line or Ctrl-D. `--sources` / `-s` reveals
  which notes grounded the conversation, `--chunks` / `-n` sets how many to
  retrieve.
- `--sources` is **off by default and prints only at the end**. Naming the
  source note mid-conversation tells you where to look, which short-circuits
  exactly the recall the tool exists to force.
- `Session` in `dialogue/socratic.py` — holds the filtered chunks, the growing
  `messages` list, and a lazily-built client. `opening_question()` seeds the
  history with the excerpts; `answer(reply)` appends the reply and returns the
  follow-up. `has_grounding` replaces the old `None` return as the no-match
  gate, and works with no API key set. See the decisions log for why the
  chunks are filtered once and why the assistant's turns are recorded.
- `SYSTEM_PROMPT` gained rules 6-9 for the conversation half: never confirm or
  deny, never correct a contradiction directly, never answer even on "I don't
  know", never repeat a question.
- `ask_questions()` (single-shot) was left in place at this point with no
  callers, and removed in the following commit — see Phase 5/6 below.

Three bugs found in review of the first multi-turn draft, all worth knowing:
1. The CLI still called `ask_questions()` for the opening question, so
   `session.messages` was empty when the loop started — every turn after the
   first was ungrounded, with no excerpts and no memory of the question just
   asked. It *looked* fine because turn 1 was correct.
2. `Session.__init__` assigned `self.chunks = chunks` without filtering, which
   silently killed the relevance gate — `has_grounding` became "did retrieval
   return anything," which is always true.
3. `get_client()` ran during `Session` construction, outside any `try`, so a
   missing `ANTHROPIC_API_KEY` produced a raw traceback. Fixed by making the
   client lazy, which also means the no-match path needs no credentials.

**Prompt verified against the real vault, multi-turn.** Topic: "what is
attention mechnaism?" (typo preserved — retrieval handled it). Four turns
against the `Transformer Architecture` notes, with partial answers and then an
explicit "no idea":

> **>** no idea
>
> *"Look at your notes again — you mention that 'A high score means that the
> model will use more of the value vector.' If the model is going to use more
> of some values and less of others, what needs to happen to those scores
> first so they can be used as weights?"*

Rule 8 held: the surrender produced a smaller question pointing back at the
user's own note, not the answer. **The word "softmax" was never said across
four turns.** Rule 6 held (no confirmation, even on a correct partial answer);
rule 9 held (four distinct questions, progressively narrowing, none a
rephrase). This was the specific failure predicted when choosing Haiku over
Opus, and it did not happen.

**Still untested: rule 7** — what happens when an answer *contradicts* the
excerpts. Partial answers and surrender are covered; a confidently wrong
answer is not.

**Session history, resume, stall detection, vault filtering — built,
tested, used. Merged as PRs #2 and #3.**

- `history/store.py` + `history/recorder.py` — SQLite at
  `user_data_dir/sessions.db`, last ten sessions, incremental writes, raw
  messages stored for replay. A broken database degrades to not recording;
  it never costs a tutoring session. The existing real database was
  migrated in place (`ALTER TABLE` when the `messages` column is absent).
- `socratese resume [id]` — lists recent sessions or continues one, in the
  same row, from stored chunks. Verified against the real database: a
  resumed session continued its ordinals and added no duplicate row.
- `dialogue/stall.py` — orbiting detection over a four-question window.
  The CLI warns when a conversation circles, and reveals the notes on exit
  whether or not `--sources` was passed. This replaced three failed prompt
  attempts; see the decisions log for why it lives in code.
- `--vault / -v` on `ask`, backed by a `vault` metadata tag on every chunk
  and a `where` filter inside Chroma. Real index re-indexed (851 chunks, all
  tagged, no duplicates).
- `tutor.py` — the setup sequence the CLI and TUI now share.

**The terminal app — built and tested; this branch.**

- `tui/app.py`, `tui/commands.py`, `tui/vault_picker.py`. Bare `socratese`
  opens it; the subcommands stay for scripting.
- Commands: `/ask`, `/resume`, `/vaults` (modal picker, or typed names),
  `/add`, `/index` (with a real progress bar), `/sources`, `/end`, `/help`,
  `/quit`. Plain text answers the current question and is echoed as `> …`.
  Slash commands get ghost-text completion, case-insensitively.
- Inherits the terminal's theme (`ansi_color=True`, transparent
  backgrounds, no Header/Footer). Text re-wraps on resize. The transcript
  never scrolls under the input.
- Embedding is batched at 128 per request, which is what makes the progress
  bar real.

Three real bugs from building the TUI, worth knowing the shape of:
1. **SQLite connections cannot cross threads.** The worker opened the
   history connection; `/end` closed it on the event loop. Would have fired
   for every user on their first `/end`. `check_same_thread=False`, safe for
   reasons checked and written into the code.
2. **`query_one(..., SelectionList[str])` crashes at runtime.** Pyright
   accepted the subscripted generic; `isinstance` rejected it. A
   type-checker-clean change to a runtime-checked call is not a safe change.
3. **The progress bar rendered on the input's border row, invisible.** Both
   were `dock: bottom`. My test asserted the CSS class was set — which it
   was — and passed while nothing showed. Geometry assertions replaced it.

Three vacuous assertions were found and replaced in this branch — asserting a
CSS class instead of a region, asserting a position that never changes,
and a test helper that returned widget reprs so phrases could never match.
Same mistake each time: testing the mechanism rather than the outcome. The
`# type: ignore` comments that had been hiding pyright errors in the TUI
tests were removed by typing the app explicitly.

Tests: 249 passing, mirroring source structure under `tests/` —
`vault/test_models.py`, `test_config.py`, `vault/test_discovery.py`,
`cli/test_vault.py`, `cli/test_index.py`, `ingest/test_parser.py`,
`chunking/test_chunker.py`, `embedding/test_embedder.py`,
`vectorstore/test_store.py`, `retrieval/test_retriever.py`,
`dialogue/test_prompt.py`, `dialogue/test_socratic.py`, `dialogue/test_stall.py`,
`history/test_store.py`, `history/test_recorder.py`, `test_tutor.py`,
`tui/test_commands.py`, `tui/test_app.py`, `tui/test_vault_picker.py`.
The TUI tests drive the app headlessly through Textual's pilot
(`pytest-asyncio`, `asyncio_mode = "auto"`).
Config/vault tests use `monkeypatch` on `config.get_config_path` to avoid
touching the real `~/.config/socratese/config.toml`. CLI tests use
`typer.testing.CliRunner`. Ingest/chunking tests use pytest's `tmp_path`
fixture. Embedder tests use a hand-rolled fake OpenAI client (no real API
calls). Vectorstore tests use a *real* Chroma `PersistentClient` pointed
at `tmp_path` (deliberate — a fake collection wouldn't have caught the
`emebeddings`/`metadata` keyword-arg typos that real integration testing
did catch).

`cli/test_index.py` monkeypatches `embed_chunks`/`add_chunks` **on the
`socratese.cli.index` module**, not on their defining modules — `index.py`
imports them by name at import time, so patching `embedding.embedder` or
`vectorstore.store` directly would rebind a name `index.py` never looks at
again, and the test would hit the real API. Covers: no vaults tracked,
unknown vault name, single-vault success, `all`, stale/invalid vault path
skipped, empty vault, and the API-error path (a genuine `openai.APIError`
constructed with an `httpx.Request`) asserting vaults indexed *before* the
failure keep their `last_indexed` while the failed one stays `None`.
Vault fixtures are real directories with a real `.obsidian/` marker under
`tmp_path`, since `index_vault()` validates that marker before parsing.

`retrieval/test_retriever.py` needs **no monkeypatching at all** — it
passes a fake OpenAI client and a real `tmp_path` Chroma collection
straight into `retrieve()` through its injection seams. Worth contrasting
with `cli/test_index.py` above, which has no such seams and must patch
module attributes instead. Covers metadata mapping, the `str` → `Path`
round-trip, nearest-first ordering, both endpoints of Chroma's
squared-L2 scale (identical vectors read 0.0, orthogonal read 2.0),
`n_results`, over-asking a small collection, and an empty collection.
`embedding/test_embedder.py` also gained `embed_text()` coverage, which
it previously had none of — which is exactly how a
`cliet = cliet or get_client()` typo survived to runtime.

Every retrieval test was verified by mutating the source and confirming
it fails (dropping the `Path()` conversion, hardcoding `n_results`,
replacing `distance` with a constant, restoring the `cliet` typo). That
last check caught a weak assertion: an exact-match test asserting
`distance == 0.0` passed *harder* when distance was stubbed to `0.0`,
which is why the test now pins both ends of the scale instead.

`dialogue/test_prompt.py` (8 tests) needs **no fakes at all** — `prompt.py`
is pure. Covers the heading-less label (no dangling em dash), content
preserved verbatim including chunk-internal markdown headings, blank-line
separation between excerpts, and topic-before-excerpts ordering (pinned
deliberately: that ordering is what keeps prompt caching possible later).
One unusual test asserts `SYSTEM_PROMPT` still contains its four
load-bearing rules — a tripwire on prose, not logic, because an edit
dropping "Never state the answer" would degrade every question with no
other test failing anywhere.

`dialogue/test_socratic.py` (17 tests) injects a fake Anthropic client
through the `client=None` seam. The two that matter most: a chunk at
*exactly* `RELEVANCE_THRESHOLD` is kept (pins `<=` as inclusive), and the
API is **never called** when nothing passes the gate — asserting only on
the return value would still pass if the filter ran after the request. The
non-text-block test uses a fake `thinking` block with no `.text` attribute
at all, so a filter that stopped checking `.type` raises rather than
quietly passing.

Both dialogue files were mutation-verified the same way retrieval was —
eight mutations (`<=`→`<`, filter bypassed, `.strip()` removed, `.type`
filter removed, model hardcoded, `max_tokens` lowballed, heading separator
always rendered, excerpts joined with a single newline), each breaking
exactly one test. One-failure-each is the signal worth having: no test is
redundant, none so broad it catches everything.

`dialogue/test_socratic.py` drives `Session` through a fake client
that **snapshots** each call's message list rather than storing the reference
— the session passes `self.messages` by value-of-reference and keeps mutating
it, so an aliasing fake makes every turn look identical. (Found by a test
failing for the wrong reason; a real SDK serialises immediately, so this is a
test artefact, not a source bug.) The load-bearing cases: chunks filtered once
at construction and dropped ones never reaching the prompt; the assistant's
question recorded as an assistant turn (remove it and 4 tests fail); each turn
resending the *whole* history, not just the latest reply; the grounding
appearing exactly once across the conversation; and `has_grounding` answering
with `ANTHROPIC_API_KEY` deleted, which pins the lazy client.

All nine mutations to `Session` break tests — dropping the threshold filter,
flipping `<=` to `<`, not recording assistant turns, sending only the latest
message, dropping the system prompt, hardcoding the model, removing the
`.type` filter, making the client eager, and re-sending the grounding on every turn.

**Type checking:** `npx pyright` from the repo root. Config is pinned in
`pyproject.toml` under `[tool.pyright]` (strict). `src/` and `tests/` are both
clean; see the decisions log for the two necessary casts and the one
suppression. Pyright is not a Python dependency — it runs via node/npx, so it
is deliberately absent from `pyproject.toml`'s `[dev]` extra.

Run `pytest -v` from repo root to confirm (needs `pip install -e ".[dev]"`
in the venv once, for `pytest` itself).

**Manual evaluation is not a test and must not live in `tests/`** — it
costs real money, hits the network, and needs a human to judge the output.
The sweep used to eyeball question quality across topics (prints each
chunk's distance with a PASS/drop marker against the threshold, plus
retrieve/generate timings) belongs in `scripts/eval_dialogue.py`; it is
currently only in shell history. Note that a heredoc version needs
`load_dotenv(".env")`, not bare `load_dotenv()` — the latter calls
`find_dotenv()`, which walks the stack for the calling *file's* directory
and asserts when run from stdin.

**Phase 5/6 (partial): evaluation harness, README, cleanup.**

- `scripts/eval_dialogue.py` — drives scripted conversations through `Session`
  so the prompt rules are judged against transcripts rather than vibes. Four
  scenarios: an answer contradicting the notes (rule 7), a surrender (rule 8),
  three vague answers in a row (rules 6 and 9), and a topic the vault does not
  cover (the relevance gate). `python scripts/eval_dialogue.py 7` runs one.
  ~8 API calls for a full sweep, Haiku, well under a cent.
- **Rule 7 verified — the last untested rule.** A scripted answer describing
  AOF behaviour as RDB drew a question pointing at the contradicting passage,
  not a correction. Phase 4's remaining risk is closed.
- **A tenth prompt rule was drafted, measured twice, and rejected** — see the
  decisions log. Net effect of the exercise: the prompt is unchanged at 9
  rules, but now with evidence behind that rather than assumption.
- `ask_questions()` removed; `Session` subsumed it. `test_session.py` merged
  back into `test_socratic.py` so tests mirror source one-to-one.
- `README.md` written — the repo now has a front door, leading with a real
  transcript. This was the most visible remaining gap.
- `socratese index` had no help text (the only command missing a docstring);
  added.

**Long sessions stall around turn 7 — measured, and it changes the plan.**
An 11-turn scripted session (`eval_dialogue.py`, scenario "9 over a long
session") stays sharp for about six turns and then grinds. Q7-Q11 were five
rewordings of the same unanswered question ("what operation connects the score
to V?"), each quoting the same sentence from the notes back at the user.

Rule 9 holds *literally* the whole way — no two questions share more than half
their words, which is why the first repetition heuristic passed it. The harness
now also detects **orbiting**: any run of five consecutive questions sharing
content words. Q7-Q11 all circle `score, use, vector`; every earlier window
shares nothing at all. Validated by replaying the captured transcript, not by
re-spending on the API.

Consequences, in order of importance:
1. **A session's useful life is ~6 turns.** The Textual app therefore does not
   need deep scrollback for 20-turn conversations; that was the open design
   question this eval was run to answer.
2. **There is no escape hatch when the user is stuck.** Rule 6 forbids
   confirming, rule 8 forbids answering, and nothing lets the model change
   tack or concede a hint. A stuck user can only quit. This promotes the
   "completion state" item from a nice-to-have to the main remaining gap in
   the dialogue design — it is not "no celebration when you win," it is "no
   way out when you lose."
3. **Recitation gets worse the longer a session runs.** The rejected rule 10
   targeted exactly this, and its failure was measured over 4 turns where the
   problem is mild. Worth revisiting *specifically for late turns* rather than
   as a blanket rule — though not by adding a tenth rule, which is what
   degraded rule 9 last time.

**Known retrieval wart, not yet acted on:** "Redis — Run with docker" scores
0.807 on "how does redis persist data to disk?" and passes the gate. It is
about Docker, not persistence. The gate is distance-based only, so an
on-topic-ish note from the right *area* clears it. Has not visibly hurt
question quality — the model ignores the irrelevant excerpt — but it is the
first evidence that a 1.2 cutoff is doing less work than the numbers suggest.

## Not built yet (known gaps, deliberately deferred)

- `vault add` with no `PATH` argument, and no `init` command — the "scan
  OS-conventional roots and let you pick" first-run flow. `discovery.find_vaults()`
  supports it; nothing calls it with default roots yet. `/add <path>` in the
  TUI has the same limitation.
- Chunker has no general max-chunk-size fallback (see above).
- **No `review` command.** The history tables (`turns`, `session_notes`) were
  designed so it could answer "which notes do I keep failing on"; nothing
  queries them that way yet. This is the spaced-repetition foundation and the
  natural next feature.
- **No completion state in a session.** Rule 6 means the tutor never says
  "you've got it". Stall detection now catches the *failure* case (circling);
  the *success* case — you answered well and it keeps drilling — is still
  unhandled. Do not relax rule 6 to fix this.
- **Late-session recitation.** The longer a session runs, the more the model
  quotes the notes back verbatim. Measured, recorded, not acted on: the one
  prompt rule that targeted it made things worse (decisions log). Resume makes
  sessions longer, so this matters more than it did.
- **Provider fallback designed but not built** — see the decisions log.
- **Retrieval lets near-topic noise through.** "Redis — Run with docker" at
  0.807 clears the 1.2 gate for a persistence question. Hasn't visibly hurt
  question quality, but the threshold does less work than the numbers suggest.
- **The TUI has not been driven interactively by the author at every
  size.** Headless tests cover layout geometry at 60/80/100/120 columns; real
  terminal behaviour (Ghostty, font scaling) was verified by the user for the
  reported bugs, not exhaustively.
- **No demo recording.** Phase 6 calls for one and there isn't one.

## Next step

1. **`/review` — which notes do I keep failing on.** Everything it needs is
   stored: per-session grounding chunks with distances, per-turn answers
   including `NULL` for abandonment, and stall outcomes are inferable from
   transcripts. A first cut is a query over `session_notes` joined to
   unanswered/abandoned turns, rendered as "these notes came up N times and
   you bailed on M of them". This is what turns history from a log into
   the spaced-repetition feature the project's premise points at.
2. **A demo recording** (VHS or asciinema) embedded in the README. The TUI
   now exists, so it is recorded once. For a portfolio repo this is worth
   more than any remaining feature.
3. **`init` / `/add` with no path** — the last of the original first-run UX.
4. **Provider fallback** when actually wanted — shape decided.
5. `.trash` history purging — not urgent.

## Environment notes

- Python 3.14, venv at `venv/` (not `.venv/` — both are gitignored).
- `pip install -e ".[dev]"` after any dependency change to `pyproject.toml`.
- Git repo has a remote (`origin/main`); `requirements.txt` was removed
  as redundant with `pyproject.toml`.
- `python-frontmatter`, `openai`, `chromadb`, `python-dotenv`, `anthropic`,
  `textual` all live in main `dependencies`, not `[dev]` — all are runtime
  dependencies of the shipped CLI, not just test tools. `pytest-asyncio` is
  in `[dev]` for the TUI tests; `asyncio_mode = "auto"` is set in
  `pyproject.toml` so they need no per-test marker.
- Type checking is `npx pyright` — a node tool, deliberately not a Python
  dependency. Config is `[tool.pyright]` in `pyproject.toml`, strict, and
  must be clean before committing. (Three commits on the TUI branch went
  through with pyright failing and had to be amended; run it first.)
- `.env` holds `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`, confirmed
  gitignored and untracked. `.env.example` also documents the optional
  `EMBEDDING_MODEL` and `DIALOGUE_MODEL` overrides.
- `load_dotenv()` must stay **above** the `socratese` imports in
  `cli/main.py`. It was below them, which silently broke `EMBEDDING_MODEL`
  (read at `embedder.py` import time). If a linter reorders those imports,
  the bug comes back — `# noqa: E402` on the `socratese` imports is the
  standard pin.
- Both provider accounts have billing credits (OpenAI as of 2026-09-09,
  Anthropic as of 2026-09-12 — the latter after a 400
  `invalid_request_error` on an empty balance). Indexing costs fractions of
  a cent per full run at this vault size; a Haiku question is far less.
- Chroma's local persistent store lives at
  `platformdirs.user_data_dir("socratese")` — not tracked in git, not
  gitignored explicitly either since it's outside the repo entirely.
  `sessions.db` (history) is a separate file in the same directory, so the
  index can be deleted and rebuilt without losing transcripts.
- The real database already holds sessions; one predates raw-message
  storage and cannot be resumed (`*` in the listing). Deleting
  `sessions.db` is safe — it is recreated with the current schema.
