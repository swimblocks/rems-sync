import click
import pandas as pd
from io import StringIO
from .rems_client import REMSClient, get_mfa_code
from .gsheet import get_gspread_client, write_df_to_sheet
from .utils import parse_season_to_id


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
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Members', help='The name of the sheet to write to.')
@click.option('--season', required=True, help='The season (e.g., "2025" or "2025-2026") to refresh.')
def refresh_members(username, password, output, sheet_id, sheet_name, season):
    """Refreshes the REMS members list."""
    season_id = parse_season_to_id(season)
    click.echo(f"Refreshing REMS members (output: {output}, season: {season}, season_id: {season_id})")
    client = REMSClient(username, password, get_mfa_code)
    client.login()
    csv_data = client.get_members_csv(season_id)
    
    if output == 'csv':
        click.echo(csv_data)
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
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Details', help='The name of the sheet to write to.')
@click.option('--season', required=True, help='The season (e.g., "2025" or "2025-2026") to refresh.')
@click.argument('rems_ids', nargs=-1)
def refresh_member_details(username, password, output, sheet_id, sheet_name, season, rems_ids):
    """Refreshes the REMS member details."""
    season_id = parse_season_to_id(season)
    click.echo(f"Refreshing REMS member details (output: {output}, season: {season}, season_id: {season_id})")
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
            click.echo(df.to_csv(index=False))
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
@click.option('--sheet-id', help='The Google Sheet ID to write to.')
@click.option('--sheet-name', default='REMS Member Credentials', help='The name of the sheet to write to.')
@click.argument('member_details_file', type=click.File('r') )
def refresh_member_credentials(username, password, output, sheet_id, sheet_name, member_details_file):
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
            click.echo(df.to_csv(index=False))
        elif output == 'gsheet':
            if not sheet_id:
                click.echo("Sheet ID is required for Google Sheet output.", err=True)
                return
            gsheet_client = get_gspread_client()
            write_df_to_sheet(df, sheet_id, sheet_name, gsheet_client)

if __name__ == '__main__':
    cli()
