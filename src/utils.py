import re
from datetime import date, datetime, timedelta

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

_POSITION_TO_CREDENTIAL_PREFIX = {
    "Chief Timer": "Chief Timekeeper",
    "Admin Desk": "Administration Desk",
    "Stroke Judge": "Judge of Stroke",
    "Session Referee": "Referee",
    "Timer": "Introduction to Swimming Officiating",
}


def normalize_position_for_credential(position):
    """
    Translate a Positions-tab role label into the prefix used in REMS credential
    names (e.g. 'Chief Timer' -> 'Chief Timekeeper'). Returns the input unchanged
    if no special mapping is needed.
    """
    return _POSITION_TO_CREDENTIAL_PREFIX.get(position.strip(), position.strip())


def deck_eval_credential_label(position, eval_number):
    """Build the credential label expected on the add-credential form for a deck eval."""
    prefix = normalize_position_for_credential(position)
    return f"{prefix} Evaluation #{eval_number}"

def find_existing_deck_eval_in_dates(credentials, position, dates):
    """Return the first existing 'Deck Evaluation' credential for `position` whose
    start_date falls within `dates` (set of YYYY-MM-DD strings), or None.

    This is the single source of truth for "is this eval already recorded?"
    Used by both `upload-deck-evals` (passes the meet's full session date set,
    enforcing the rule that a position can only be evaluated once per meet) and
    `add-deck-eval` (passes the specific date, or a wider set if the caller
    provides --meet-dates).
    """
    if not dates:
        return None
    date_set = {d for d in dates if d}
    prefix = normalize_position_for_credential(position).lower()
    for cred in credentials:
        cred_type = (cred.get('type') or '').strip().lower()
        cred_name = (cred.get('name') or '').strip().lower()
        if cred_type != 'deck evaluation' or not cred_name.startswith(prefix + ' '):
            continue
        iso = parse_rems_date_to_iso(cred.get('start_date'))
        if iso and iso in date_set:
            return cred
    return None


def _swap_day_month_iso(iso_date):
    """Return the YYYY-MM-DD date with day and month swapped, or None if the
    swap would be invalid (e.g. day > 12 means the swap is unambiguous and
    can't be a legacy bug)."""
    try:
        year, month, day = iso_date.split('-')
        year, month, day = int(year), int(month), int(day)
        if month > 12 or day > 12:
            return None
        return date(year, day, month).isoformat()
    except (ValueError, AttributeError):
        return None


def find_existing_deck_eval_with_swapped_date(credentials, position, dates):
    """Return the first existing 'Deck Evaluation' credential for `position`
    whose start_date is the day/month swap of one of `dates` — the legacy
    m/d/Y vs d/m/Y bug from before the date-format fix. Returns None if no
    such credential exists.

    Excludes credentials that already match a real meet date (those aren't bug
    artifacts, they're current records).
    """
    if not dates:
        return None
    real_dates = {d for d in dates if d}
    prefix = normalize_position_for_credential(position).lower()
    for cred in credentials:
        cred_type = (cred.get('type') or '').strip().lower()
        cred_name = (cred.get('name') or '').strip().lower()
        if cred_type != 'deck evaluation' or not cred_name.startswith(prefix + ' '):
            continue
        iso = parse_rems_date_to_iso(cred.get('start_date'))
        if not iso or iso in real_dates:
            continue
        swapped = _swap_day_month_iso(iso)
        if swapped and swapped in real_dates:
            return cred
    return None


def count_existing_deck_evals(credentials, position):
    """
    Count how many existing 'Deck Evaluation' credentials this member has for the given position.
    Used to determine whether the next eval is #1 or #2 (or beyond). Applies position
    name normalization (e.g. 'Chief Timer' -> 'Chief Timekeeper').

    Args:
        credentials: list of dicts as returned by REMSClient.get_member_credentials
        position: the official position string from the Positions tab
    """
    prefix = normalize_position_for_credential(position).lower()
    count = 0
    for cred in credentials:
        cred_type = (cred.get('type') or '').strip().lower()
        cred_name = (cred.get('name') or '').strip().lower()
        if cred_type != 'deck evaluation':
            continue
        if cred_name.startswith(prefix + ' '):
            count += 1
    return count

def to_rems_date_format(value):
    """
    Convert a date input to the d/m/Y format REMS forms expect (and the same
    format flatpickr renders in the UI). Returns DD/MM/YYYY.

    Accepts:
      - datetime.date / datetime.datetime
      - ISO strings YYYY-MM-DD
      - Already-formatted DD/MM/YYYY (returned as-is; ambiguous numbers like
        04/11/2025 are treated as d/m/Y per the REMS convention)

    Note: previous releases of this tool sent dates as MM/DD/YYYY; REMS
    silently misinterpreted those as d/m/Y, recording (e.g.) 04/11/2025
    as 4 November rather than 11 April. Any credentials added before the fix
    need their start_date corrected in REMS.
    """
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    s = str(value).strip()
    if re.match(r'^\d{2}/\d{2}/\d{4}$', s):
        return s
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
    raise ValueError(f"Unsupported date format: {value!r} (use YYYY-MM-DD or DD/MM/YYYY)")


def default_meet_dates_for(eval_iso_date):
    """
    Default meet-date set for an evaluation: the most recent Wednesday on or
    before `eval_iso_date` through the next Sunday on or after `eval_iso_date`,
    inclusive. Returns a set of YYYY-MM-DD strings.

    If the eval falls on a non-meet day (Mon/Tue) the bracket will span more
    than one week — in that case the caller should pass --meet-dates explicitly.
    """
    WED, SUN = 2, 6  # Monday is 0 via date.weekday()
    d = datetime.strptime(eval_iso_date, "%Y-%m-%d").date()
    start = d
    while start.weekday() != WED:
        start -= timedelta(days=1)
    end = d
    while end.weekday() != SUN:
        end += timedelta(days=1)
    out = set()
    cur = start
    while cur <= end:
        out.add(cur.isoformat())
        cur += timedelta(days=1)
    return out


def parse_rems_date_to_iso(value):
    """
    Parse a date value from REMS (typically rendered by flatpickr as d/m/Y, e.g.
    '12/04/2026' meaning 12 April 2026) into ISO format YYYY-MM-DD.

    Returns None for empty/unparseable inputs rather than raising — the caller
    may want to skip those rather than fail the whole batch.
    """
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    s = (str(value) if value is not None else '').strip()
    if not s:
        return None
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', s)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None
