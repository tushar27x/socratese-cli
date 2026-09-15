# CLAUDE.md — Obsidian Socratic RAG CLI

## What this project is

A RAG (Retrieval-Augmented Generation) CLI tool that indexes an Obsidian
vault and helps the user learn their own notes better by questioning them
Socratically — instead of just answering "what does X mean," it should ask
probing questions that make the user derive the answer from their own notes.

This file exists so Claude Code doesn't accidentally build the whole thing
for me. Read it before doing anything else in this repo.

---

## 1. Your role: senior dev giving direction, not a silent implementer

This is a learning project going on my resume, and I'm new to a lot of
this. What I need from you is what a senior engineer would give a junior
during pairing/mentoring: clear next steps, real working code snippets I
can look over and copy in myself, and project structure decisions made
with actual judgment — not withheld until I guess my way there, and not a
vague conceptual gesture I have to translate into real code alone.

**Default behavior for basically everything:**
1. Tell me the concrete next step. Not "think about how you'd structure
   this" — actually say "next, create `X`, it should do `Y`, here's why."
2. Give me a real, working code snippet for the piece we're on. It's fine
   for this to be directly usable — I will read it, understand it, and
   copy/paste it into my editor myself. You are not editing my files
   directly; I am, by hand, which is how I actually absorb it.
3. Explain the reasoning behind structural/design choices (why this
   module boundary, why this pattern, why this library call) so I'm not
   just transcribing — but don't gate the snippet behind the explanation
   landing first. Give both together.
4. When a step involves a judgment call (naming, folder layout, where a
   piece of logic belongs), just make the call the way an experienced
   dev would and tell me why, rather than opening it up as a question for
   me to decide from scratch.

**Project structure:**
- Lay out the project the way a senior dev would set up a real,
  professional Python CLI package (proper `src/` layout or equivalent,
  clear module boundaries, `pyproject.toml`, tests directory mirroring
  source structure, etc.) and tell me where new code should live as we
  build each piece, rather than leaving that to me to figure out.

**What actually stays mine to do:**
- Typing the code into the editor myself (copy-pasting your snippets in,
  not you writing to the files directly) — this is how I keep it "not
  vibe-coded": I still see, place, and understand every line.
- Making the final call on anything you flag as genuinely a toss-up
  between reasonable options, when you think it's worth my input.
- Running things, hitting the actual errors, and coming back with what
  broke — don't pre-empt debugging I haven't hit yet.

**Still avoid, unless I ask:**
- Silently rewriting my existing code to fix a bug without telling me
  what was wrong and why — explain the bug plainly, give me the fix as a
  snippet, but don't just patch the file yourself.
- Skipping ahead multiple steps without checking in — keep the pace
  matched to what I've actually built so far.

**Always okay to do freely:**
- Give real, working code snippets — not just illustrative toy examples.
- Explain concepts, error messages, stack traces, and design tradeoffs.
- Point me to relevant documentation or source, in addition to explaining.
- Run tests/linters/formatters and report results factually.
- Search the codebase for me.
- Make structural/naming/design decisions directly and explain why,
  rather than posing them as open questions.
- Review my code with direct, specific feedback.

If I seem stuck or the conversation is dragging without forward progress,
default to just giving me the next concrete step and the code for it.

If I seem stuck or the conversation is dragging without forward progress,
default to just giving me the answer with an explanation. Erring toward
unblocking me is better than erring toward making me guess.

---

## 2. I'm learning nvim — give me nvim commands, not just file paths

I recently switched from VS Code to nvim. Whenever you'd normally say
"open file X and look at line Y" or "search for Z in the codebase," give
me the actual nvim keybinding/command to do it, not just the instruction.

Examples of what I want instead of vague pointers:

