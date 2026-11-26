import csv
import io
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.member_schema import load_schema, project_csv, validate


def schema_file(tmp_path, text='columns = ["ID", "Value"]\n'):
    path = tmp_path / 'schema.toml'
    path.write_text(text, encoding='utf-8')
    return path


@pytest.mark.parametrize('policy, expected', [
    ('append', ['ID', 'Value', 'New', 'Other']), ('drop', ['ID', 'Value']),
])
def test_projection_keeps_order_and_text(tmp_path, capsys, policy, expected):
    schema = load_schema(schema_file(tmp_path), extra_columns=policy)
    source = 'New,Value,ID,Other,\nextra,"NA, café",00012,last,\n'
    df = project_csv(source, schema)
    assert list(df.columns) == expected
    assert df['ID'].tolist() == ['00012']
    assert df['Value'].tolist() == ['NA, café']
    assert list(csv.reader(io.StringIO(df.to_csv(index=False))))[1][:2] == ['00012', 'NA, café']
    assert 'New' in capsys.readouterr().err
    assert project_csv(df.to_csv(index=False), schema).equals(df)


def test_missing_warn_preserves_position_and_exact_names(tmp_path, capsys):
    schema = load_schema(schema_file(tmp_path))
    df = project_csv('id,Value\n00012,NA\n', schema)
    assert list(df.columns) == ['ID', 'Value', 'id']
    assert df.iloc[0].tolist() == ['', 'NA', '00012']
    assert 'ID' in capsys.readouterr().err


def test_missing_error_lists_all_columns_but_allows_empty_cells(tmp_path):
    schema = load_schema(schema_file(tmp_path), missing_columns='error')
    with pytest.raises(ValueError, match='ID.*Value'):
        project_csv('Else\nx\n', schema)
    assert project_csv('ID,Value\n,\n', schema).iloc[0].tolist() == ['', '']


@pytest.mark.parametrize('text', [
    '', 'columns=[]', 'columns="ID"', 'columns=["ID", "ID"]',
    'columns=[" "]', 'columns=[1]', 'columns=["ID"]\nextra_columns="ignore"',
    'columns=["ID"]\nmissing_columns="fill"', 'columns=["ID"]\nunknown=true',
    'columns = [',
])
def test_invalid_schema_is_rejected(tmp_path, text):
    with pytest.raises(ValueError):
        load_schema(schema_file(tmp_path, text))


def test_missing_file_and_override_without_schema(tmp_path):
    with pytest.raises(ValueError):
        load_schema(tmp_path / 'absent.toml')
    with pytest.raises(ValueError, match='require.*--schema'):
        load_schema(None, extra_columns='drop')
    assert load_schema(None) is None


def test_policy_overrides_and_significant_spaces(tmp_path):
    schema = load_schema(schema_file(tmp_path, 'columns=[" A "]\nextra_columns="drop"\nmissing_columns="error"'),
                         extra_columns='append', missing_columns='warn')
    assert schema.columns == (' A ',)
    assert schema.extra_columns == 'append'
    assert schema.missing_columns == 'warn'
    assert project_csv(' A \nx\n', schema).iloc[0, 0] == 'x'


@pytest.mark.parametrize('source', [
    '', 'ID,ID\na,b\n', 'ID,,Value\na,,b\n', 'ID, \na,hidden\n',
    'ID,\na,hidden\n', 'ID,Value\na,b,c\n', 'ID,Value\na\n',
    'ID,Value\n"unclosed,b\n',
])
def test_ambiguous_or_malformed_csv_is_rejected(tmp_path, source):
    with pytest.raises(ValueError):
        project_csv(source, load_schema(schema_file(tmp_path)))


def test_header_only_bom_and_multiple_empty_trailing_fields(tmp_path):
    schema = load_schema(schema_file(tmp_path))
    df = project_csv('\ufeffID,Value,,\r\n', schema)
    assert list(df.columns) == ['ID', 'Value']
    assert df.empty


def test_committed_schema_contract():
    schema = load_schema(Path(__file__).parents[1] / 'schemas/rems-members.toml')
    assert len(schema.columns) == 117
    assert schema.columns[59] == 'REMS ID'
    assert schema.columns[18] == 'Phone Number'
    assert schema.extra_columns == 'append'
    assert schema.missing_columns == 'error'


def test_preflight_entry_point(tmp_path):
    path = schema_file(tmp_path, 'columns=["ID"]\nmissing_columns="error"')
    source = tmp_path / 'input.csv'
    source.write_text('Else\nx\n', encoding='utf-8')
    runner = CliRunner()
    assert runner.invoke(validate, [str(path)]).exit_code == 0
    failed = runner.invoke(validate, [str(path), str(source)])
    assert failed.exit_code != 0
    assert 'ID' in failed.output
