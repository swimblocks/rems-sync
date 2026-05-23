import click
import re
import pandas as pd
from io import StringIO
from .rems_client import REMSClient, get_mfa_code
from .gsheet import (
    get_gspread_client, get_drive_session, get_credentials_identity,
    write_df_to_sheet, read_sheet_tab, read_sheet_rows,
    parse_meet_tab, parse_grid_session_dates, parse_officials_name_to_rems_id,
    list_drive_subfolders, find_drive_sheet_in_folder, update_cell,
)


# Root Drive folder under which seasons -> meets -> sheets are organised.
# (Specific to the Rowing-Hamilton officials Drive layout.)
ROW_OFFICIALS_ROOT_FOLDER_ID = "0AFczXKtVbxcaUk9PVA"
DEFAULT_ROSTER_SHEET_NAME_SUBSTRING = "Officials Roster"


def _discover_meet_sheets(season, root_folder_id, roster_substring, interactive):
    """Find roster sheets via the Drive folder hierarchy:
    `root_folder_id/<season>/<meet>/<...Officials Roster sheet>`.

    Returns a list of `{'id', 'name', 'meet_name'}` dicts. When `interactive`
    is true and >1 meet is found, prompts the user to pick one or 'a' for all.
    When `interactive` is false, returns every discovered meet (process all)."""
    drive = get_drive_session()

    # Shared-drive IDs start with "0A" (e.g. 0AFczXKtVbxcaUk9PVA). When the
    # configured root is a shared drive we have to scope queries to that drive.
    drive_id = root_folder_id if root_folder_id.startswith("0A") else None

    season_folders = list_drive_subfolders(drive, root_folder_id, drive_id=drive_id)
    if not season_folders:
        identity = get_credentials_identity() or "(unknown identity — try `gcloud auth list`)"
        raise click.ClickException(
            f"Drive folder {root_folder_id} has 0 visible sub-folders. The account in use "
            f"({identity}) probably doesn't have access to that shared drive. Open the drive "
            f"in your browser, choose 'Manage members', and add the account above as a Viewer."
        )
    season_key = season.strip().casefold()
    season_matches = [f for f in season_folders if season_key in (f.get('name') or '').casefold()]
    if not season_matches:
        names = ", ".join(f.get('name', '?') for f in season_folders)
        raise click.ClickException(
            f"No season folder matching {season!r} under root folder {root_folder_id}. "
            f"Visible season folders: {names}"
        )
    if len(season_matches) > 1:
        names = ", ".join(f.get('name', '?') for f in season_matches)
        raise click.ClickException(
            f"Multiple season folders match {season!r}: {names}. Be more specific via --season."
        )
    season_folder = season_matches[0]
    click.echo(f"Season folder: {season_folder.get('name')} ({season_folder['id']})")

    meet_folders = list_drive_subfolders(drive, season_folder['id'], drive_id=drive_id)
    meets_with_roster = []
    for meet in meet_folders:
        sheet = find_drive_sheet_in_folder(drive, meet['id'], roster_substring, drive_id=drive_id)
        if sheet:
            meets_with_roster.append((meet, sheet))

    if not meets_with_roster:
        raise click.ClickException(
            f"No meet folders under {season_folder.get('name')!r} contain a sheet matching "
            f"{roster_substring!r}."
        )

    meets_with_roster.sort(key=lambda ms: (ms[0].get('name') or '').casefold())

    def _entry(meet, sheet):
        return {'id': sheet['id'], 'name': sheet.get('name'), 'meet_name': meet.get('name')}

    # Non-interactive: process all discovered meets.
    if not interactive:
        click.echo(f"Found {len(meets_with_roster)} meet(s) in {season_folder.get('name')}; "
                   f"processing all (use --interactive to pick one).")
        return [_entry(m, s) for (m, s) in meets_with_roster]

    # Interactive: show a numbered list with 'a' (all) and 'q' (quit) options.
    click.echo(f"Meets found in {season_folder.get('name')}:")
    for i, (meet, sheet) in enumerate(meets_with_roster, 1):
        click.echo(f"  {i:>2}. {meet.get('name')}   ({sheet.get('name')})")
    click.echo("   a. Process all of them")
    click.echo("   q. Quit")
    choice = click.prompt(
        f"Pick a meet [1-{len(meets_with_roster)} / a / q]",
        default="1", show_default=True,
    ).strip().lower()
    if choice in ('q', 'quit'):
        raise click.ClickException("Aborted by user.")
    if choice in ('a', 'all'):
        return [_entry(m, s) for (m, s) in meets_with_roster]
    try:
        idx = int(choice) - 1
    except ValueError:
        raise click.ClickException(f"Not a number / a / q: {choice!r}")
    if not (0 <= idx < len(meets_with_roster)):
        raise click.ClickException(f"Out of range: {choice!r}")
    chosen_meet, chosen_sheet = meets_with_roster[idx]
    click.echo(f"Using meet {chosen_meet.get('name')!r} sheet {chosen_sheet.get('name')!r} ({chosen_sheet['id']})")
    return [_entry(chosen_meet, chosen_sheet)]
