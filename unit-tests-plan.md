# User request
pergit is completely missing unit tests, I would like to add that to the codebase, including mocking p4 and git commandline calls. Let's make a plan for this

# Plan

## 1. Test infrastructure setup

- Use `unittest` from the standard library (no external dependencies, matches project philosophy).
- Create a `tests/` directory at the project root alongside `pergit/`.
- Add a `tests/__init__.py` (empty).
- Use `unittest.mock` (stdlib) for mocking subprocess calls.
- Run tests with: `python -m pytest tests/` or `python -m unittest discover -s tests`.
  - Prefer pytest for nicer output, but keep tests unittest-compatible so either runner works.
  - Add `pytest` as an optional dev dependency (e.g. `pip install pytest`).

## 2. Mocking strategy

All external commands flow through two chokepoints in `common.py`:

| Function | Mechanism | Used for |
|---|---|---|
| `run()` | `subprocess.run()` | Most p4/git commands |
| `run_with_output()` | `subprocess.Popen()` | p4 sync, git add/commit with real-time output |

Plus one direct `subprocess.run()` call in `changelist.py` and `review.py` for `p4 change -i` (stdin input).

**Approach:** Mock at the `common.run` and `common.run_with_output` level for command-module tests (sync, edit, list_changes, changelist, review). This avoids dealing with subprocess internals and lets us return `RunResult` objects directly.

For `common.py` tests themselves, mock `subprocess.run` and `subprocess.Popen` to verify the wiring.

Create a shared test helper (`tests/helpers.py`) with:
- `make_run_result(returncode, stdout_lines, stderr_lines)` — factory for `RunResult`.
- `MockRunDispatcher` — a class that maps command patterns to `RunResult` responses, to be used as a side_effect for `mock.patch('pergit.common.run')`. This makes it easy to set up multi-command test scenarios.

## 3. Test modules and coverage targets

### `tests/test_common.py` — common.py

- `run()`: verify it calls `subprocess.run` with correct args, returns `RunResult`, handles dry_run.
- `run_with_output()`: verify it calls `Popen`, invokes callback, returns `RunResult`.
- `get_workspace_dir()` / `is_workspace_dir()`: use `tmp_path` / `tempfile` to create dirs with/without `.git`.
- `join_command_line()`: pure function, test quoting edge cases.

### `tests/test_cli.py` — cli.py

- `create_parser()`: verify parser accepts all subcommands and flags.
- `run_command()`: verify dispatching to the correct command function (mock the command functions).

### `tests/test_sync.py` — sync.py

Mock `pergit.common.run` and `pergit.common.run_with_output`.

- `git_is_workspace_clean()`: mock `git status --porcelain` returning empty (clean) vs non-empty (dirty).
- `p4_is_workspace_clean()`: mock `p4 opened` returning no files vs files opened.
- `git_changelist_of_last_commit()`: mock `git log` with various commit message formats, verify CL extraction.
- `get_latest_changelist_affecting_workspace()`: mock `p4 info` + `p4 changes`, verify CL parsing.
- `get_file_count_to_sync()`: mock `p4 sync -n`, verify count parsing.
- `parse_p4_sync_line()`: pure function, test various p4 output formats.
- `get_writable_files()`: pure function, test stderr parsing.
- `P4SyncOutputProcessor`: feed it synthetic p4 sync output lines, verify stats tracking.
- `sync_command()`: integration-style test mocking all subprocess calls, verify end-to-end flow for `latest`, `last-synced`, specific CL, force mode, dirty workspace rejection.

### `tests/test_edit.py` — edit.py

Mock `pergit.common.run`.

- `check_file_status()`: mock `p4 opened` for opened/not-opened files, different CLs.
- `find_common_ancestor()`: mock `git merge-base`, verify hash extraction.
- `get_local_git_changes()`: mock `git merge-base` + `git diff --name-status`, verify `LocalChanges` population for adds/mods/dels/renames.
- `include_changes_in_changelist()`: mock `p4 add/edit/delete/reopen`, verify correct p4 operations for each change type. Test dry_run skips execution.
- `edit_command()`: end-to-end with mocked subprocess.

### `tests/test_list_changes.py` — list_changes.py

Mock `pergit.common.run`.

- `get_commit_subjects_since()`: mock `git log --oneline --reverse`, verify subject extraction.
- `get_enumerated_change_description_since()`: verify numbered formatting.
- `list_changes_command()`: end-to-end.

### `tests/test_changelist.py` — changelist.py

Mock `pergit.common.run` and `subprocess.run` (for `p4 change -i`).

- `create_changelist()`: mock `git log` + `p4 change -i`, verify spec construction and CL number parsing.
- `get_changelist_spec()`: mock `p4 change -o`, verify spec return.
- `extract_description()`: pure function, test with real-looking specs.
- `replace_description_in_spec()`: pure function, verify field replacement.
- `split_description_message_and_commits()`: pure function, test splitting numbered lists from message text.
- `update_changelist()`: mock fetch + update flow.
- `changelist_new_command()` / `changelist_update_command()`: end-to-end.

### `tests/test_review.py` — review.py

Mock `pergit.common.run` and `subprocess.run`.

- `p4_shelve_changelist()`: verify correct p4 shelve command.
- `open_changes_for_edit()`: verify it wires through to edit module correctly.
- `p4_add_review_keyword_to_changelist()`: mock `p4 change -o` returning spec without `#review`, verify it inserts keyword and calls `p4 change -i`.
- `review_new_command()`: end-to-end flow (create CL, open files, add keyword, shelve).
- `review_update_command()`: end-to-end flow with/without `--description` flag.

## 4. Implementation order

1. **Test infrastructure** — Create `tests/` dir, `helpers.py` with `make_run_result` and `MockRunDispatcher`.
2. **`test_common.py`** — Foundation tests; validates mocking approach works.
3. **`test_list_changes.py`** — Simplest command module, good for validating the pattern.
4. **`test_cli.py`** — Parser and dispatch tests.
5. **`test_edit.py`** — Moderate complexity, tests change detection and p4 operation mapping.
6. **`test_changelist.py`** — Tests spec parsing and construction.
7. **`test_sync.py`** — Most complex module, depends on patterns established above.
8. **`test_review.py`** — Builds on changelist and edit test patterns.

## 5. File tree after implementation

```
pergit/
  __init__.py
  __main__.py
  cli.py
  common.py
  sync.py
  edit.py
  list_changes.py
  changelist.py
  review.py
tests/
  __init__.py
  helpers.py
  test_common.py
  test_cli.py
  test_sync.py
  test_edit.py
  test_list_changes.py
  test_changelist.py
  test_review.py
```
