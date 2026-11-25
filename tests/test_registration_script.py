"""Exercise the PowerShell pipeline with fake network commands and real schema validation."""

import csv
import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

from src.member_schema import load_schema

ROOT = Path(__file__).parents[1]
SHELLS = [shell for name in ('pwsh', 'powershell') if (shell := shutil.which(name))]
pytestmark = pytest.mark.skipif(not SHELLS, reason='PowerShell is not installed')


@pytest.fixture(params=SHELLS or [None], ids=lambda shell: Path(shell).stem if shell else 'unavailable')
def shell(request):
    return request.param


def run_script(tmp_path, shell, *, missing=False, invalid=False):
    repo = tmp_path / 'repo'
    scripts = repo / 'scripts'
    scripts.mkdir(parents=True)
    (repo / 'schemas').mkdir()
    shutil.copy(ROOT / 'schemas/rems-members.toml', repo / 'schemas/rems-members.toml')
    if invalid:
        (repo / 'schemas/rems-members.toml').write_text('columns=[]', encoding='utf-8')
    shutil.copytree(ROOT / 'src', repo / 'src', ignore=shutil.ignore_patterns('__pycache__'))
    script = (ROOT / 'scripts/refresh-registration.ps1').read_text(encoding='utf-8')
    # Only substitute the executable: the pipeline and validation code run unchanged.
    script = script.replace("'.venv\\Scripts\\python.exe'", "'python-stub.ps1'")
    (scripts / 'refresh-registration.ps1').write_text(script, encoding='utf-8')
    headers = list(load_schema(ROOT / 'schemas/rems-members.toml').columns)
    if missing:
        headers.remove('REMS ID')
    csv_out = StringIO()
    writer = csv.writer(csv_out)
    writer.writerow(headers)
    writer.writerow([''] * len(headers))
    (repo / 'source.csv').write_text(csv_out.getvalue(), encoding='utf-8')
    (repo / 'python-stub.ps1').write_text(r'''
Add-Content -LiteralPath $env:SCHEMA_TEST_LOG -Value ($args -join ' ')
if ($args[0] -eq '-m' -and $args[1] -eq 'src.member_schema') {
    & $env:SCHEMA_TEST_PYTHON @args
    $global:LASTEXITCODE = $LASTEXITCODE
    return
}
$outputIndex = [Array]::IndexOf($args, '--output-file')
if ($outputIndex -ge 0) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'source.csv') -Destination $args[$outputIndex + 1] }
$global:LASTEXITCODE = 0
''', encoding='utf-8')
    harness = tmp_path / 'run.ps1'
    harness.write_text(r'''
function global:gcloud {
    Add-Content -LiteralPath $env:SCHEMA_TEST_LOG -Value ('gcloud ' + ($args -join ' '))
    $global:LASTEXITCODE = 0
}
try {
    & (Join-Path $env:SCHEMA_TEST_REPO 'scripts/refresh-registration.ps1') -Team test -Season 2026-2027 -SheetId test-sheet -ServiceAccount test-account -OutDir './output'
} catch { Write-Output $_.Exception.Message; exit 1 }
''', encoding='utf-8')
    log = tmp_path / 'calls.log'
    env = {**os.environ, 'TEMP': str(tmp_path), 'SCHEMA_TEST_LOG': str(log), 'SCHEMA_TEST_REPO': str(repo),
           'SCHEMA_TEST_PYTHON': sys.executable}
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    calls = log.read_text(encoding='utf-8-sig').splitlines() if log.exists() else []
    return result, calls, tmp_path / 'output'


def test_script_validates_committed_schema_and_keeps_raw_intermediate(tmp_path, shell):
    result, calls, out = run_script(tmp_path, shell)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'src.member_schema' in calls[0]
    refresh = next(i for i, line in enumerate(calls) if 'src.main refresh-members ' in line)
    assert 'src.member_schema' in calls[refresh + 1]
    assert '--schema' not in calls[refresh]
    upload = next(line for line in calls if 'src.main upload-members ' in line)
    assert '--schema' in upload and 'schemas' in upload
    assert (out / 'members.csv').exists()


def test_missing_column_stops_before_following_refreshes_and_all_uploads(tmp_path, shell):
    result, calls, _ = run_script(tmp_path, shell, missing=True)
    assert result.returncode != 0
    assert 'REMS ID' in result.stdout + result.stderr
    assert not any('refresh-member-details' in line or 'upload-' in line for line in calls)


def test_invalid_schema_stops_before_google_login(tmp_path, shell):
    result, calls, _ = run_script(tmp_path, shell, invalid=True)
    assert result.returncode != 0
    assert not any('gcloud' in line or 'src.main' in line for line in calls)