from .utils import (
    parse_season_to_id,
    validate_rems_id,
    deck_eval_credential_label,
    count_existing_deck_evals,
    find_existing_deck_eval_in_dates,
    find_existing_deck_eval_with_swapped_date,
    to_rems_date_format,
    parse_rems_date_to_iso,
    default_meet_dates_for,
)


class AlreadyRecordedError(click.ClickException):
    """Raised when an existing credential for this position covers one of the meet's session dates."""

    def __init__(self, message, credential=None):
        super().__init__(message)
        self.credential = credential


class NoMatchingCredentialError(click.ClickException):
    """Raised when no credential on the form matches the position. Carries the
    full options list so callers can offer the user a manual pick."""

    def __init__(self, message, options):
        super().__init__(message)
        self.options = options


def _unique_credential_families(options):
    """Return the unique credential families from form options: each option's
    label with any trailing ' Evaluation #N' suffix stripped, deduped, ordered."""
    seen = set()
    out = []
    for opt in options:
        label = (opt.get('label') or '').strip()
        family = re.sub(r'\s*Evaluation\s*#\d+\s*$', '', label).strip()
        if family and family not in seen:
            seen.add(family)
            out.append(family)
    return out


def _fetch_eval_state(client, member_season_id, member_id):
    """Fetch the data needed to resolve a deck eval credential for a member.
    Returns (existing_credentials, form_options). Cached at the call site so
    interactive re-resolution doesn't pay the round-trip cost twice."""
    existing = client.get_member_credentials(
        rems_id=None, member_id=member_id, member_season_id=member_season_id
    )
    options = client.get_add_credential_form_options(member_season_id, member_id)
    return existing, options


def _resolve_deck_eval_credential(client, member_season_id, member_id, position,
                                   meet_session_dates=None, existing=None, options=None):
    """
    Determine which credential to add next for the given position.
    Returns (credential_id, type_id, eval_number, label).

    Raises `AlreadyRecordedError` if an existing eval for this position
    falls on one of `meet_session_dates`. Raises `NoMatchingCredentialError`
    if no form option matches (carries the available options list for
    callers that want to offer a manual pick). Raises `click.ClickException`
    when the form's max # for the position already exists on other dates.

    `existing` and `options` may be passed in to avoid re-fetching on a
    follow-up call (e.g. after an interactive credential-family pick).
    """
    if existing is None or options is None:
        existing, options = _fetch_eval_state(client, member_season_id, member_id)

    existing_count = count_existing_deck_evals(existing, position)
    eval_number = existing_count + 1
    expected_label = deck_eval_credential_label(position, eval_number)
    normalized_prefix = deck_eval_credential_label(position, 1).rsplit(' #', 1)[0].lower()

    matching_options = [o for o in options if o['label'].strip().lower().startswith(normalized_prefix + ' #')]
    matching_existing = [
        c for c in existing
        if (c.get('type') or '').strip().lower() == 'deck evaluation'
        and (c.get('name') or '').strip().lower().startswith(normalized_prefix + ' ')
    ]

    duplicate = find_existing_deck_eval_in_dates(existing, position, meet_session_dates)
    if duplicate is not None:
        raise AlreadyRecordedError(
            f"already recorded (existing {duplicate.get('name')!r} on {duplicate.get('start_date')})",
            credential=duplicate,
        )

    for opt in options:
        if opt['label'].strip().lower() == expected_label.lower():
            return opt['credential_id'], opt['type_id'], eval_number, expected_label

    if matching_options and existing_count >= len(matching_options):
        existing_summary = ", ".join(f"{c.get('name', '')} ({c.get('start_date', '?')})"
                                     for c in matching_existing)
        raise click.ClickException(
            f"Max {len(matching_options)} {normalized_prefix.title()} evaluations already "
            f"exist for this official ({existing_summary}) but none match this meet's session "
            f"dates. Resolve in REMS before re-running."
        )

    raise NoMatchingCredentialError(
        f"No credential option matching {expected_label!r} on add-credential form.",
        options=options,
    )


def _credential_view_url(member_season_id, member_id, credential_id):
    """Full REMS URL for viewing/editing a member credential — handy to print
    so the user can verify what the tool's report refers to."""
    return (f"{REMSClient.BASE_URL}/sportlomo/user/credentials/"
            f"view-from-member-profile/{member_season_id}/{member_id}/{credential_id}")


