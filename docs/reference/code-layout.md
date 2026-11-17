# Code layout

| Path | Holds |
|---|---|
| [`src/main.py`](../../src/main.py) | Every CLI command (Click), and the deck-evaluation decisions (`_resolve_deck_eval_credential`, the recheck checks). |
| [`src/rems_client.py`](../../src/rems_client.py) | `REMSClient`: REMS login, the session cache, re-login on 403, and every REMS call. Transient errors are retried by `urllib3` `Retry`, set up in `__init__`. |
| [`src/gsheet.py`](../../src/gsheet.py) | Google access (ADC), Drive search, reading and writing sheet tabs, and parsing the roster's Grid, Meet and Officials tabs. |
| [`src/utils.py`](../../src/utils.py) | Seasons, REMS IDs and dates; position names; finding an existing deck evaluation by date. |
| [`tests/`](../../tests/) | `pytest`, one file per module plus `test_upload_deck_evals.py`. HTTP to REMS is faked with `responses`; nothing touches REMS or Google. |
| [`terraform/`](../../terraform/) | The Google Cloud project ([reference](terraform.md)). |
| [`docs/`](../) | These docs ([index](../README.md)). |
