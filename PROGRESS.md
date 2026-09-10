# Socratese — Progress

Last updated: 2026-09-10

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

Tests: 58 passing, mirroring source structure under `tests/` —
`vault/test_models.py`, `test_config.py`, `vault/test_discovery.py`,
`cli/test_vault.py`, `cli/test_index.py`, `ingest/test_parser.py`,
`chunking/test_chunker.py`, `embedding/test_embedder.py`,
`vectorstore/test_store.py`.
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

Run `pytest -v` from repo root to confirm (needs `pip install -e ".[dev]"`
in the venv once, for `pytest` itself).

## Not built yet (known gaps, deliberately deferred)

- `vault add` with no `PATH` argument — currently `PATH` is required.
  The "scan OS-conventional roots and let you pick a candidate"
  behavior implied by the `[PATH]` brackets in the original design was
  explicitly deferred, not forgotten.
- No `init` command — the decisions log describes a bounded scan from
  `Path.home()` + OS-typical roots (Documents, iCloud Drive, etc.) for
  first-run setup. `discovery.find_vaults()` supports this (just needs
  a root passed in), but nothing calls it with those default roots yet.
- Chunker has no general max-chunk-size fallback (see above).
- No `README.md` in the repo at all. The remote (`origin/main`) is
  therefore a portfolio repo with no front door — the most visible
  remaining doc gap. Open question, not yet decided: write a minimal one
  now (setup + `vault add` → `index`, i.e. what actually works today),
  or wait until `ask` exists so it can document a real end-to-end flow
  instead of being rewritten at Phase 4.
- Nothing past indexing — no retrieval or dialogue code exists yet. All
  of `src/socratese/{retrieval,dialogue}/` are still docstring-only stub
  files.

## Next step

1. **Phase 3: retrieval.** Similarity search against the now-populated
   Chroma store. `vectorstore.store.query()` already exists and takes a
   raw embedding, but nothing calls it yet. Planned shape — *designed,
   not yet written*:
   - Add `embed_text(text, client=None) -> list[float]` to
     `embedding/embedder.py`. Needed because `embed_chunks()` takes
     `Chunk` objects and reads `.content` off each; a search query has no
     `note_path`/`heading`, so fabricating a `Chunk` just to reuse that
     function would be the wrong shape. Leaves `embed_chunks` untouched.
   - `retrieval/retriever.py` gets
     `retrieve(query: str, n_results: int = 5) -> list[dict]` — embed the
     query, hand the vector to `store.query()`. Pure function, no new
     state, no knowledge of Chroma or OpenAI internals (that's what the
     existing module split is for). `n_results` stays a parameter rather
     than a constant because Phase 4's prompt will want to tune how many
     chunks it feeds the model.
   - **No CLI command for this step.** Retrieved chunks aren't useful
     one-shot output on their own; they're an intermediate that feeds
     Phase 4's Socratic prompt. A Typer command now would be UI for a
     feature that doesn't exist.
   - Then `tests/retrieval/test_retriever.py`, combining
     `vectorstore/test_store.py`'s real-Chroma-on-`tmp_path` approach
     with `test_embedder.py`'s fake OpenAI client.
2. Given only ~850 chunks, plain vector similarity is probably
   sufficient to start; hybrid keyword search / re-ranking (per CLAUDE.md
   phase notes) is a stretch goal, not a blocker.
3. Consider whether `.trash` history is worth also purging from the
   vault config over time, or whether excluding it at parse-time is
   sufficient forever — not urgent, just noting it as a possible
   future edge case (e.g. if the vault grows a very large `.trash/`).

## Environment notes

- Python 3.14, venv at `venv/` (not `.venv/` — both are gitignored).
- `pip install -e ".[dev]"` after any dependency change to `pyproject.toml`.
- Git repo has a remote (`origin/main`); `requirements.txt` was removed
  as redundant with `pyproject.toml`.
- `python-frontmatter`, `openai`, `chromadb`, `python-dotenv` all live in
  main `dependencies`, not `[dev]` — all are runtime dependencies of the
  shipped CLI, not just test tools.
- `.env` holds `OPENAI_API_KEY`, confirmed gitignored and untracked.
  `load_dotenv()` is called at the top of `cli/main.py`. OpenAI account
  has billing credits added (as of 2026-09-09) — indexing costs
  fractions of a cent per full run at this vault size.
- Chroma's local persistent store lives at
  `platformdirs.user_data_dir("socratese")` — not tracked in git, not
  gitignored explicitly either since it's outside the repo entirely.
