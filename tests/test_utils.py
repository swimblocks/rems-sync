import pytest
from src.utils import parse_season_to_id
import click

def test_parse_season_to_id_year():
    assert parse_season_to_id("2017") == 226
    assert parse_season_to_id("2021") == 230
    assert parse_season_to_id("2022") == 224
    assert parse_season_to_id("2023") == 225
    assert parse_season_to_id("2024") == 231
    assert parse_season_to_id("2025") == 232

def test_parse_season_to_id_year_range():
    assert parse_season_to_id("2017-2018") == 226
    assert parse_season_to_id("2021-2022") == 230
    assert parse_season_to_id("2022-2023") == 224
    assert parse_season_to_id("2023-2024") == 225
    assert parse_season_to_id("2024-2025") == 231
    assert parse_season_to_id("2025-2026") == 232

def test_parse_season_to_id_invalid_input():
    with pytest.raises(click.BadParameter, match="Season must be a year"):
        parse_season_to_id("abc")
    with pytest.raises(click.BadParameter, match="Season must be a year"):
        parse_season_to_id("2025-")
    with pytest.raises(click.BadParameter, match="Season must be a year"):
        parse_season_to_id("2025-202X")
    with pytest.raises(click.BadParameter, match="Season must be a year"):
        parse_season_to_id("2025-202")

def test_validate_rems_id():
    from src.utils import validate_rems_id
    assert validate_rems_id("SC24074099") is True
    assert validate_rems_id("SC12345678") is True
    assert validate_rems_id("SC1234567") is False # too short
    assert validate_rems_id("AB12345678") is False # wrong prefix
    assert validate_rems_id("SC12345678A") is False # extra char
    assert validate_rems_id(None) is False

def test_deck_eval_credential_label():
    from src.utils import deck_eval_credential_label
    assert deck_eval_credential_label("Inspector of Turns", 1) == "Inspector of Turns Evaluation #1"
    assert deck_eval_credential_label("Starter", 2) == "Starter Evaluation #2"
    # Normalization handles known mismatches between sheet and REMS labels
    assert deck_eval_credential_label("Chief Timer", 1) == "Chief Timekeeper Evaluation #1"
    assert deck_eval_credential_label("Admin Desk", 2) == "Administration Desk Evaluation #2"
    assert deck_eval_credential_label("Stroke Judge", 1) == "Judge of Stroke Evaluation #1"
    assert deck_eval_credential_label("Session Referee", 1) == "Referee Evaluation #1"
    assert deck_eval_credential_label("Timer", 1) == "Introduction to Swimming Officiating Evaluation #1"

def test_normalize_position_for_credential():
    from src.utils import normalize_position_for_credential
    assert normalize_position_for_credential("Chief Timer") == "Chief Timekeeper"
    assert normalize_position_for_credential("Inspector of Turns") == "Inspector of Turns"
    assert normalize_position_for_credential("  Admin Desk  ") == "Administration Desk"

def test_find_existing_deck_eval_in_dates():
    from src.utils import find_existing_deck_eval_in_dates
    credentials = [
        {'type': 'Clinic',           'name': 'Inspector of Turns Clinic',           'start_date': '12/04/2026'},
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #1',     'start_date': '12/04/2026'},
        {'type': 'Deck Evaluation', 'name': 'Starter Evaluation #1',                'start_date': '15/03/2024'},
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #2',     'start_date': '20/05/2025'},
    ]
    # Hit on the same meet date for the same position.
    found = find_existing_deck_eval_in_dates(credentials, 'Inspector of Turns', {'2026-04-12'})
    assert found is not None and found['name'] == 'Inspector of Turns Evaluation #1'
    # Date outside the set → no match.
    assert find_existing_deck_eval_in_dates(credentials, 'Inspector of Turns', {'2026-04-13'}) is None
    # Wrong position → no match even if date matches.
    assert find_existing_deck_eval_in_dates(credentials, 'Starter', {'2026-04-12'}) is None
    # Position normalization works (Chief Timer -> Chief Timekeeper).
    creds_ct = [{'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1', 'start_date': '12/04/2026'}]
    assert find_existing_deck_eval_in_dates(creds_ct, 'Chief Timer', {'2026-04-12'}) is not None
    # Empty / None dates -> no match (defensive).
    assert find_existing_deck_eval_in_dates(credentials, 'Inspector of Turns', None) is None
    assert find_existing_deck_eval_in_dates(credentials, 'Inspector of Turns', set()) is None
    # Existing cred with unparseable start_date is skipped, not crashed on.
    creds_bad = [{'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #1', 'start_date': 'garbage'}]
    assert find_existing_deck_eval_in_dates(creds_bad, 'Inspector of Turns', {'2026-04-12'}) is None


