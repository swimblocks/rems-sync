# Code layout

| Path | Holds |
|---|---|
| [`src/main.py`](../../src/main.py) | Every CLI command (Click), and the deck-evaluation decisions (`_resolve_deck_eval_credential`, the recheck checks). |
| [`src/credentials.py`](../../src/credentials.py) | Saved logins: `config.toml`, the keychain, the environment override, and `KeyringSessionStore` for REMS sessions ([configuration](configuration.md)). |
| [`src/rems_client.py`](../../src/rems_client.py) | `REMSClient`: REMS login, the session cache, re-login on 403, and every REMS call. Transient errors are retried by `urllib3` `Retry`, set up in `__init__`. |
| [`src/gsheet.py`](../../src/gsheet.py) | Google access (ADC), Drive search, reading and writing sheet tabs, and parsing the roster's Grid, Meet and Officials tabs. |
| [`src/utils.py`](../../src/utils.py) | Seasons, REMS IDs and dates; position names; finding an existing deck evaluation by date. |
| [`scripts/refresh-registration.ps1`](../../scripts/refresh-registration.ps1) | The whole season refresh in one go ([reference](refresh-registration-script.md)). |
| [`tests/`](../../tests/) | `pytest`, one file per module plus `test_upload_deck_evals.py` and `test_auth_cli.py`. HTTP to REMS is faked with `responses`, and an autouse fixture in `conftest.py` swaps in an in-memory keychain and config file; nothing touches REMS, Google or the real keychain. |
| [`terraform/`](../../terraform/) | The Google Cloud project ([reference](terraform.md)). |
| [`docs/`](../) | These docs ([index](../README.md)). |