def _handle_swapped_eval(client, gsheet_client, sheet_id, positions_tab, row_idx,
                          name, position, swap_cred,
                          member_season_id, member_id, meet_dates,
                          interactive, dry_run):
    """Report a SWAPPED row, and if --interactive, offer to fix it via REMS edit.
    Returns True if handled successfully (logged or fixed), False if the fix
    was attempted and failed."""
    existing_date = swap_cred.get('start_date', '?')
    # The corrected date is the meet date whose day/month swap matches the existing one.
    existing_iso = parse_rems_date_to_iso(existing_date)
    correct_iso = next(
        (d for d in meet_dates if _swap_day_month_for_match(d) == existing_iso),
        None,
    )
    correct_rems_date = to_rems_date_format(correct_iso) if correct_iso else None
    credential_id = _credential_id_from_swap(swap_cred)
    url = _credential_view_url(member_season_id, member_id, credential_id) if credential_id else None

    click.echo(
        f"  SWAPPED row {row_idx} ({name} / {position}): existing "
        f"{swap_cred.get('name')!r} has start_date {existing_date} "
        f"(day/month swapped — legacy m/d/Y bug)"
    )
    if url:
        click.echo(f"    {url}")

    if not interactive or not correct_rems_date:
        return True  # logged, no further action

    if not credential_id:
        click.echo("    (could not parse credential id from listing; fix manually in REMS)")
        return True

    click.echo(f"    Fix start_date to {correct_rems_date}? [y/N]")
    choice = click.prompt("    Choose", default="n", show_default=True).strip().lower()
    if choice not in ('y', 'yes'):
        click.echo("    Leaving as-is.")
        return True

    if dry_run:
        click.echo(f"    [dry-run] would POST update_member_credential start_date={correct_rems_date}")
        return True

    try:
        client.update_member_credential(
            member_season_id, member_id, credential_id,
            field_overrides={"start_date": correct_rems_date},
        )
        click.echo(f"    OK: start_date updated to {correct_rems_date}")
        return True
    except Exception as e:
        click.echo(f"    FAIL: update_member_credential raised: {e}", err=True)
        return False


def _swap_day_month_for_match(iso_date):
    """Mirror utils._swap_day_month_iso for matching purposes. Returns the
    swapped ISO date or None if either component is > 12 (unambiguous)."""
    from datetime import date
    try:
        y, m, d = iso_date.split('-')
        y, m, d = int(y), int(m), int(d)
        if m > 12 or d > 12:
            return None
        return date(y, d, m).isoformat()
    except (ValueError, AttributeError):
        return None


def _credential_id_from_swap(cred):
    """Extract the credential id from the 'actions' URLs returned alongside the
    credentials listing — view/edit URLs follow .../{msid}/{mid}/{cid}."""
    actions = cred.get('actions') or ''
    m = re.search(r'view-from-member-profile/\d+/\d+/(\d+)', actions)
    return m.group(1) if m else None


def _prompt_for_credential_family(options, sheet_position, row_idx, name, rems_id):
    """Show a numbered list of unique credential families and return the
    chosen family name, or None to skip the row. The row's identifying info
    is printed first so the prompt isn't ambiguous after a batch of OK lines."""
    families = _unique_credential_families(options)
    click.echo("")
    click.echo(f"  Row {row_idx}: {name} ({rems_id}) / sheet position {sheet_position!r}")
    click.echo(f"    Sheet position {sheet_position!r} doesn't match a known credential.")
    click.echo("    What credential was this evaluation for?")
    for i, fam in enumerate(families, 1):
        click.echo(f"      {i:>2}. {fam}")
    click.echo("       s. Skip this row")
    choice = click.prompt("    Choose", default="s", show_default=True).strip().lower()
    if choice in ('s', 'skip', ''):
        return None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(families):
            return families[idx]
    except ValueError:
        pass
    click.echo(f"    Invalid choice {choice!r}; skipping.")
    return None


@click.group()
def cli():
    """A CLI tool to synchronize data from the Swimming Canada REMS system."""
    pass

@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.', required=True)
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True, required=True)
def login(username, password):
    """Logs in to the REMS system."""
    client = REMSClient(username, password, get_mfa_code)
    client.login()

@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.', required=True)
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True, required=True)
@click.option('--output', type=click.Choice(['csv', 'gsheet']), default='csv', help='The output format.')
@click.option('--output-file', help='The file to write CSV output to (required if output is csv).')
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Members', help='The name of the sheet to write to.')
@click.option('--season', required=True, help='The season (e.g., "2025" or "2025-2026") to refresh.')
def refresh_members(username, password, output, output_file, sheet_id, sheet_name, season):
    """Refreshes the REMS members list."""
    season_id = parse_season_to_id(season)
    click.echo(f"Refreshing REMS members (output: {output}, season: {season}, season_id: {season_id})")
    client = REMSClient(username, password, get_mfa_code)
    client.login()
    csv_data = client.get_members_csv(season_id)
    
    if output == 'csv':
        if not output_file:
            click.echo("Output file is required for CSV output.", err=True)
            return
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            f.write(csv_data)
        click.echo(f"Successfully wrote data to {output_file}")
    elif output == 'gsheet':
        if not sheet_id:
            click.echo("Sheet ID is required for Google Sheet output.", err=True)
            return
        df = pd.read_csv(StringIO(csv_data))
        gsheet_client = get_gspread_client()
        write_df_to_sheet(df, sheet_id, sheet_name, gsheet_client)