def test_count_existing_deck_evals():
    from src.utils import count_existing_deck_evals
    credentials = [
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #1'},
        {'type': 'Deck Evaluation', 'name': 'Starter Evaluation #1'},
        {'type': 'Clinic',           'name': 'Inspector of Turns Clinic'},
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #2'},
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1'},
    ]
    assert count_existing_deck_evals(credentials, "Inspector of Turns") == 2
    assert count_existing_deck_evals(credentials, "Starter") == 1
    assert count_existing_deck_evals(credentials, "Chief Finish Judge") == 0
    # Position name from the sheet is normalized before matching
    assert count_existing_deck_evals(credentials, "Chief Timer") == 1

def test_to_rems_date_format():
    from src.utils import to_rems_date_format
    from datetime import date
    # REMS expects d/m/Y (matches the flatpickr display config); 12 April 2026 -> 12/04/2026.
    assert to_rems_date_format("2026-04-12") == "12/04/2026"
    assert to_rems_date_format("12/04/2026") == "12/04/2026"
    assert to_rems_date_format(date(2026, 4, 12)) == "12/04/2026"
    with pytest.raises(ValueError, match="Unsupported date format"):
        to_rems_date_format("12-Apr-2026")


def test_default_meet_dates_for():
    from src.utils import default_meet_dates_for
    # Friday Apr 10, 2026: meet brackets Wed Apr 8 -> Sun Apr 12.
    assert default_meet_dates_for("2026-04-10") == {
        "2026-04-08", "2026-04-09", "2026-04-10", "2026-04-11", "2026-04-12",
    }
    # Wednesday itself: same 5-day bracket.
    assert default_meet_dates_for("2026-04-08") == {
        "2026-04-08", "2026-04-09", "2026-04-10", "2026-04-11", "2026-04-12",
    }
    # Sunday itself: same 5-day bracket.
    assert default_meet_dates_for("2026-04-12") == {
        "2026-04-08", "2026-04-09", "2026-04-10", "2026-04-11", "2026-04-12",
    }
    # Tuesday (off-meet): bracket spans two weeks (prev Wed -> next Sun).
    # Tuesday Apr 14, 2026 -> Wed Apr 8 to Sun Apr 19.
    tuesday_bracket = default_meet_dates_for("2026-04-14")
    assert min(tuesday_bracket) == "2026-04-08"
    assert max(tuesday_bracket) == "2026-04-19"
    assert len(tuesday_bracket) == 12


def test_parse_rems_date_to_iso():
    from src.utils import parse_rems_date_to_iso
    from datetime import date
    # REMS displays dates in d/m/Y format (per flatpickr config)
    assert parse_rems_date_to_iso("12/04/2026") == "2026-04-12"
    assert parse_rems_date_to_iso("1/4/2026") == "2026-04-01"
    # ISO passes through
    assert parse_rems_date_to_iso("2026-04-12") == "2026-04-12"
    # date object
    assert parse_rems_date_to_iso(date(2026, 4, 12)) == "2026-04-12"
    # blanks / unparseable -> None (so dedup can skip the row rather than crash)
    assert parse_rems_date_to_iso("") is None
    assert parse_rems_date_to_iso(None) is None
    assert parse_rems_date_to_iso("garbage") is None

