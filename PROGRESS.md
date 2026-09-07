# Socratese — Progress

Last updated: 2026-09-07

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
  explicit `onerror` handler for permission errors.
- `src/socratese/cli/vault.py` — `socratese vault {list,add,remove,rescan}`,
  wired into `cli/main.py` via `app.add_typer(vault_app, name="vault")`.
  Rich for output; `Console(soft_wrap=True)` (needed — default wrapping
  broke on long paths, see git history for why).
- Tracked vault: `learning` at `/home/tushar27x/notes/obsidian/learning`
  (`socratese vault list` to confirm it's still there).

**Phase 1: vault parsing & chunking — fully built and tested.**

- `src/socratese/ingest/models.py` — `Note` dataclass (`path`, `title`,
  `frontmatter`, `wikilinks`, `content`).
- `src/socratese/ingest/parser.py` — `parse_note()`/`parse_vault()`.
  Uses `python-frontmatter` for YAML frontmatter (main dependency, not
  dev-only — the shipped CLI needs it at runtime). `WIKILINK_RE` regex
  handles all three Obsidian link forms: `[[Target]]`,
  `[[Target|Display]]`, `[[Target#Heading]]` — captures the target only,
  discards display text/heading anchor via `[^\]]*` before the closing
  `]]`.
- `src/socratese/chunking/models.py` — `Chunk` dataclass (`note_path`,
  `note_title`, `heading`, `content`, `frontmatter`). Self-contained —
  carries note metadata directly rather than requiring a lookup back
  into `Note`, since retrieval later needs to display "came from X.md
  under heading Y" without a second fetch.
- `src/socratese/chunking/chunker.py` — `chunk_note()`/`chunk_notes()`.
  Splits by markdown heading (`#`–`######`), one chunk per section.
  Content before the first heading becomes its own chunk with
  `heading=""`. Empty sections produce no chunk. Heading-less notes
  become a single whole-note chunk.
  **Known gap, deliberately deferred:** no max-chunk-size fallback yet —
  an oversized heading-less section won't get split further (e.g. at
  paragraph boundaries). Add if/when a real note in `learning` produces
  a chunk too large to embed sensibly.

Tests: 34 passing, mirroring source structure under `tests/` —
`vault/test_models.py`, `test_config.py`, `vault/test_discovery.py`,
`cli/test_vault.py`, `ingest/test_parser.py`, `chunking/test_chunker.py`.
Config/vault tests use `monkeypatch` on `config.get_config_path` to avoid
touching the real `~/.config/socratese/config.toml`. CLI tests use
`typer.testing.CliRunner`. Ingest/chunking tests use pytest's `tmp_path`
fixture — no real vault touched.

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
- Chunker has no max-size fallback (see above).
- Nothing past chunking — no embedding, vector store, retrieval, or
  dialogue code exists yet. All of
  `src/socratese/{embedding,vectorstore,retrieval,dialogue}/` are still
  docstring-only stub files.
- No CLI command wires up ingest/chunking yet (no `socratese index` or
  similar) — `parse_vault()`/`chunk_notes()` are only exercised by tests
  so far, not run end-to-end against the real `learning` vault.

## Next step (up for discussion, not yet started)

**Phase 2: embeddings & vector store.**

This is the decision CLAUDE.md flags as mine to argue through, not one
to be handed. Open questions to resolve first:

1. Offline/local embeddings vs. hosted API — depends on whether an API
   key is already assumed elsewhere (the Socratic dialogue LLM will
   need one regardless; could mean reusing that provider for embeddings
   too, for simplicity).
2. Vault size ballpark — determines whether a simple in-memory/SQLite-
   backed store is enough, or a real vector DB (Chroma, LanceDB, etc.)
   is warranted.

Once decided: pick + justify an embedding model, pick + justify a
vector store, then build `src/socratese/embedding/` and
`src/socratese/vectorstore/`.

## Environment notes

- Python 3.14, venv at `venv/` (not `.venv/` — both are gitignored).
- `pip install -e ".[dev]"` after any dependency change to `pyproject.toml`.
- Git repo has a remote (`origin/main`); `requirements.txt` was removed
  as redundant with `pyproject.toml`.
- `python-frontmatter` lives in main `dependencies`, not `[dev]` — it's
  a runtime dependency of `ingest/parser.py`, not just a test tool.
