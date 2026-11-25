# Member output schema implementation plan

**Goal:** Stabilize member output columns using design 0002.

**Architecture:** A pure CSV projection module loads TOML schemas and validates raw CSV
headers before pandas sees them. CLI member commands opt in; the registration script always
uses a committed schema, preserving raw intermediate files.

**Tech stack:** Python, standard-library csv/tomllib, pandas, Click, PowerShell; no new deps.

**Spec:** [Design 0002](../../design/0002-member-output-schema.md).

## Constraints and review focus

- Exact header matching; preserve textual values and row order.
- Append/drop extras, warn/error missing headers; reject ambiguous input and invalid schemas.
- No schema keeps the old behaviour. Invalid data cannot truncate files or clear sheets.
- Script uses the committed schema with append/error, without new switches, before uploads.
- Read only the November 16 export's header for the committed compatibility schema.
- Check duplicate/unnamed headers, ragged rows, policy override precedence, and source text
  that pandas could turn into numbers or NA. Verify script phase order with a stubbed CLI.

## Tasks

1. [x] Add failing unit tests for schema loading and CSV projection. Implement
   `src/member_schema.py`: `load_schema`, `project_csv`, and an internal module entry
   point for schema/header preflight. Run the targeted tests.
2. [x] Add failing CLI integration tests for both refresh outputs and upload, policy overrides,
   and errors leaving files/Google untouched. Add `--schema`, `--extra-columns` and
   `--missing-columns` to the two member commands. Run targeted tests.
3. [x] Extract only old header names into `schemas/rems-members.toml` with append/error.
   Test its column positions. Add script tests using fake executables (no network/keychain),
   then wire schema validation before Google login and member validation before downstream
   steps. Run script tests from outside the repo.
4. [x] Update all evergreen docs named by the design, including script usage, schema policies,
   manual preflight, tutorial and configuration examples. Mark the design implemented.
5. [x] Run full lint/tests, documentation link checks and a fresh diff review. Fix findings,
   commit and push for local review; stop before opening the implementation PR.

## Execution notes

- Shared schema/projection tests were observed failing before the module was added.
- CLI integration tests failed on missing options, then passed with the shared projection.
- Script orchestration tests failed before preflight was added, then passed in PowerShell 7
  and Windows PowerShell 5.1 using fake network commands and real local validation.
- Whole-branch review found embedded newline translation on file reads; a failing regression
  test now covers it and `project_csv_file` opens with `newline=""`.
- The existing sheet writer dropped legitimate `Unnamed:` names; schema-projected output now
  explicitly preserves validated columns, covered through the real writer with a fake client.
- No shared sheet was written and no live REMS or Google login was run.
