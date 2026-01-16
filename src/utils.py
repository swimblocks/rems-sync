import re
import click

def parse_season_to_id(season_str):
    """
    Parses a season string (e.g., "2025" or "2025-2026") and returns the calculated season_id.
    """
    start_year = None
    match_year_range = re.match(r'(\d{4})-(\d{4})', season_str)
    if match_year_range:
        start_year = int(match_year_range.group(1))
    else:
        try:
            start_year = int(season_str)
        except ValueError:
            raise click.BadParameter("Season must be a year (e.g., '2025') or a year range (e.g., '2025-2026').")

    base_year = 0
    base_season_id = 0

    if start_year >= 2024:
        base_year = 2024
        base_season_id = 231
    elif start_year == 2022 or start_year == 2023:
        base_year = 2022
        base_season_id = 224
    else: # start_year < 2022
        base_year = 2017
        base_season_id = 226

    season_id = base_season_id + (start_year - base_year)
    return season_id

def validate_rems_id(rems_id):
    """
    Validates that a REMS ID starts with 'SC' followed by at least 8 digits.
    """
    if not rems_id:
        return False
    return bool(re.match(r'^SC\d{8,}$', str(rems_id)))