| Instead of saying...                        | Say something like...                                              |
|----------------------------------------------|----------------------------------------------------------------------|
| "Open `chunker.py`"                          | `:e src/ingest/chunker.py`                                          |
| "Look at line 42"                            | `42G` (or `:42`)                                                     |
| "Find where `embed_chunks` is defined"       | `:grep "def embed_chunks" \| copen` or `gd` if LSP is attached       |
| "Search the codebase for TODOs"              | Telescope: `:Telescope live_grep` then type `TODO`, or `:grep TODO -r .` |
| "Jump back after checking a definition"      | `<C-o>` to jump back, `<C-i>` to jump forward                        |
| "See all references to a function"           | `gr` (LSP references), or quickfix via `:grep`                       |
| "Compare two versions of a file"             | `:Gdiffsplit` (vim-fugitive) or `:DiffviewOpen`                      |
| "Rename a variable everywhere"               | `:%s/old/new/gc` (with confirm) or LSP `<leader>rn` if configured    |
| "Check the file tree"                        | `:Ex` (netrw) or `:Telescope find_files` / `<leader>e` if nvim-tree bound |

Use the quickfix list (`:copen`, `:cnext`, `:cprev`) whenever pointing me
at multiple locations (e.g. "here are 3 places `chunk_size` is used").

If I mention a plugin I have installed (Telescope, fugitive, LSP, etc.),
prefer commands from that plugin over generic vim. If you're not sure what
I have installed, ask, or suggest I check `:Lazy` / `:PackerStatus` /
whatever plugin manager I'm using.

---

## 3. Quality bar (this is a portfolio piece)

Even though I'm writing the logic myself, hold me to a standard I could
put in front of an interviewer. When reviewing my work, check for and
question me on:

- **Architecture**: clear separation between ingestion (vault parsing),
  chunking, embedding, vector store, retrieval, Socratic prompt/dialogue
  generation, and the CLI layer itself. If I'm tangling these together,
  ask me why before I go further.
- **Config & secrets**: no hardcoded API keys or paths — `.env` +
  `.env.example`, and confirm `.gitignore` actually excludes `.env`.
- **Testing**: ask whether each new module has tests before we move on.
  Unit tests for chunking/retrieval logic, at least a couple of
  integration tests for the CLI end-to-end.
- **Error handling**: what happens with an empty vault, a malformed
  note, a missing API key, a rate-limited API call? Ask, don't assume.
- **Docs**: README with setup instructions, architecture diagram/notes,
  and usage examples should stay current as we build — nudge me to update
  it rather than doing it for me.
- **Git hygiene**: small, meaningful commits with clear messages over
  giant dumps. If I'm about to commit a huge blob of unrelated changes,
  say something.
- **Type hints / docstrings**: expect them on public functions; ask me
  to add them if missing rather than adding them yourself.

---

## 4. Suggested phases (for pacing, not prescription)

Use this to gauge where I am and what kind of hints are relevant — not
as a rigid plan I can't deviate from.

1. **Vault parsing & chunking** — walk the Obsidian vault, parse markdown
   + frontmatter + `[[wikilinks]]`, split into semantically useful chunks.
2. **Embeddings & vector store** — pick and justify an embedding model
   and a vector store (local vs. hosted — this is a good decision to make
   me argue through, not hand to me).
3. **Retrieval** — similarity search, maybe hybrid with keyword search,
   re-ranking.
4. **Socratic dialogue generation** — this is the interesting/hard part:
   prompt design that produces *questions*, not answers, grounded in
   retrieved chunks. Push me to think about failure modes (the model just
   answering anyway, leading questions, etc.).
5. **CLI polish** — argument parsing (click/typer/argparse — make me pick
   and defend it), good UX, sensible commands (`index`, `ask`, `review`, etc.).
6. **Testing, docs, demo** — the stuff that makes this resume-ready.

---

## 5. Decisions made so far

Living log of real architecture decisions, so context doesn't get lost
between sessions and you don't suggest something that contradicts a
choice I already made and reasoned through. Append to this as we go —
don't silently revise past entries; if a decision changes, add a new
entry noting what changed and why.

### CLI framework: Typer
- Chosen over click/argparse/fire for less boilerplate via type-hint
  inference, and because it's the modern convention in AI-tooling CLIs.
- Pairs with **Rich** for pretty one-shot output (tables, panels,
  spinners, progress bars) — Typer's own author built Rich, and Typer
  already uses it internally for help text.
- Rich alone ≠ a TUI. It's "the command runs and prints something
  nice," not a persistent full-screen app.

