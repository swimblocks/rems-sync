# Add a position name

When a roster uses a position name that isn't REMS's credential name, `upload-deck-evals` can't
find the evaluation to record. Teach it the new name.

1. **Find REMS's name.** In REMS, open the add-credential form for any official, choose type
   **Deck Evaluation**, and find the position's entry, such as
   `Chief Timekeeper Evaluation #1`. The name is the part before ` Evaluation #`.
2. **Add a row** to `_POSITION_TO_CREDENTIAL_PREFIX` in [src/utils.py](../../../src/utils.py),
   from the roster's name to REMS's:
   ```python
   "Chief Timer": "Chief Timekeeper",
   ```
3. **Add a test** in `tests/test_utils.py` that `deck_eval_credential_label("<roster name>", 1)`
   gives `"<REMS name> Evaluation #1"`.
4. **Add the row** to the [position names table](../../reference/sheets.md#position-names).
5. Run `ruff check .` and `pytest -q`, and open a pull request.
