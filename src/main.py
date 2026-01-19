import click
import pandas as pd
from io import StringIO
from typing import Optional
from .rems_client import REMSClient, get_mfa_code
from .gsheet import get_gspread_client, write_df_to_sheet
from .utils import parse_season_to_id, validate_rems_id
from .auth_manager import store_auth, load_auth, is_session_expired
from .gmail_mfa import get_mfa_code_gmail


@click.group()
def cli() -> None:
    """A CLI tool to synchronize data from the Swimming Canada REMS system."""
    pass


def get_authenticated_client(username: Optional[str], password: Optional[str],
                             skip_cache: bool, use_gmail_mfa: bool,
                             project_id: Optional[str]) -> REMSClient:
    """
    Returns authenticated REMSClient, using cache if available and not skipped.
    Handles fallback logic for auth and MFA.
    """
    if skip_cache or not project_id:
        # Use traditional authentication
        if not username or not password:
            raise click.UsageError("Username and password required when skipping cache")
        mfa_callback = get_mfa_code_gmail if use_gmail_mfa else get_mfa_code
        client = REMSClient(username, password, mfa_callback, use_cached_auth=False)
        client.login()
        return client

    # Try to load from cache
    auth_data = load_auth(project_id)

    if auth_data and not is_session_expired(auth_data):
        # Try to use cached session
        cached_username = auth_data.get('username')
        cached_password = auth_data.get('password')
        mfa_callback = get_mfa_code_gmail if use_gmail_mfa else get_mfa_code
        client = REMSClient(
            username or cached_username,
            password or cached_password,
            mfa_callback,
            project_id=project_id
        )
        if client.restore_from_cache(auth_data) and client.is_session_valid():
            click.echo("Using cached authentication")
            return client
        click.echo("Cached session expired, re-authenticating...")

    # Cache miss or expired - perform fresh login
    if not username or not password:
        if auth_data:
            username = auth_data.get('username')
            password = auth_data.get('password')
        else:
            raise click.UsageError(
                "Username and password required. Please run 'setup-auth' first or provide credentials."
            )

    mfa_callback = get_mfa_code_gmail if use_gmail_mfa else get_mfa_code
    client = REMSClient(username, password, mfa_callback, project_id=project_id)
    client.login()

    # Store in cache for next time
    store_auth(username, password, client.session, project_id)
    click.echo("Authentication cached successfully")

    return client


@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.', required=True)
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True, required=True)
@click.option('--project-id', envvar='GCP_PROJECT_ID', help='The GCP project ID for Secret Manager.')
@click.option('--use-gmail-mfa/--no-gmail-mfa', default=False, help='Use Gmail API for MFA code extraction.')
def setup_auth(username: str, password: str, project_id: Optional[str], use_gmail_mfa: bool) -> None:
    """Sets up and caches REMS authentication in GCP Secret Manager."""
    if not project_id:
        click.echo("Warning: No project ID provided. Authentication will not be cached.", err=True)
        click.echo("Performing login without caching...")

    mfa_callback = get_mfa_code_gmail if use_gmail_mfa else get_mfa_code
    client = REMSClient(username, password, mfa_callback, project_id=project_id)
    client.login()

    if project_id:
        store_auth(username, password, client.session, project_id)
        click.echo("Authentication cached successfully in Secret Manager")

    click.echo("Setup complete!")

@cli.command()
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.')
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True)
@click.option('--skip-cache', is_flag=True, help='Skip cached authentication and prompt for MFA.')
@click.option('--use-gmail-mfa', is_flag=True, help='Use Gmail API for MFA code extraction.')
@click.option('--project-id', envvar='GCP_PROJECT_ID', help='The GCP project ID for Secret Manager.')
@click.option('--output', type=click.Choice(['csv', 'gsheet']), default='csv', help='The output format.')
@click.option('--output-file', help='The file to write CSV output to (required if output is csv).')
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Members', help='The name of the sheet to write to.')
@click.option('--season', required=True, help='The season (e.g., "2025" or "2025-2026") to refresh.')
def refresh_members(username: Optional[str], password: Optional[str], skip_cache: bool,
                   use_gmail_mfa: bool, project_id: Optional[str], output: str,
                   output_file: Optional[str], sheet_id: Optional[str],
                   sheet_name: str, season: str) -> None:
    """Refreshes the REMS members list."""
    season_id = parse_season_to_id(season)
    click.echo(f"Refreshing REMS members (output: {output}, season: {season}, season_id: {season_id})")
    client = get_authenticated_client(username, password, skip_cache, use_gmail_mfa, project_id)
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
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.')
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True)
@click.option('--skip-cache', is_flag=True, help='Skip cached authentication and prompt for MFA.')
@click.option('--use-gmail-mfa', is_flag=True, help='Use Gmail API for MFA code extraction.')
@click.option('--project-id', envvar='GCP_PROJECT_ID', help='The GCP project ID for Secret Manager.')
@click.option('--output', type=click.Choice(['csv', 'gsheet']), default='csv', help='The output format.')
@click.option('--output-file', help='The file to write CSV output to (required if output is csv).')
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Details', help='The name of the sheet to write to.')
@click.option('--season', required=True, help='The season (e.g., "2025" or "2025-2026") to refresh.')
@click.argument('input_file', type=click.Path(exists=True))
def refresh_member_details(username, password, skip_cache, use_gmail_mfa, project_id, output, output_file, sheet_id, sheet_name, season, input_file):
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

    client = get_authenticated_client(username, password, skip_cache, use_gmail_mfa, project_id)
    
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
@click.option('--username', envvar='REMS_USERNAME', help='The REMS username.')
@click.option('--password', envvar='REMS_PASSWORD', help='The REMS password.', hide_input=True)
@click.option('--skip-cache', is_flag=True, help='Skip cached authentication and prompt for MFA.')
@click.option('--use-gmail-mfa', is_flag=True, help='Use Gmail API for MFA code extraction.')
@click.option('--project-id', envvar='GCP_PROJECT_ID', help='The GCP project ID for Secret Manager.')
@click.option('--output', type=click.Choice(['csv', 'gsheet']), default='csv', help='The output format.')
@click.option('--output-file', help='The file to write CSV output to (required if output is csv).')
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Credentials', help='The name of the sheet to write to.')
@click.argument('member_details_file', type=click.File('r') )
def refresh_member_credentials(username, password, skip_cache, use_gmail_mfa, project_id, output, output_file, sheet_id, sheet_name, member_details_file):
    """Refreshes the REMS member credentials."""
    click.echo(f"Refreshing REMS member credentials (output: {output})")
    client = get_authenticated_client(username, password, skip_cache, use_gmail_mfa, project_id)
    
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


if __name__ == '__main__':
    cli()
