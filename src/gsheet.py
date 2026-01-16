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
    # Replace NaN with empty string to avoid JSON compliance issues
    df_filled = df.fillna('')
    # Filter out columns that are "Unnamed" (Pandas adds these for trailing commas)
    cols_to_include = [c for c in df_filled.columns if not str(c).startswith('Unnamed:')]
    df_final = df_filled[cols_to_include]
    worksheet.update([df_final.columns.values.tolist()] + df_final.values.tolist())
    click.echo(f"Successfully wrote data to sheet: {sheet_name}")
