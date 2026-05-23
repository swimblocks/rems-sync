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


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_happy_path(mock_mfa, mock_client_class, runner):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    # No existing IT evals → this will be #1
    mock_client.get_member_credentials.return_value = [
        {'type': 'Clinic', 'name': 'Some Clinic'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '452', 'type_id': '127'},
        {'label': 'Inspector of Turns Evaluation #2', 'credential_id': '453', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Inspector of Turns',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',
        '--description', 'Session 6',
    ])

    assert result.exit_code == 0, result.output
    assert 'Success: recorded deck eval #1' in result.output
    mock_client.add_member_credential.assert_called_once_with(
        member_season_id='685100',
        member_id='178722',
        credential_id='452',
        type_id='127',
        provider='Kaoru Yajima',
        provider_identifier='Cunningham Classic 2026',
        start_date='04/12/2026',
        description='Session 6',
    )


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_promotes_to_second_eval(mock_mfa, mock_client_class, runner):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    # Existing #1 eval for IT → next is #2
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #1'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '452', 'type_id': '127'},
        {'label': 'Inspector of Turns Evaluation #2', 'credential_id': '453', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Inspector of Turns',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',
        '--description', 'Session 6',
    ])

    assert result.exit_code == 0, result.output
    assert 'Success: recorded deck eval #2' in result.output
    assert mock_client.add_member_credential.call_args.kwargs['credential_id'] == '453'


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_member_not_found(mock_mfa, mock_client_class, runner):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = None

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Nobody Here',
        '--position', 'Starter',
        '--provider', 'p', '--meet', 'm', '--date', '2026-04-12', '--description', 'd',
    ])

    assert result.exit_code != 0
    assert 'Could not find official' in result.output


def _setup_chief_timer_existing(mock_client, existing_credentials):
    """Helper: member has two Chief Timekeeper evals; form offers #1 and #2.
    existing_credentials is the list returned by get_member_credentials (must include start_date)."""
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = existing_credentials
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Chief Timekeeper Evaluation #1', 'credential_id': '451', 'type_id': '127'},
        {'label': 'Chief Timekeeper Evaluation #2', 'credential_id': '452', 'type_id': '127'},
    ]


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_already_recorded_matching_date(mock_mfa, mock_client_class, runner):
    """An existing eval on the same date is treated as already recorded (regardless of meet name)."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    _setup_chief_timer_existing(mock_client, existing_credentials=[
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1', 'start_date': '15/03/2024'},
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #2', 'start_date': '12/04/2026'},
    ])

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Chief Timer',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',
        '--description', 'Session 6',
    ])

    assert result.exit_code == 0, result.output
    assert 'already recorded' in result.output.lower()
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_one_existing_same_date_is_duplicate(mock_mfa, mock_client_class, runner):
    """With one existing eval on the requested date, dedup catches it as a duplicate."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1', 'start_date': '12/04/2026'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Chief Timekeeper Evaluation #1', 'credential_id': '451', 'type_id': '127'},
        {'label': 'Chief Timekeeper Evaluation #2', 'credential_id': '452', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Chief Timer',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',
        '--description', 'Session 6',
    ])

    assert result.exit_code == 0, result.output
    assert 'already recorded' in result.output.lower()
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_one_existing_different_date_proceeds(mock_mfa, mock_client_class, runner):
    """With one existing eval on a DIFFERENT date, we proceed to add the next eval."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1', 'start_date': '15/03/2024'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Chief Timekeeper Evaluation #1', 'credential_id': '451', 'type_id': '127'},
        {'label': 'Chief Timekeeper Evaluation #2', 'credential_id': '452', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Chief Timer',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',
        '--description', 'Session 6',
    ])

    assert result.exit_code == 0, result.output
    assert 'Success' in result.output
    mock_client.add_member_credential.assert_called_once()
    assert mock_client.add_member_credential.call_args.kwargs['credential_id'] == '452'


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_default_bracket_catches_adjacent_meet_day(mock_mfa, mock_client_class, runner):
    """Without --meet-dates, the default Wed-Sun bracket catches a duplicate on another meet day."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    # Existing eval on Sat Apr 11 (mid-meet). User adds for Sun Apr 12 — same meet.
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1', 'start_date': '11/04/2026'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Chief Timekeeper Evaluation #1', 'credential_id': '451', 'type_id': '127'},
        {'label': 'Chief Timekeeper Evaluation #2', 'credential_id': '452', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Chief Timer',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',  # Sun
        '--description', 'Session 6',
        # No --meet-dates: should default to Wed Apr 8 .. Sun Apr 12.
    ])

    assert result.exit_code == 0, result.output
    assert 'already recorded' in result.output.lower()
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_meet_dates_flag_catches_other_session(mock_mfa, mock_client_class, runner):
    """--meet-dates lets add-deck-eval detect a duplicate on a different session of the same meet."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    # Existing eval on Apr 11 — different session of the same meet (Apr 10-12).
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1', 'start_date': '11/04/2026'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Chief Timekeeper Evaluation #1', 'credential_id': '451', 'type_id': '127'},
        {'label': 'Chief Timekeeper Evaluation #2', 'credential_id': '452', 'type_id': '127'},
    ]

    # User is trying to add on Apr 12, but provides --meet-dates covering the whole meet.
    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Chief Timer',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',
        '--description', 'Session 6',
        '--meet-dates', '2026-04-10,2026-04-11,2026-04-12',
    ])

    assert result.exit_code == 0, result.output
    assert 'already recorded' in result.output.lower()
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_at_max_but_different_dates(mock_mfa, mock_client_class, runner):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    _setup_chief_timer_existing(mock_client, existing_credentials=[
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #1', 'start_date': '15/03/2024'},
        {'type': 'Deck Evaluation', 'name': 'Chief Timekeeper Evaluation #2', 'start_date': '20/05/2025'},
    ])

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Chief Timer',
        '--provider', 'Kaoru Yajima',
        '--meet', 'Cunningham Classic 2026',
        '--date', '2026-04-12',
        '--description', 'Session 6',
    ])

    assert result.exit_code != 0
    assert 'max' in result.output.lower()
    assert 'resolve in rems' in result.output.lower()
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_add_deck_eval_dry_run_does_reads_but_no_post(mock_mfa, mock_client_class, runner):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.search_member_by_name.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '452', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'add-deck-eval',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--official-name', 'Chris Fletcher',
        '--position', 'Inspector of Turns',
        '--provider', 'p', '--meet', 'm', '--date', '2026-04-12', '--description', 'd',
        '--dry-run',
    ])

    assert result.exit_code == 0, result.output
    assert '[dry-run]' in result.output
    mock_client.login.assert_called_once()
    mock_client.search_member_by_name.assert_called_once()
    mock_client.get_add_credential_form_options.assert_called_once()
    mock_client.add_member_credential.assert_not_called()
