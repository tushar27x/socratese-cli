# Socratese — Progress

Last updated: 2026-09-05

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
- Tests: 22 passing, mirroring source structure under `tests/` —
  `vault/test_models.py`, `test_config.py`, `vault/test_discovery.py`,
  `cli/test_vault.py`. Config/vault tests use `monkeypatch` on
  `config.get_config_path` to avoid touching the real
  `~/.config/socratese/config.toml`. CLI tests use `typer.testing.CliRunner`.

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
- Nothing past vault management — no ingest, chunking, embedding,
  vector store, retrieval, or dialogue code exists yet. All of
  `src/socratese/{ingest,chunking,embedding,vectorstore,retrieval,dialogue}/`
  are still docstring-only stub files.

## Next step (agreed, not yet started)

**Phase 1: vault parsing & chunking.**
- `src/socratese/ingest/parser.py` — walk a tracked vault's markdown
  files, parse YAML frontmatter and `[[wikilinks]]`.
- `src/socratese/chunking/chunker.py` — split parsed notes into
  semantically useful chunks.

Building it against a real vault: `learning` is already tracked
(`/home/tushar27x/notes/obsidian/learning`) — `socratese vault list`
to confirm it's still there.

## Environment notes

- Python 3.14, venv at `venv/` (not `.venv/` — both are gitignored).
- `pip install -e ".[dev]"` after any dependency change to `pyproject.toml`.
- Git repo has a remote (`origin/main`); `requirements.txt` was removed
  as redundant with `pyproject.toml`.
