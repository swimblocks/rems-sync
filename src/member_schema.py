"""Ordered member CSV contracts, shared by the CLI and registration preflight.

Only headers appear in diagnostics: member data must never be logged. CSV values remain
strings so identifiers, postal codes, and literal NA values survive projection unchanged.
"""

import csv
import tomllib
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import click
import pandas as pd


@dataclass(frozen=True)
class MemberSchema:
    """The ordered output columns and policies for member CSV projection.

    Attributes:
        columns: Unique header names in the required output order, matched exactly.
        extra_columns: 'append' keeps unexpected fields at the end; 'drop' omits them.
        missing_columns: 'warn' fills absent headers with blanks; 'error' rejects them.
    """

    columns: tuple[str, ...]
    extra_columns: str = 'append'
    missing_columns: str = 'warn'


def load_schema(path, *, extra_columns=None, missing_columns=None):
    """Validate a TOML contract and apply independent CLI policy overrides.

    None means pass-through. Policy overrides require an explicit schema.
    """
    if path is None:
        if extra_columns is not None or missing_columns is not None:
            raise ValueError('Column policy overrides require --schema.')
        return None
    try:
        data = tomllib.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as e:
        # Do not echo malformed file contents: a caller may have selected a member CSV.
        raise ValueError(f'Cannot read schema {path}: expected a UTF-8 TOML file.') from e
    if set(data) - {'columns', 'extra_columns', 'missing_columns'}:
        raise ValueError('Unknown schema keys; allowed: columns, extra_columns, missing_columns.')
    columns = data.get('columns')
    if (not isinstance(columns, list) or not columns
            or any(not isinstance(c, str) or not c.strip() for c in columns)):
        raise ValueError('Schema columns must be a non-empty list of non-empty strings.')
    if len(set(columns)) != len(columns):
        raise ValueError('Schema columns must be unique.')
    for key, override, default, choices in (
        ('extra_columns', extra_columns, 'append', ('append', 'drop')),
        ('missing_columns', missing_columns, 'warn', ('warn', 'error')),
    ):
        file_value = data.get(key, default)
        if file_value not in choices:
            raise ValueError(f'Schema {key} must be one of: {", ".join(choices)}.')
        if override is not None and override not in choices:
            raise ValueError(f'Override {key} must be one of: {", ".join(choices)}.')
        data[key] = override if override is not None else file_value
    return MemberSchema(tuple(columns), data['extra_columns'], data['missing_columns'])


def _read_named_rows(source):
    """Parse unambiguous named fields, rejecting malformed or populated unnamed fields."""
    try:
        reader = csv.reader(StringIO(source.lstrip('\ufeff'), newline=''), strict=True)
        headers = next(reader, None)
        if not headers:
            raise ValueError('Member CSV has no header.')
        named_count = len(headers)
        while named_count and not headers[named_count - 1].strip():
            named_count -= 1
        named = headers[:named_count]
        if not named or any(not h.strip() for h in named):
            raise ValueError('Member CSV has an unnamed header between named fields.')
        if len(set(named)) != len(named):
            raise ValueError('Member CSV contains duplicate headers.')
        rows = []
        for row in reader:
            if not row:  # Ignore genuinely empty lines, as pandas does in the old path.
                continue
            if len(row) != len(headers):
                raise ValueError(f'Member CSV record near line {reader.line_num} has the wrong field count.')
            if any(row[named_count:]):
                raise ValueError('Member CSV has data under an unnamed trailing header.')
            rows.append(row[:named_count])
    except csv.Error as e:
        raise ValueError('Malformed member CSV quoting.') from e
    return named, rows


def project_csv(source, schema):
    """Return a string-valued DataFrame in schema order, or reject ambiguous input.

    Complete parsing and validation happen before a caller opens an output file or clears
    a worksheet. Missing-column checks concern header presence, not empty member cells.
    """
    named, rows = _read_named_rows(source)

    missing = [c for c in schema.columns if c not in named]
    if missing:
        message = 'Missing expected member columns: ' + ', '.join(missing)
        if schema.missing_columns == 'error':
            raise ValueError(message)
        click.echo('Warning: ' + message, err=True)
    extras = [c for c in named if c not in schema.columns]
    if extras:
        action = 'Appending' if schema.extra_columns == 'append' else 'Dropping'
        click.echo(f'{action} unexpected member columns: {", ".join(extras)}', err=True)
    order = list(schema.columns) + (extras if schema.extra_columns == 'append' else [])
    return pd.DataFrame(rows, columns=named, dtype=str).reindex(columns=order, fill_value='')


def project_csv_file(path, schema):
    """Project a CSV file without translating line endings embedded in quoted cells."""
    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        return project_csv(source.read(), schema)


@click.command()
@click.argument('schema_path', type=click.Path(path_type=Path))
@click.argument('csv_path', required=False, type=click.Path(path_type=Path))
def validate(schema_path, csv_path):
    """Internal registration preflight: validate SCHEMA_PATH and optionally CSV_PATH.

    Run as python -m src.member_schema. It produces no output files or network requests.
    """
    try:
        schema = load_schema(schema_path)
        if csv_path is not None:
            project_csv_file(csv_path, schema)
    except (ValueError, OSError, UnicodeError) as e:
        raise click.ClickException(str(e)) from e


if __name__ == '__main__':
    validate()