@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.', required=True)
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True, required=True)
@click.option('--output', type=click.Choice(['csv', 'gsheet']), default='csv', help='The output format.')
@click.option('--output-file', help='The file to write CSV output to (required if output is csv).')
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Details', help='The name of the sheet to write to.')
@click.option('--season', required=True, help='The season (e.g., "2025" or "2025-2026") to refresh.')
@click.argument('input_file', type=click.Path(exists=True))
def refresh_member_details(username, password, output, output_file, sheet_id, sheet_name, season, input_file):
    """Refreshes the REMS member details using REMS IDs from an input CSV."""
    season_id = parse_season_to_id(season)
    click.echo(f"Refreshing REMS member details (input: {input_file}, output: {output}, season: {season}, season_id: {season_id})")
    
    try:
        df_input = pd.read_csv(input_file)
    except Exception as e:
        click.echo(f"Error reading input file: {e}", err=True)
        return

    # Look for REMS ID column (case-insensitive, ignore non-alphanumeric)
    rems_id_col = None
    for col in df_input.columns:
        normalized = "".join(c for c in col.upper() if c.isalnum())
        if normalized == "REMSID":
            rems_id_col = col
            break
    
    if not rems_id_col:
        click.echo(f"Could not find REMS ID column in {input_file}. Found columns: {list(df_input.columns)}", err=True)
        return

    rems_ids_all = df_input[rems_id_col].dropna().unique()
    rems_ids = [rid for rid in rems_ids_all if validate_rems_id(rid)]
    
    click.echo(f"Found {len(rems_ids)} valid unique REMS IDs in {rems_id_col} column.")
    if len(rems_ids) < len(rems_ids_all):
        click.echo(f"Skipped {len(rems_ids_all) - len(rems_ids)} invalid REMS IDs.")

    client = REMSClient(username, password, get_mfa_code)
    client.login()
    
    all_details = []
    for rems_id in rems_ids:
        click.echo(f"Fetching details for {rems_id}...")
        member_season_id = client.get_member_season_id(rems_id, season_id)
        if member_season_id:
            details = client.get_member_details(member_season_id, season_id)
            all_details.append(details)
        else:
            click.echo(f"Could not find member season ID for {rems_id}", err=True)

    if all_details:
        df = pd.DataFrame(all_details)
        if output == 'csv':
            if not output_file:
                click.echo("Output file is required for CSV output.", err=True)
                return
            df.to_csv(output_file, index=False)
            click.echo(f"Successfully wrote data to {output_file}")
        elif output == 'gsheet':
            if not sheet_id:
                click.echo("Sheet ID is required for Google Sheet output.", err=True)
                return
            gsheet_client = get_gspread_client()
            write_df_to_sheet(df, sheet_id, sheet_name, gsheet_client)

@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.', required=True)
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True, required=True)
@click.option('--output', type=click.Choice(['csv', 'gsheet']), default='csv', help='The output format.')
@click.option('--output-file', help='The file to write CSV output to (required if output is csv).')
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Credentials', help='The name of the sheet to write to.')
@click.argument('member_details_file', type=click.File('r') )
def refresh_member_credentials(username, password, output, output_file, sheet_id, sheet_name, member_details_file):
    """Refreshes the REMS member credentials."""
    click.echo(f"Refreshing REMS member credentials (output: {output})")
    client = REMSClient(username, password, get_mfa_code)
    client.login()
    
    try:
        member_details_df = pd.read_csv(member_details_file)
    except Exception as e:
        click.echo(f"Error reading member details file: {e}", err=True)
        return
    
    all_credentials = []
    for _, row in member_details_df.iterrows():
        click.echo(f"Fetching credentials for {row['rems_id']}...")
        credentials = client.get_member_credentials(
            row['rems_id'],
            row['member_id'],
            row['member_season_id']
        )
        all_credentials.extend(credentials)

    if all_credentials:
        df = pd.DataFrame(all_credentials)
        if output == 'csv':
            if not output_file:
                click.echo("Output file is required for CSV output.", err=True)
                return
            df.to_csv(output_file, index=False)
            click.echo(f"Successfully wrote data to {output_file}")
        elif output == 'gsheet':
            if not sheet_id:
                click.echo("Sheet ID is required for Google Sheet output.", err=True)
                return
            gsheet_client = get_gspread_client()
            write_df_to_sheet(df, sheet_id, sheet_name, gsheet_client)

