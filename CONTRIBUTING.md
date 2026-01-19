# Contributing to rems-sync

This file contains instructions and development standards for to follow when making changes to this repository.

## Core Principles

*   **Test-Driven:** All new functionality must be accompanied by tests. All existing tests must pass before a change is considered complete.
*   **Simplicity and Refactoring:** Strive for simple, readable code. If a change introduces complexity, consider refactoring to improve clarity.
*   **Comprehensive Documentation:** All user-facing changes must be reflected in the documentation (`README.md`). All new code should have clear docstrings.

## On Every Change

Before finalizing a change, please ensure the following checklist is completed:

-   [x] **Run Tests After Every Change:** After making any code changes and before indicating completion, I MUST run all tests and confirm they pass.
-   [ ] **Tests:**
    -   [ ] Have I added new tests for the changes I've made?
    -   [ ] Do all tests (new and existing) pass?
-   [ ] **Documentation:**
    -   [ ] Have I updated the `README.md` to reflect any changes to the CLI or functionality?
    -   [ ] Have I added or updated docstrings for any new or modified functions/classes?
-   [ ] **Code Quality:**
    -   [ ] Is the code easy to understand?
    -   [ ] Have I considered any opportunities for refactoring?
-   [ ] **CLI:**
    -   [ ] Are the command-line options and arguments clear and consistent with the existing CLI?
    -   [ ] Is the help text for the commands up-to-date?

## Prompts for a Helpful Agent

### When adding a new feature:

"Your primary goal is to add the new feature as requested, but it is equally important that you add comprehensive tests that validate the feature's functionality. Also, please update the `README.md` to include instructions on how to use the new feature."

### When fixing a bug:

"Your task is to fix the bug as described. Before you start, try to write a test that reproduces the bug. After you've fixed the bug, ensure that the new test and all existing tests pass."

### When refactoring code:

"Your goal is to refactor the code to improve its structure, readability, or performance. Please ensure that all existing tests continue to pass after the refactoring is complete. No new functionality should be introduced."