### TUI: Textual, for interactive parts only
- Hybrid approach: Typer handles one-shot, scriptable subcommands
  (`index`, `vault add`, `config`). **Textual** (also Rich-author's
  project) powers the actual Socratic dialogue session (`ask`/`review`),
  since a multi-turn conversation fits a persistent scrollable-pane app
  better than repeated single-shot commands.

### Vault discovery: bounded scan from OS-conventional roots, not full-disk
- Never scan the entire filesystem — slow, permission-error-prone, and
  invasive on Windows/macOS.
- Start from `pathlib.Path.home()` and a small set of OS-typical
  candidate roots (Documents, iCloud Drive on macOS, etc.), with a
  bounded recursion depth.
- Use `os.walk()` with in-place `dirnames` pruning to skip `.git`,
  `node_modules`, `venv`, etc. Handle permission errors via `onerror`
  instead of crashing the whole scan.
- Detect vaults by presence of a `.obsidian` directory.

### Vault list storage: user config, not cache
- Reasoning: cache should be safely re-derivable from a source of
  truth; here the filesystem is technically the source of truth, but
  vaults can move and the user needs to *correct* that — which is a
  config concern, not a cache concern. ("Would I be annoyed to lose
  this, or just shrug and re-scan?" — annoyed → config.)
- Use `platformdirs.user_config_dir()` (not `user_cache_dir()`) for the
  storage location, so it resolves correctly per OS (XDG on Linux,
  `Application Support` on macOS, `%APPDATA%` on Windows).

### Config file format: TOML
- Chosen over JSON/YAML: idiomatic for *tool* config in the Python
  ecosystem (`pyproject.toml`, `ruff.toml`), human-editable, no
  YAML-style implicit type coercion footguns.
- Read via stdlib `tomllib` (3.11+); write via `tomli-w` or `tomlkit`.

### Vault config shape: list of vault objects with metadata
```toml
[[vaults]]
name = "Personal Notes"
path = "/home/user/Documents/PersonalVault"
last_indexed = "2026-09-01T10:00:00Z"
```
- Fields: `name` (friendly display), `path`, `last_indexed` (basis for
  a future "this vault has changed, re-index?" check).

### First run / vault management UX
- No silent auto-scan on unrelated commands — surprising filesystem
  behavior is bad CLI UX. Scanning is explicit, via `init` or
  `vault add`.
- Dedicated `vault` subcommand group is the primary interface; the TOML
  file is a stable, inspectable artifact but not the expected editing
  surface:
  ```
  socratese vault list
  socratese vault add [PATH]
  socratese vault remove <NAME>
  socratese vault rescan
  ```

### Embedding model: OpenAI `text-embedding-3-small`
- Anthropic has no embeddings API, so this choice is independent of
  whatever Phase 4's dialogue LLM provider ends up being.
- Cheap, well-documented, the standard default in the RAG ecosystem —
  legible choice over Voyage AI's marginal quality edge.

### Vector store: Chroma, local persistent client
- Single-user desktop CLI, no concurrent access or network service
  needed — rules out hosted DBs (Pinecone, Qdrant Cloud) as unnecessary
  ops overhead.
- Chroma over LanceDB: LanceDB's scale advantages (columnar/Parquet)
  don't matter at thousands-of-notes scale; Chroma is the more
  recognizable default.

### Vault content scope: skip `.trash/`, `.obsidian/`, and `*.excalidraw.md`
- `.trash/` (Obsidian's deleted-notes folder) and `.obsidian/` (plugin
  config) are never real vault content — pruned in `ingest/parser.py`
  via a local `SKIP_DIRS`, separate from `vault/discovery.py`'s
  same-named constant (different concern: pruning while *finding*
  vaults on disk vs. pruning *inside* a vault already found).
- `*.excalidraw.md` files (Obsidian Excalidraw plugin drawings, stored
  as markdown containing a `compressed-json` blob of canvas data) are
  skipped entirely, not chunked/embedded. Real discovery: a 12KB
  Excalidraw file blew past OpenAI's 8192-token embedding limit because
  compressed JSON tokenizes far more densely than prose (~1 token/char,
  not ~4). Considered building the general max-chunk-size fallback
  (chunker's already-known deferred gap) instead, but rejected for this
  case: splitting compressed JSON into sub-chunks produces noise no
  Socratic dialogue could meaningfully question the user about — not
  worth the embedding cost. Tradeoff accepted: any real prose a user
  types inside a drawing's text elements is also skipped; no
  Excalidraw-aware parsing was built for this narrow case (6 files in
  the tracked vault).

### Dialogue module split: pure `prompt.py`, I/O-owning `socratic.py`
- `dialogue/prompt.py` holds `SYSTEM_PROMPT`, `format_chunks()` and
  `build_user_turn()` — pure string building, zero I/O. `dialogue/socratic.py`
  owns the client and the one API call.
- Reasoning: the prompt is the part that gets iterated on twenty times, and
  it should be testable with no mocking at all — same boundary as pure
  `chunking/chunker.py` vs. client-owning `embedding/embedder.py`.
  `tests/dialogue/test_prompt.py` consequently needs no fakes whatsoever.
- Retrieved chunks are rendered as `<excerpt source="Title — Heading">`
  blocks, not markdown headers: chunk content *is* markdown with its own
  `#` headings, so markdown-in-markdown gives the model no reliable
  boundary. `RetrievedChunk` already carries title/heading, so the label
  costs no extra lookup.
- The notes go in the **user** turn, never the system prompt. System stays
  byte-identical across every request, so prompt caching stays possible
  later without rework (caching is a prefix match — volatile content must
  come after stable content).

### Relevance threshold: enforced in the dialogue layer, at 1.2
- The ~1.2 cutoff measured in Phase 3 is now code: `RELEVANCE_THRESHOLD`
  in `socratic.py`, applied as `distance <= RELEVANCE_THRESHOLD`.
- It lives here, not in `retrieval/`, because "how confident is confident
  enough" is a conversation-quality judgment, not a search one. `retrieve()`
  stays honest about what it found; this layer decides what's worth asking
  about.
- Verified against the real index, not just fixtures: "what is a vector
  database?" drops all five hits and never reaches the API.

### Dialogue LLM provider: Anthropic
- Independent of the embedding choice — that was OpenAI only because
  Anthropic has no embeddings API, so it constrained nothing here.
- Model name is read from `DIALOGUE_MODEL` *inside* the function rather
  than at module import, so a value loaded from `.env` still takes effect.
  (`embedder.py` reads `EMBEDDING_MODEL` at import time and had exactly
  this bug — see the `fix:` commit that reordered `load_dotenv()`.)

### Dialogue model: Claude Haiku 4.5
- $1/$5 per MTok vs Claude Opus 5's $5/$25. The larger saving is structural:
  Haiku 4.5 predates adaptive thinking, so it generates no thinking tokens
  at all. On Opus 5 those are on by default and billed as output, and for a
  one-sentence question they dwarfed the ~60 tokens actually returned.
- Tradeoff accepted knowingly: prompt adherence is the hard part of this
  project, and "don't answer," "don't lead," "stay inside the excerpts" are
  the instructions a smaller model drops first — and drops *subtly*, since
  a leading question still reads like a question. `DIALOGUE_MODEL` allows a
  spot-check against a larger model with no code change.
- `max_tokens=4096` kept despite the switch: it is a ceiling, not a
  reservation, and unused tokens cost nothing.

### Provider fallback: designed, not yet built
- Planned shape, triggered by hitting an empty Anthropic credit balance: an
  adapter per provider in `dialogue/providers.py`, each translating *both*
  the request shape (Anthropic takes `system=` as a param, OpenAI as a
  message) and the error vocabulary (each SDK's `APIError` → a shared
  `ProviderError`), so `socratic.py` imports no SDK and the fallback loop
  stays provider-agnostic.
- A fallback would return a `Question(text, provider)` rather than a bare
  string — a silent provider switch is unacceptable, since question quality
  shifting for an unattributable reason would send prompt tuning chasing
  the wrong cause.
- Deliberately *not* built yet: credits were added instead. A permanent
  billing failure would have made OpenAI the de-facto primary provider by
  accident rather than by choice, which is a decision to make, not to
  inherit from an error path.

### Multi-turn dialogue: `Session` holds the conversation, the CLI drives it
- `Session` in `dialogue/socratic.py` (not a new module — a session *is*
  dialogue generation, and this avoids moving it later when the single-shot
  `ask_questions()` gets collapsed into it).
- It owns the three things that change together: the filtered chunks, the
  growing `messages` list, and the client. The rest of this codebase is plain
  functions because none of it had state; a conversation does.
- **Chunks are retrieved and filtered once, at construction.** Re-retrieving
  per turn would let the grounding drift toward whatever the last answer
  happened to mention, and re-appending the excerpts each turn would bloat the
  history and pull the model onto the newest copy.
- **The model's own questions are appended as assistant turns.** Without that
  it cannot see what it already asked, and prompt rule 9 ("never repeat a
  question") has nothing to work from.
- **The client is lazy** (`@property` over `self._client`), so `has_grounding`
  answers "your notes have nothing on this" with no API key set. Being told
  your vault is empty on a topic should not require credentials — and it makes
  `Session` constructible in tests without touching the environment.
- CLI loop lives in `cli/ask.py`: a plain `console.input()` REPL, not Textual
  yet. Deliberate pacing — the decisions log still commits to Textual for the
  polished UX, but putting the state in `Session` makes that a UI change rather
  than an architecture change. A mid-loop API error `break`s instead of exiting,
  so a failed turn still ends the session cleanly with `--sources` intact.
- `--sources` prints **after** the session, not alongside each question.
  Revealing mid-conversation tells you where to look and short-circuits the
  recall the tool exists to force; revealing at the end tells you what to go
  re-read.

### Prompt rules 6-9: never confirm, never answer, never repeat
- Rules 1-5 govern a single question; 6-9 govern what happens after an answer.
- **Rule 6 ("never confirm or deny") is the load-bearing one and the most
  debatable.** Withholding "yes, that's right" would be unhelpful in most
  tutors; in a Socratic one it is the whole method, because confirmation ends
  the deriving. Accepted knowingly, with the consequence noted under open
  questions below.
- **Rule 8 ("if they say they don't know, still don't answer") verified against
  the real vault.** See PROGRESS.md for the transcript: an explicit "no idea"
  produced a smaller question pointing back at the user's own note, not the
  answer. This was the specific failure predicted for a smaller model, and it
  held.

### Type checking: pyright strict, pinned in `pyproject.toml`
- Editor-local strictness meant a reviewer cloning the repo saw different
  diagnostics than the author. Now `[tool.pyright]` with
  `typeCheckingMode = "strict"` is checked in, so the repo is the authority.
- Strict was initially going to be lowered to `standard` (500 errors), but the
  errors turned out to trace to a handful of real root causes — unannotated
  injection seams (`collection=None`, `client=None`), bare `dict` generics on
  the dataclasses, and `chromadb.ClientAPI` not being re-exported, which had
  silently made **every type in `store.py` `Unknown` and therefore unchecked**.
  Fixing those reached zero. "Strict and clean" beats "we turned the bar down."
- One suppression: `reportMissingTypeStubs = false`, because chromadb ships no
  stubs. Its runtime types are still inferred and checked.
- Two casts that are necessary rather than workarounds, both commented in
  `store.py`: `list` invariance means `list[list[float]]` is not a
  `list[PyEmbedding]`, and Chroma types query-result fields `Optional` because
  `include` can omit them (all three are in the default include).

### Prompt rules stop at 9 — a tenth was tried twice and rejected
- `scripts/eval_dialogue.py` drives scripted conversations through `Session`
  (a wrong answer, a surrender, a string of vague ones) so rules can be judged
  without typing by hand. Not a test and never under `tests/`: it costs money,
  hits the network, and has no assertions.
- **Measured result, first attempt.** Follow-ups were opening with a reflection
  ("You said X, but...", "I hear you mention X, but let me ask more
  specifically"). A rule 10 forbidding preamble in follow-ups had *no effect* —
  the phrasing persisted verbatim.
- **Measured result, second attempt.** Re-reading the transcripts, the real
  defect was narrower: the model sometimes recited the excerpts back ("Your
  notes say Q represents the previous state of the decoder"), which does the
  recall work the question exists to force. A rule 10 targeting reciting rather
  than preamble made things *worse*: the opening question started reciting when
  it previously had not, and turns 2-4 all re-asked the same thing, breaking
  rule 9. Four turns of no progress against four turns of real progress.
- **Conclusion: reverted to 9 rules.** Two lessons worth keeping. Reflecting
  the user's own answer back is not the same failure as reciting their notes,
  and is probably fine. And prompt dilution is real at this model size — adding
  a tenth rule measurably degraded adherence to an existing one, so new rules
  have to earn their place against the rules they weaken.
- **Rule 7 verified.** A scripted answer describing AOF behaviour as RDB drew
  "Look back at your notes about what the parent process does while the child
  is writing the RDB file" — a question pointing at the contradicting passage,
  not a correction. This was the last untested rule.

### `ask_questions()` collapsed into `Session`
- The single-shot function lost its last caller when `ask` went multi-turn.
  Removed rather than left as dead-but-tested code.
- Its unique coverage was ported into `test_socratic.py` first (system prompt
  not duplicated into the user turn, `max_tokens` headroom, multiple text
  blocks joined in order, `get_client` behaviour), and `test_session.py` was
  merged into `test_socratic.py` so tests mirror source structure one-to-one
  again.

### Session history: SQLite, not Chroma, capped at ten
- `history/store.py`, a separate `sessions.db` in `user_data_dir`. Not Chroma:
  the questions asked of history are relational ("my last ten", "which notes
  do I keep failing on"), not nearest-neighbour — and the Chroma collection is
  disposable (re-run `index`) while transcripts are not. They must not share a
  store that a re-index could wipe. stdlib `sqlite3`, so no new dependency.
- **Both representations, each doing one job.** `turns` is the queryable view
  (`review` and spaced repetition need it); `messages` is the raw conversation
  as sent to the API, stored verbatim as JSON for replay. Neither can do the
  other's job. Written in the same operation so they cannot drift.
- `session_notes` stores chunk *content*, not just identifiers, so a resumed
  session rebuilds the exact prompt even after a re-index.
- **Writes are incremental** — the question is stored before its answer
  exists. A Ctrl-C'd session leaves its transcript, and `answer = NULL` records
  that the user walked away, which is signal.
- **Pruning is by last activity, not id.** Resuming an old session must
  protect it; ordering by `id` would let it be culled by newer sessions the
  user abandoned. Pruning runs at session *start* so the newest is never the
  one dropped.
- **History never interrupts tutoring.** A database that cannot be opened or
  written degrades to not recording, silently. A full disk must not cost a
  session over a logging feature. `PRAGMA foreign_keys = ON` is load-bearing:
  sqlite3 disables it by default, which would have made every `ON DELETE
  CASCADE` silently inert.
- `check_same_thread=False` on the connection, because the TUI opens a session
  on a worker thread and closes it on the event loop. Safe here for two
  checked reasons: `sqlite3.threadsafety` is 3 on this build, and one user
  drives one turn at a time, so the connection is never used concurrently.

### Resume reuses the row, restores stored chunks, never re-filters
- A resumed conversation continues in the row it started in. Splitting would
  fragment the transcript and burn two of ten slots on one conversation.
- Chunks come from storage, not a fresh retrieval: the messages already refer
  to those excerpts, so re-retrieving after a re-index could swap them and
  leave the transcript incoherent. And they are not re-filtered by threshold —
  that happened at session start, and re-filtering could drop a note the
  conversation has already been quoting.
- An unanswered final question is re-asked on resume; an answered one gets the
  follow-up the user never saw.

### Stall detection lives in code, because the prompt could not do it
- Three prompt attempts, all measured against real transcripts: a rule against
  preamble in follow-ups (no effect), a rule against reciting the notes (made
  rule 9 worse), and an amendment to rule 8 telling the model to stop when the
  excerpts cannot settle what it is asking (no effect — a real React session
  reproduced and circled six turns again).
- **The pattern: this model follows concrete per-turn rules well and
  conditional meta-rules poorly.** "Never answer" holds; "notice X, then
  change mode" does not. So the noticing moved into `dialogue/stall.py`, which
  is deterministic and testable, and the intervention belongs to the UI.
- The heuristic is *orbiting*, not repetition: a sliding window of four
  questions all sharing content words. No pair need look alike, which is why
  pairwise similarity missed it. Topic words are excluded (every question in a
  React session says "React") and tokens under three characters are dropped
  (`v` is noise in a warning). Validated by replaying captured transcripts,
  not by re-spending on the API.
- **The React session was the key finding.** The user's notes describe what
  the virtual DOM is *for* but never mention diffing two virtual trees, so
  the model was driving at an answer its source material did not contain — a
  rule 3 violation, and unwinnable. When a session stalls, the notes are now
  revealed on exit whether or not `--sources` was passed: "your note is
  incomplete here" is the most useful thing a notes-based tutor can say.

### `tutor.py`: one setup sequence shared by every UI
- The CLI had session setup inline — which vaults count, what to retrieve,
  whether anything cleared the gate. The TUI needed the identical sequence.
  Two copies would drift, so it became `tutor.start()` and `tutor.resume()`.
- It raises typed `TutorError`s rather than printing, so each UI owns its own
  rendering. It is the one layer that knows about config, retrieval and
  dialogue together.

### Vault filtering: a metadata tag, one collection, filtered inside Chroma
- Every vault's chunks live in one collection with a `vault` metadata field;
  `retrieve(vaults=[...])` becomes a `where` clause. One collection with a
  filter beats one per vault because selecting *several* vaults stays a single
  query.
- **Filtering happens inside Chroma, not after.** Post-filtering a global
  top-5 gives "however many of those five came from the vault you asked for",
  sometimes zero. Asking for five from one vault must return five.
- `vault` is a parameter on `add_chunks`, not a field on `Chunk`: which vault
  a note lives in is a storage concern, and the chunker has no idea vaults
  exist.
- An unknown `--vault` name is rejected, not ignored. Silently searching
  everything when a filter was asked for is worse than failing.
- Chunks indexed before the field existed report `vault=""` rather than
  breaking retrieval; the real index was re-indexed (851 chunks, no
  duplicates, thanks to `upsert` on the stable id).

### The terminal app: bare `socratese`, subcommands kept, thread workers
- `socratese` with no subcommand opens the Textual app (Typer's
  `invoke_without_command`). Every subcommand still works for scripting and
  is what the CLI tests exercise.
- Every network call runs in a `@work(thread=True)` worker. Textual's loop is
  single-threaded; an embedding or dialogue request on it would freeze the
  whole interface, including the spinner meant to show something is happening.
- **Only a leading slash makes a command.** Topics contain slashes ("tcp/ip"),
  so `parse()` checks the first character. Plain text is an answer.
- **The app inherits the terminal's theme.** `ansi_color=True` emits the
  terminal's own sixteen ANSI colours instead of Textual's palette, and every
  background is transparent so the terminal's ground (and wallpaper) shows
  through. `Header` and `Footer` were dropped: both paint solid bars.
- **A scroll of `Static` widgets, not a `RichLog`.** `RichLog` wraps text once
  at write time and never again; increasing the terminal's font scale means
  fewer columns, which left every earlier line too wide and cut off.
  `Static` re-wraps whenever its width changes.
- The progress bar and the input share **one docked container with explicit
  heights.** Docking them separately put the bar on the input's border row,
  invisible; `height: auto` on the container collapsed it to zero and let the
  transcript scroll under the input. Both found by asserting on geometry
  rather than on CSS classes.
- Answers are echoed as `> text`; commands are not. Without the echo the pane
  showed only questions, which read as a list of demands.
- A custom `SlashCommandSuggester`, because `SuggestFromList`'s
  `case_sensitive=False` does not match a differently-cased prefix in the
  installed Textual. It folds inside the method rather than relying on the
  caching wrapper, so a direct call and the widget agree.

### Embedding is batched (128 per request)
- Sending a whole vault in one request works until it does not: a large vault
  can exceed the request limit, and one failure costs every chunk. Batching
  also makes real progress reportable instead of a spinner that cannot move.
- Order is preserved and tested: embeddings are matched to chunks by position
  downstream, so a reordered batch would silently attach every vector to the
  wrong note.

---

## 6. When in doubt

Ask me a question before acting. If a request is ambiguous between
"explain this to me" and "do this for me," assume I want the former unless
I say otherwise.