from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from click.testing import CliRunner

from src.gsheet import write_df_to_sheet
from src.main import cli

pytestmark = pytest.mark.usefixtures('saved_row_login')


@pytest.fixture
def files(tmp_path):
    schema = tmp_path / 'schema.toml'
    schema.write_text('columns=["ID", "Value"]\nmissing_columns="error"', encoding='utf-8')
    source = tmp_path / 'source.csv'
    source.write_text('New,Value,ID\nx,NA,00012\n', encoding='utf-8')
    return schema, source


@pytest.mark.parametrize('mode', ['csv', 'gsheet', 'upload'])
def test_all_member_outputs_use_same_projection(tmp_path, files, mode):
    schema, source = files
    dest = tmp_path / 'dest.csv'
    with (patch('src.main._rems_client') as client,
          patch('src.main.get_gspread_client'), patch('src.main.write_df_to_sheet') as write):
        client.return_value.get_members_csv.return_value = source.read_text()
        if mode == 'upload':
            args = ['upload-members', '--input-file', str(source), '--sheet-id', 'test-sheet']
        else:
            args = ['refresh-members', '--team', 'row', '--season', '2026', '--output', mode]
            args += ['--output-file', str(dest)] if mode == 'csv' else ['--sheet-id', 'test-sheet']
        result = CliRunner().invoke(cli, [*args, '--schema', str(schema)])
        assert result.exit_code == 0, result.output
        df = pd.read_csv(dest, dtype=str, keep_default_na=False) if mode == 'csv' else write.call_args.args[0]
        assert list(df.columns) == ['ID', 'Value', 'New']
        assert df.iloc[0].tolist() == ['00012', 'NA', 'x']


@pytest.mark.parametrize('command', ['refresh-members', 'refresh-gsheet', 'upload-members'])
@pytest.mark.parametrize('problem', ['invalid-schema', 'missing', 'duplicate'])
def test_schema_errors_leave_existing_output_and_google_untouched(tmp_path, files, command, problem):
    schema, source = files
    if problem == 'invalid-schema':
        schema.write_text('columns=[]', encoding='utf-8')
    elif problem == 'missing':
        source.write_text('Other\nx\n', encoding='utf-8')
    else:
        source.write_text('ID,ID\nx,y\n', encoding='utf-8')
    dest = tmp_path / 'dest.csv'
    dest.write_text('keep this', encoding='utf-8')
    with (patch('src.main._rems_client') as client,
          patch('src.main.get_gspread_client') as google,
          patch('src.main.write_df_to_sheet') as write):
        client.return_value.get_members_csv.return_value = source.read_text()
        args = (['refresh-members', '--team', 'row', '--season', '2026', '--output-file', str(dest)]
                if command != 'upload-members' else
                ['upload-members', '--input-file', str(source), '--sheet-id', 'test-sheet'])
        if command == 'refresh-gsheet':
            args += ['--output', 'gsheet', '--sheet-id', 'test-sheet']
        result = CliRunner().invoke(cli, [*args, '--schema', str(schema)])
        assert result.exit_code != 0
        assert 'No such option' not in result.output
        assert dest.read_text() == 'keep this'
        google.assert_not_called()
        write.assert_not_called()
        if problem == 'invalid-schema':
            client.assert_not_called()


def test_missing_file_schema_is_rejected_before_login(tmp_path):
    with patch('src.main._rems_client') as client:
        result = CliRunner().invoke(cli, ['refresh-members', '--team', 'row', '--season', '2026',
                                         '--schema', str(tmp_path / 'missing.toml')])
        assert result.exit_code != 0
        assert 'Cannot read schema' in result.output
        client.assert_not_called()


@pytest.mark.parametrize('option', ['--extra-columns', '--missing-columns'])
def test_override_without_schema_is_rejected_before_network(files, option):
    value = 'drop' if option == '--extra-columns' else 'error'
    with patch('src.main._rems_client') as client:
        result = CliRunner().invoke(cli, ['refresh-members', '--team', 'row', '--season', '2026', option, value])
        assert result.exit_code != 0
        assert '--schema' in result.output
        client.assert_not_called()


def test_cli_policy_overrides_file_policy(files):
    schema, source = files
    source.write_text('Value,Other\nNA,x\n', encoding='utf-8')
    with patch('src.main.get_gspread_client'), patch('src.main.write_df_to_sheet') as write:
        result = CliRunner().invoke(cli, ['upload-members', '--input-file', str(source),
                                         '--sheet-id', 'test-sheet', '--schema', str(schema),
                                         '--extra-columns', 'drop', '--missing-columns', 'warn'])
        assert result.exit_code == 0, result.output
        assert write.call_args.args[0].iloc[0].tolist() == ['', 'NA']
        assert 'Missing expected' in result.output


def test_schema_header_named_unnamed_survives_actual_sheet_writer(files):
    schema, source = files
    schema.write_text('columns=["Unnamed: expected", "ID"]', encoding='utf-8')
    source.write_text('ID,Unnamed: expected\n00012,NA\n', encoding='utf-8')
    google = MagicMock()
    with patch('src.main.get_gspread_client', return_value=google), \
            patch('src.main.write_df_to_sheet', wraps=write_df_to_sheet):
        result = CliRunner().invoke(cli, ['upload-members', '--input-file', str(source),
                                         '--sheet-id', 'test-sheet', '--schema', str(schema)])
    assert result.exit_code == 0, result.output
    sheet = google.open_by_key.return_value.worksheet.return_value
    assert sheet.update.call_args.args[0] == [['Unnamed: expected', 'ID'], ['NA', '00012']]


def test_upload_preserves_line_endings_inside_quoted_cells(files):
    schema, source = files
    source.write_bytes(b'ID,Value\r\n00012,"one\r\ntwo\rthree"\r\n')
    with patch('src.main.get_gspread_client'), patch('src.main.write_df_to_sheet') as write:
        result = CliRunner().invoke(cli, ['upload-members', '--input-file', str(source),
                                         '--sheet-id', 'test-sheet', '--schema', str(schema)])
    assert result.exit_code == 0, result.output
    assert write.call_args.args[0].iloc[0].tolist() == ['00012', 'one\r\ntwo\rthree']
