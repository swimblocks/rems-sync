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

def test_to_mmddyyyy():
    from src.utils import to_mmddyyyy
    from datetime import date
    assert to_mmddyyyy("2026-04-12") == "04/12/2026"
    assert to_mmddyyyy("04/12/2026") == "04/12/2026"
    assert to_mmddyyyy(date(2026, 4, 12)) == "04/12/2026"
    with pytest.raises(ValueError, match="Unsupported date format"):
        to_mmddyyyy("12-Apr-2026")

