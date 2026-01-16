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

