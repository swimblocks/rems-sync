<#
.SYNOPSIS
    Refresh a season's Officials Registration sheet from REMS in one go.

.DESCRIPTION
    Runs the full pipeline: refresh-members -> refresh-member-details ->
    refresh-member-credentials (to CSV), then uploads all three CSVs to the sheet.

    Google auth is temporary: the script logs in with service-account impersonation into a
    throwaway gcloud config folder (via CLOUDSDK_CONFIG), and revokes and deletes it when it
    finishes, even on failure. Your normal gcloud login is never touched.

    REMS credentials come from the saved login for -Team; save it once first with
    `python -m src.main auth login --team <alias>`. REMS may ask for an MFA code.

    Member columns follow the committed schemas/rems-members.toml contract. New columns are
    appended; missing expected columns stop the run before further refreshes or any uploads.

.PARAMETER Team
    Saved REMS login (alias) to use, e.g. row.

.PARAMETER Season
    Season to refresh, e.g. 2026-2027.

.PARAMETER SheetId
    Google Sheet ID of the season's registration sheet. Defaults to the season's entry in the
    [sheets] table of rems-sync's config.toml (the file `auth login` writes), e.g.
        [sheets]
        "2026-2027" = "<sheet_id>"
    Sheet IDs live there rather than in this public repo.

.PARAMETER OutDir
    Where to write the CSVs. Defaults to a new timestamped folder under
    ~\Downloads\rems-sync\<Season>\.

.PARAMETER ServiceAccount
    Service account to impersonate. Defaults to rems-sync-sa in the project_id from
    terraform/terraform.tfvars.

.EXAMPLE
    .\scripts\refresh-registration.ps1 -Team row -Season 2026-2027
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Team,
    [Parameter(Mandatory)][string]$Season,
    [string]$SheetId,
    [string]$OutDir,
    [string]$ServiceAccount
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$MemberSchema = Join-Path $RepoRoot 'schemas\rems-members.toml'

if (-not (Test-Path $Python)) { throw "No virtualenv at $Python. See README Quick start." }
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud not found on PATH." }

# Check local configuration before opening the Google sign-in browser.
Push-Location $RepoRoot
try {
    & $Python -m src.member_schema $MemberSchema
    if ($LASTEXITCODE -ne 0) { throw "The committed member schema is invalid." }
}
finally { Pop-Location }

if (-not $SheetId) {
    Push-Location $RepoRoot
    try {
        $lookup = "import sys; from src.credentials import config_file, season_sheet_ids; " +
                  "print(season_sheet_ids().get(sys.argv[1], '')); print(config_file())"
        $SheetId, $configFile = & $Python -c $lookup $Season
        if ($LASTEXITCODE -ne 0) { throw "Could not read the rems-sync config file." }
    }
    finally { Pop-Location }
    if (-not $SheetId) {
        throw "No sheet for season $Season. Pass -SheetId, or add it to ${configFile}:`n[sheets]`n`"$Season`" = `"<sheet_id>`""
    }
    Write-Host "Using sheet $SheetId for $Season (from $configFile)"
}

if (-not $ServiceAccount) {
    $tfvars = Join-Path $RepoRoot 'terraform\terraform.tfvars'
    $m = if (Test-Path $tfvars) { Select-String -Path $tfvars -Pattern '^\s*project_id\s*=\s*"([^"]+)"' } else { $null }
    if (-not $m) { throw "Pass -ServiceAccount, or set project_id in $tfvars." }
    $ServiceAccount = "rems-sync-sa@$($m.Matches[0].Groups[1].Value).iam.gserviceaccount.com"
}

if (-not $OutDir) {
    $OutDir = Join-Path $HOME "Downloads\rems-sync\$Season\$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}
# Absolute, because the CLI steps run from the repo root (Push-Location below), not the caller's directory.
$OutDir = (New-Item -ItemType Directory -Force $OutDir).FullName
$Members     = Join-Path $OutDir 'members.csv'
$Details     = Join-Path $OutDir 'member_details.csv'
$Credentials = Join-Path $OutDir 'credentials.csv'

# Remember env vars we change so they can be restored exactly.
$saved = @{}
foreach ($name in @('CLOUDSDK_CONFIG')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

function Invoke-Step([string]$Name, [string[]]$CliArgs, [string]$ExpectFile) {
    Write-Host "`n==> $Name" -ForegroundColor Cyan
    & $Python -m src.main @CliArgs
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE)." }
    # Some commands print an error and still exit 0; a missing output file catches that.
    if ($ExpectFile -and -not (Test-Path $ExpectFile)) { throw "$Name did not produce $ExpectFile." }
}

$gcloudDir = Join-Path $env:TEMP "rems-sync-gcloud-$([guid]::NewGuid().ToString('N'))"
Push-Location $RepoRoot
try {
    $env:CLOUDSDK_CONFIG = $gcloudDir
    Write-Host "==> Google login (temporary, impersonating $ServiceAccount)" -ForegroundColor Cyan
    gcloud auth application-default login --impersonate-service-account=$ServiceAccount
    if ($LASTEXITCODE -ne 0) { throw "gcloud login failed." }

    Invoke-Step 'Refresh members' @('refresh-members', '--team', $Team, '--season', $Season, '--output', 'csv', '--output-file', $Members) $Members
    # Preserve the raw CSV for member-details, but reject schema drift before touching any tab.
    & $Python -m src.member_schema $MemberSchema $Members
    if ($LASTEXITCODE -ne 0) { throw "Member CSV does not satisfy the committed schema; no tabs were uploaded." }
    Invoke-Step 'Refresh member details' @('refresh-member-details', $Members, '--team', $Team, '--season', $Season, '--output', 'csv', '--output-file', $Details) $Details
    Invoke-Step 'Refresh member credentials' @('refresh-member-credentials', $Details, '--team', $Team, '--output', 'csv', '--output-file', $Credentials) $Credentials

    Invoke-Step 'Upload members' @('upload-members', '--input-file', $Members, '--sheet-id', $SheetId, '--schema', $MemberSchema)
    Invoke-Step 'Upload member details' @('upload-member-details', '--input-file', $Details, '--sheet-id', $SheetId)
    Invoke-Step 'Upload member credentials' @('upload-member-credentials', '--input-file', $Credentials, '--sheet-id', $SheetId)

    Write-Host "`nDone. CSVs are in $OutDir" -ForegroundColor Green
}
finally {
    Pop-Location
    if (Test-Path $gcloudDir) {
        Write-Host "`n==> Revoking temporary Google login" -ForegroundColor Cyan
        # No 2>$null: under Windows PowerShell 5.1 with Stop, redirected native stderr throws.
        try { gcloud auth application-default revoke --quiet } catch { Write-Warning "Revoke failed: $_" }
        Remove-Item -Recurse -Force $gcloudDir -ErrorAction SilentlyContinue
    }
    foreach ($name in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
}
