import gspread
import click
import google.auth

def get_gspread_client():
    """
    Returns an authenticated gspread client using Application Default Credentials.
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds, project = google.auth.default(scopes=scopes)
    client = gspread.authorize(creds)
    return client

def write_df_to_sheet(df, sheet_id, sheet_name, client):
    """
    Writes a pandas DataFrame to a Google Sheet.
    """
    spreadsheet = client.open_by_key(sheet_id)
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="20")
    
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    click.echo(f"Successfully wrote data to sheet: {sheet_name}")