@cli.command()
@click.option('--input-file', type=click.Path(exists=True), required=True, help='The CSV file to upload.')
@click.option('--sheet-id', required=True, help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Members', help='The name of the sheet to write to.')
def upload_members(input_file, sheet_id, sheet_name):
    """Uploads members from a CSV file to a Google Sheet."""
    click.echo(f"Uploading members from {input_file} to sheet {sheet_id}...")
    try:
        df = pd.read_csv(input_file)
        gsheet_client = get_gspread_client()
        write_df_to_sheet(df, sheet_id, sheet_name, gsheet_client)
    except Exception as e:
        click.echo(f"Error uploading members: {e}", err=True)

@cli.command()
@click.option('--input-file', type=click.Path(exists=True), required=True, help='The CSV file to upload.')
@click.option('--sheet-id', required=True, help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Details', help='The name of the sheet to write to.')
def upload_member_details(input_file, sheet_id, sheet_name):
    """Uploads member details from a CSV file to a Google Sheet."""
    click.echo(f"Uploading member details from {input_file} to sheet {sheet_id}...")
    try:
        df = pd.read_csv(input_file)
        gsheet_client = get_gspread_client()
        write_df_to_sheet(df, sheet_id, sheet_name, gsheet_client)
    except Exception as e:
        click.echo(f"Error uploading member details: {e}", err=True)

@cli.command()
@click.option('--input-file', type=click.Path(exists=True), required=True, help='The CSV file to upload.')
@click.option('--sheet-id', required=True, help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Credentials', help='The name of the sheet to write to.')
def upload_member_credentials(input_file, sheet_id, sheet_name):
    """Uploads member credentials from a CSV file to a Google Sheet."""
    click.echo(f"Uploading member credentials from {input_file} to sheet {sheet_id}...")
    try:
        df = pd.read_csv(input_file)
        gsheet_client = get_gspread_client()
        write_df_to_sheet(df, sheet_id, sheet_name, gsheet_client)
    except Exception as e:
        click.echo(f"Error uploading member credentials: {e}", err=True)


@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.', required=True)
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True, required=True)
@click.option('--season', required=True, help='The season (e.g. "2025-2026").')
@click.option('--sheet-id', default=None,
              help='The Google Sheet ID with Positions, Grid, and Meet tabs. '
                   'When omitted, the tool searches the configured season folder in Drive '
                   'and prompts you to pick a meet.')
@click.option('--season-folder-id', default=ROW_OFFICIALS_ROOT_FOLDER_ID,
              help='Root Drive folder ID under which season subfolders live. '
                   'Used only when --sheet-id is not provided.')
@click.option('--roster-name-substring', default=DEFAULT_ROSTER_SHEET_NAME_SUBSTRING,
              help='Substring used to identify the roster sheet inside a meet folder. '
                   'Used only when --sheet-id is not provided.')
@click.option('--positions-tab', default='Positions', help='Name of the positions tab.')
@click.option('--grid-tab', default='Grid', help='Name of the grid tab (session -> date).')
@click.option('--meet-tab', default='Meet', help='Name of the meet tab (key/value meet metadata).')
@click.option('--officials-tab', default='Officials', help='Name of the officials tab (Name -> REMS ID lookup).')
@click.option('--session-col', default='Session', help='Column in the positions tab that identifies a session.')
@click.option('--rems-club', default='ROW', help='Only process rows whose Official Club matches this. Default: ROW.')
@click.option('--meet-name', default=None, help='Override meet name; if omitted, read from the Meet tab.')
@click.option('--dry-run', is_flag=True, help='Print what would be posted without contacting REMS or writing back to the sheet.')
@click.option('--interactive', is_flag=True, help='Prompt y/n/q before POSTing each evaluation.')
@click.option('--recheck', is_flag=True, help='Verify-only pass: include rows already marked Deck Eval Recorded? = TRUE, '
                                              'confirm against REMS, but never POST. Missing rows are reported.')
def upload_deck_evals(username, password, season, sheet_id, season_folder_id, roster_name_substring,
                     positions_tab, grid_tab, meet_tab,
                     officials_tab, session_col, rems_club, meet_name, dry_run, interactive, recheck):
    """Upload deck evaluations from a positions sheet to REMS and mark each row recorded."""
    season_id = parse_season_to_id(season)
    gsheet_client = get_gspread_client()

    if sheet_id:
        sheets_to_process = [{'id': sheet_id, 'name': None, 'meet_name': None}]
    else:
        sheets_to_process = _discover_meet_sheets(
            season, season_folder_id, roster_name_substring, interactive=interactive,
        )

    # One login covers every sheet — the cookie cache makes subsequent login()
    # calls cheap, but we don't even need them.
    client = REMSClient(username, password, get_mfa_code)
    client.login()

    overall_successes = 0
    overall_failures = 0
    for sheet_entry in sheets_to_process:
        sheet_id = sheet_entry['id']
        if sheet_entry.get('meet_name'):
            click.echo(f"\n=== {sheet_entry['meet_name']} ({sheet_entry.get('name')}) ===")

        successes, failures = _process_meet_sheet(
            client, gsheet_client, sheet_id,
            season=season, season_id=season_id,
            positions_tab=positions_tab, grid_tab=grid_tab, meet_tab=meet_tab,
            officials_tab=officials_tab, session_col=session_col,
            rems_club=rems_club, meet_name_override=meet_name,
            dry_run=dry_run, interactive=interactive, recheck=recheck,
        )
        overall_successes += successes
        overall_failures += failures

    if len(sheets_to_process) > 1:
        click.echo(f"\nAll meets done: {overall_successes} succeeded, {overall_failures} failed.")


def _process_meet_sheet(client, gsheet_client, sheet_id, *,
                         season, season_id,
                         positions_tab, grid_tab, meet_tab, officials_tab,
                         session_col, rems_club, meet_name_override,
                         dry_run, interactive, recheck):
    """Process a single meet's roster sheet. Returns (successes, failures)."""
    positions_df = read_sheet_tab(sheet_id, positions_tab, gsheet_client)
    meet_meta = parse_meet_tab(read_sheet_rows(sheet_id, meet_tab, gsheet_client))
    meet_name = meet_name_override
    if meet_name is None:
        meet_name = meet_meta.get('Meet Name') or meet_meta.get('Name')
        if not meet_name:
            raise click.ClickException(
                f"Could not find 'Meet Name' in tab {meet_tab!r}. Use --meet-name to override."
            )
    click.echo(f"Meet: {meet_name}")

    meet_start_date = meet_meta.get('Meet Start Date', '')
    year_match = re.match(r'(\d{4})', meet_start_date)
    if year_match:
        year = int(year_match.group(1))
    else:
        season_year_match = re.search(r'(\d{4})\s*$', season)
        year = int(season_year_match.group(1)) if season_year_match else int(season[:4])

    session_dates = parse_grid_session_dates(
        read_sheet_rows(sheet_id, grid_tab, gsheet_client), year=year
    )
    if not session_dates:
        raise click.ClickException(f"Could not parse any session dates from Grid tab {grid_tab!r}.")
    click.echo(f"Session dates: {session_dates}")

    name_to_rems_id = parse_officials_name_to_rems_id(
        read_sheet_rows(sheet_id, officials_tab, gsheet_client)
    )
    click.echo(f"Loaded {len(name_to_rems_id)} officials from {officials_tab!r}.")

    # 'Position Name' is a common alternative spelling for 'Official Position' in
    # older meet rosters; accept either.
    position_col = None
    for candidate in ('Official Position', 'Position Name'):
        if candidate in positions_df.columns:
            position_col = candidate
            break
    if position_col is None:
        raise click.ClickException(
            "Positions tab is missing a position column "
            "(expected 'Official Position' or 'Position Name')"
        )

    # 'Deck Eval Reported?' is an older spelling of 'Deck Eval Recorded?'; accept either.
    recorded_col = None
    for candidate in ('Deck Eval Recorded?', 'Deck Eval Reported?'):
        if candidate in positions_df.columns:
            recorded_col = candidate
            break

    required = ['Official Name', 'Official Club', 'Deck Eval Success?', session_col]
    if not recheck:
        # Recheck doesn't POST or write back, so these aren't needed.
        required += ['Deck Eval Provider']
        if recorded_col is None:
            raise click.ClickException(
                "Positions tab is missing a recorded column "
                "(expected 'Deck Eval Recorded?' or 'Deck Eval Reported?')"
            )
    missing = [c for c in required if c not in positions_df.columns]
    if missing:
        raise click.ClickException(f"Positions tab is missing required columns: {missing}")

    def _is_true(v):
        return str(v).strip().upper() in ('TRUE', 'YES', '1')
    def _is_blank(v):
        return str(v).strip() == '' or str(v).strip().upper() == 'FALSE'

    success_mask = positions_df['Deck Eval Success?'].apply(_is_true)
    club_mask = positions_df['Official Club'].astype(str).str.strip().str.casefold() == rems_club.strip().casefold()
    if recheck:
        pending_mask = success_mask & club_mask
        click.echo("Recheck mode: verifying every Deck Eval Success?=TRUE row against REMS (no POSTs).")
    else:
        pending_mask = success_mask & club_mask & positions_df[recorded_col].apply(_is_blank)
    pending = positions_df[pending_mask]
    excluded_other_club = int((success_mask & ~club_mask).sum())
    noun = "row(s) to verify" if recheck else "pending deck eval(s) to upload"
    click.echo(f"Found {len(pending)} {noun} for club {rems_club!r}"
               + (f" ({excluded_other_club} other-club row(s) skipped)" if excluded_other_club else "")
               + ".")
    if pending.empty:
        return 0, 0

    successes = 0
    failures = 0
    for idx, row in pending.iterrows():
        name = str(row['Official Name']).strip()
        position = str(row[position_col]).strip()
        provider = str(row['Deck Eval Provider']).strip() if 'Deck Eval Provider' in row else ''
        session = str(row[session_col]).strip()
        date_raw = session_dates.get(session)
        if not date_raw:
            click.echo(f"  SKIP row {idx} ({name}, {position}): no date for session {session!r}", err=True)
            failures += 1
            continue

        try:
            start_date = to_rems_date_format(date_raw)
            description = f"Session {session}" if not session.lower().startswith('session') else session

            rems_id = name_to_rems_id.get(name)
            if not rems_id:
                raise click.ClickException(f"no REMS ID for {name!r} in Officials tab")

            member_season_id = client.get_member_season_id(rems_id, season_id)
            if not member_season_id:
                raise click.ClickException(f"REMS ID {rems_id} not found in season {season}")
            details = client.get_member_details(member_season_id, season_id)
            member_id = details['member_id']
            if not member_id:
                raise click.ClickException(f"could not resolve member_id for {name!r} (REMS {rems_id})")

            cached_existing, cached_options = _fetch_eval_state(client, member_season_id, member_id)

            # Recheck: spot the legacy m/d/Y date-swap bug before the resolve
            # may raise (e.g. at-max). A swap takes up a position slot in REMS,
            # so we want to flag it independently of whatever resolve would say.
            if recheck:
                meet_dates_set = set(session_dates.values())
                swap_cred = find_existing_deck_eval_with_swapped_date(
                    cached_existing, position, meet_dates_set,
                )
                if swap_cred is not None:
                    swap_handled = _handle_swapped_eval(
                        client, gsheet_client, sheet_id, positions_tab, idx,
                        name, position, swap_cred,
                        member_season_id=member_season_id, member_id=member_id,
                        meet_dates=meet_dates_set,
                        interactive=interactive, dry_run=dry_run,
                    )
                    if swap_handled:
                        successes += 1
                    else:
                        failures += 1
                    continue

            try:
                credential_id, type_id, eval_number, label = _resolve_deck_eval_credential(
                    client, member_season_id, member_id, position,
                    meet_session_dates=set(session_dates.values()),
                    existing=cached_existing, options=cached_options,
                )
            except AlreadyRecordedError as e:
                click.echo(f"  OK row {idx} ({name} / {position}): {e.message}")
                cred_id = _credential_id_from_swap(e.credential or {})
                if cred_id:
                    click.echo(f"    {_credential_view_url(member_season_id, member_id, cred_id)}")
                # Tick the cell to TRUE only when we're in the normal flow.
                # Recheck is verify-only; the cell is already TRUE in that path.
                if not dry_run and not recheck and recorded_col:
                    update_cell(sheet_id, positions_tab, idx, recorded_col, True, gsheet_client)
                successes += 1
                continue
            except NoMatchingCredentialError as e:
                if not interactive:
                    raise
                chosen = _prompt_for_credential_family(
                    e.options, sheet_position=position,
                    row_idx=idx, name=name, rems_id=rems_id,
                )
                if chosen is None:
                    click.echo(f"  SKIP row {idx} ({name} / {position}): no credential picked")
                    failures += 1
                    continue
                try:
                    credential_id, type_id, eval_number, label = _resolve_deck_eval_credential(
                        client, member_season_id, member_id, chosen,
                        meet_session_dates=set(session_dates.values()),
                        existing=cached_existing, options=cached_options,
                    )
                except AlreadyRecordedError as e:
                    click.echo(f"  OK row {idx} ({name} / {chosen}): {e.message}")
                    cred_id = _credential_id_from_swap(e.credential or {})
                    if cred_id:
                        click.echo(f"    {_credential_view_url(member_season_id, member_id, cred_id)}")
                    if not dry_run and not recheck and recorded_col:
                        update_cell(sheet_id, positions_tab, idx, recorded_col, True, gsheet_client)
                    successes += 1
                    continue

            # Track whether the user has already approved adding this row;
            # used to suppress the regular interactive Submit? prompt below
            # when we already prompted via the recheck-missing path.
            recheck_missing_approved = False
            if recheck:
                if interactive:
                    click.echo(
                        f"\n  MISSING row {idx}: {name} ({rems_id}) / {position}\n"
                        f"    REMS has no matching {label} for meet={meet_name!r} "
                        f"session={description!r}\n"
                        f"    Add it now?"
                    )
                    choice = click.prompt(
                        "    [y]es / [n]o (skip) / [q]uit batch",
                        default="n", show_default=True,
                    ).strip().lower()
                    if choice in ('q', 'quit'):
                        click.echo("  Aborting batch.")
                        break
                    if choice not in ('y', 'yes'):
                        click.echo(f"  MISSING row {idx} (skipped)")
                        failures += 1
                        continue
                    recheck_missing_approved = True
                    # Fall through to the POST logic.
                else:
                    # Verify-only with no prompt: report and continue.
                    click.echo(f"  MISSING row {idx} ({name} / {position}): "
                               f"REMS has no matching {label} for meet={meet_name!r} "
                               f"session={description!r}")
                    failures += 1
                    continue

            if dry_run:
                click.echo(f"  [dry-run] row {idx}: {name} ({rems_id}) / {label} "
                           f"(credential_id={credential_id}) session {session} ({start_date}) "
                           f"provider={provider!r}")
                successes += 1
                continue

            if interactive and not recheck_missing_approved:
                click.echo(
                    f"\n  Row {idx}: {name} ({rems_id})\n"
                    f"    Credential: {label} (credential_id={credential_id})\n"
                    f"    Session:    {session} ({start_date})\n"
                    f"    Provider:   {provider}\n"
                    f"    Meet:       {meet_name}"
                )
                choice = click.prompt(
                    "  Submit? [y]es / [n]o (skip) / [q]uit batch",
                    default="n", show_default=True,
                ).strip().lower()
                if choice in ('q', 'quit'):
                    click.echo("  Aborting batch.")
                    break
                if choice not in ('y', 'yes'):
                    click.echo(f"  SKIP row {idx} (user declined)")
                    failures += 1
                    continue

            client.add_member_credential(
                member_season_id=member_season_id,
                member_id=member_id,
                credential_id=credential_id,
                type_id=type_id,
                provider=provider,
                provider_identifier=meet_name,
                start_date=start_date,
                description=description,
            )
            if recorded_col:
                update_cell(sheet_id, positions_tab, idx, recorded_col, True, gsheet_client)
            click.echo(f"  OK row {idx}: {name} / {label} (session {session})")
            successes += 1
        except Exception as e:
            click.echo(f"  FAIL row {idx} ({name} / {position}): {e}", err=True)
            failures += 1

    click.echo(f"Done: {successes} succeeded, {failures} failed.")
    return successes, failures


@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.', required=True)
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True, required=True)
@click.option('--season', required=True, help='The season (e.g. "2025-2026").')
@click.option('--official-name', required=True, help='Official\'s full name, e.g. "Chris Fletcher".')
@click.option('--rems-id', default=None, help='REMS ID (e.g. SC24176410); if given, used instead of name search.')
@click.option('--position', required=True, help='Official position, e.g. "Inspector of Turns".')
@click.option('--provider', required=True, help='Full name of the evaluator (Deck Eval Provider).')
@click.option('--meet', required=True, help='Meet name; submitted as provider_identifier.')
@click.option('--date', 'eval_date', required=True, help='Session date in YYYY-MM-DD or MM/DD/YYYY.')
@click.option('--description', required=True, help='Free-form description, e.g. "Session 6".')
@click.option('--meet-dates', default=None,
              help='Comma-separated list of all the meet\'s session dates (YYYY-MM-DD or MM/DD/YYYY). '
                   'When provided, the duplicate check rejects an add if any existing eval for the position '
                   'falls on ANY of these dates, enforcing "no two evals for the same position at the same meet". '
                   'When omitted, defaults to the Wed..Sun bracket around --date.')
@click.option('--dry-run', is_flag=True, help='Print what would be posted without contacting REMS.')
def add_deck_eval(username, password, season, official_name, rems_id, position, provider, meet, eval_date, description, meet_dates, dry_run):
    """Add a single deck evaluation for one named official."""
    season_id = parse_season_to_id(season)
    start_date = to_rems_date_format(eval_date)

    client = REMSClient(username, password, get_mfa_code)
    client.login()

    click.echo(f"Looking up {official_name!r} in season {season}...")
    if rems_id:
        member_season_id = client.get_member_season_id(rems_id, season_id)
        if not member_season_id:
            raise click.ClickException(f"REMS ID {rems_id} not found in season {season}.")
    else:
        member_season_id = client.search_member_by_name(official_name, season_id)
        if not member_season_id:
            raise click.ClickException(f"Could not find official named {official_name!r} in season {season}.")
    details = client.get_member_details(member_season_id, season_id)
    member_id = details['member_id']
    if not member_id:
        raise click.ClickException(f"Could not resolve member_id for {official_name!r}.")

    iso_date = parse_rems_date_to_iso(eval_date)
    if meet_dates:
        date_set = {parse_rems_date_to_iso(d.strip()) for d in meet_dates.split(',') if d.strip()}
        date_set.discard(None)
        if iso_date:
            date_set.add(iso_date)
    elif iso_date:
        # Default: bracket the eval date with the Wed-Sun the meet most likely covers.
        date_set = default_meet_dates_for(iso_date)
    else:
        date_set = set()
    try:
        credential_id, type_id, eval_number, label = _resolve_deck_eval_credential(
            client, member_season_id, member_id, position,
            meet_session_dates=date_set,
        )
    except AlreadyRecordedError as e:
        click.echo(f"Deck evaluation for {official_name} / {position} {e.message}.")
        cred_id = _credential_id_from_swap(e.credential or {})
        if cred_id:
            click.echo(_credential_view_url(member_season_id, member_id, cred_id))
        return

    if dry_run:
        click.echo(f"[dry-run] Resolved {label!r} (credential_id={credential_id}, type={type_id}) "
                   f"for {official_name} ({details.get('rems_id')}). Skipping POST.")
        return

    click.echo(f"Adding {label!r} (credential_id={credential_id}, type={type_id}) "
               f"for {official_name} ({details.get('rems_id')})...")
    client.add_member_credential(
        member_season_id=member_season_id,
        member_id=member_id,
        credential_id=credential_id,
        type_id=type_id,
        provider=provider,
        provider_identifier=meet,
        start_date=start_date,
        description=description,
    )
    click.echo(f"Success: recorded deck eval #{eval_number} for {official_name}.")


if __name__ == '__main__':
    cli()
