import os
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from src.main import cli

@pytest.fixture
def runner():
    return CliRunner()

@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_refresh_members_csv(mock_mfa, mock_client_class, runner, tmp_path):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_members_csv.return_value = "header1,header2\nvalue1,value2"
    
    output_file = tmp_path / "members.csv"
    
    result = runner.invoke(cli, [
        'refresh-members',
        '--username', 'testuser',
        '--password', 'testpass',
        '--season', '2025',
        '--output', 'csv',
        '--output-file', str(output_file)
    ])
    
    assert result.exit_code == 0
    assert f"Successfully wrote data to {output_file}" in result.output
    assert output_file.read_text(encoding='utf-8').strip() == "header1,header2\nvalue1,value2"

@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_refresh_members_csv_missing_file(mock_mfa, mock_client_class, runner):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_members_csv.return_value = "header1,header2\nvalue1,value2"
    
    result = runner.invoke(cli, [
        'refresh-members',
        '--username', 'testuser',
        '--password', 'testpass',
        '--season', '2025',
        '--output', 'csv'
    ])
    
    assert result.exit_code == 0 # click commands return 0 unless exception raised
    assert "Output file is required for CSV output." in result.output

@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_refresh_member_details_csv(mock_mfa, mock_client_class, runner, tmp_path):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "789"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC123456',
        'member_id': '456',
        'member_season_id': '789',
        'season_id': 123
    }
    
    input_file = tmp_path / "input.csv"
    input_file.write_text("Some Other Col,REMS ID\nval,SC12345678")
    
    output_file = tmp_path / "details.csv"
    
    result = runner.invoke(cli, [
        'refresh-member-details',
        '--username', 'testuser',
        '--password', 'testpass',
        '--season', '2025',
        '--output', 'csv',
        '--output-file', str(output_file),
        str(input_file)
    ])
    
    assert result.exit_code == 0
    assert "Found 1 valid unique REMS IDs in REMS ID column." in result.output
    assert f"Successfully wrote data to {output_file}" in result.output
    assert os.path.exists(output_file)

def test_refresh_member_details_missing_col(runner, tmp_path):
    input_file = tmp_path / "input.csv"
    input_file.write_text("Wrong Col\nval")
    
    result = runner.invoke(cli, [
        'refresh-member-details',
        '--username', 'testuser',
        '--password', 'testpass',
        '--season', '2025',
        str(input_file)
    ])
    
    assert result.exit_code == 0
    assert "Could not find REMS ID column" in result.output

@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_refresh_member_credentials_csv(mock_mfa, mock_client_class, runner, tmp_path):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_credentials.return_value = [
        {'name': 'Cred1', 'status': 'Active'}
    ]
    
    details_file = tmp_path / "details.csv"
    details_file.write_text("rems_id,member_id,member_season_id\nSC123456,456,789")
    
    output_file = tmp_path / "creds.csv"
    
    result = runner.invoke(cli, [
        'refresh-member-credentials',
        '--username', 'testuser',
        '--password', 'testpass',
        '--output', 'csv',
        '--output-file', str(output_file),
        str(details_file)
    ])
    
    assert result.exit_code == 0
    assert f"Successfully wrote data to {output_file}" in result.output
    assert os.path.exists(output_file)

@patch('src.main.get_gspread_client')
@patch('src.main.write_df_to_sheet')
def test_upload_members(mock_write_df, mock_get_client, runner, tmp_path):
    input_file = tmp_path / "input.csv"
    input_file.write_text("col1,col2\nval1,val2")
    
    result = runner.invoke(cli, [
        'upload-members',
        '--input-file', str(input_file),
        '--sheet-id', 'test-sheet-id'
    ])
    
    assert result.exit_code == 0
    assert "Uploading members from" in result.output
    mock_get_client.assert_called_once()
    mock_write_df.assert_called_once()

@patch('src.main.get_gspread_client')
@patch('src.main.write_df_to_sheet')
def test_upload_member_details(mock_write_df, mock_get_client, runner, tmp_path):
    input_file = tmp_path / "details.csv"
    input_file.write_text("rems_id,member_id\nSC12345678,456")
    
    result = runner.invoke(cli, [
        'upload-member-details',
        '--input-file', str(input_file),
        '--sheet-id', 'test-sheet-id'
    ])
    
    assert result.exit_code == 0
    assert "Uploading member details from" in result.output
    mock_get_client.assert_called_once()
    mock_write_df.assert_called_once()

@patch('src.main.get_gspread_client')
@patch('src.main.write_df_to_sheet')
def test_upload_member_credentials(mock_write_df, mock_get_client, runner, tmp_path):
    input_file = tmp_path / "credentials.csv"
    input_file.write_text("rems_id,member_id,member_season_id,name,type,first_name,last_name,status,start_date,expiry_date,actions\nSC12345678,456,789,Clinic,Type,First,Last,Active,28/01/2024,,/sportlomo/user/credentials/member-credential-history/231/178705/423, /sportlomo/user/credentials/view-member-credential-profile/231/178705/186777")
    
    result = runner.invoke(cli, [
        'upload-member-credentials',
        '--input-file', str(input_file),
        '--sheet-id', 'test-sheet-id'
    ])
    
    assert result.exit_code == 0
    assert "Uploading member credentials from" in result.output
    mock_get_client.assert_called_once()
    mock_write_df.assert_called_once()
