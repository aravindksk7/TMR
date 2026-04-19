#Requires -Version 5.1
<#
.SYNOPSIS
    Build QA-Pipeline-Report.pbit from the TMDL semantic model.

.DESCRIPTION
    Step 1 - Uses pbi-tools to convert TMDL sources to a BIM (TMSL JSON) file.
    Step 2 - Uses make_pbit.py to pack the BIM + report layout into a .pbit template.

    Opening the resulting .pbit in Power BI Desktop will prompt for DB credentials
    and trigger an initial data refresh.  Then: File > Save As > .pbix.

    Requirements:
      - Python 3.x on PATH
      - pbi-tools.exe at C:\Users\<you>\AppData\Local\pbi-tools\pbi-tools.exe
        (run with -InstallPbiTools to download automatically)
      - Power BI Desktop installed

.EXAMPLE
    .\build_pbix.ps1
    .\build_pbix.ps1 -InstallPbiTools
#>
param(
    [switch]$InstallPbiTools
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ROOT           = $PSScriptRoot
$PBIXPROJ_DIR   = Join-Path $ROOT "pbixproj"
$BIM_FILE       = Join-Path $ROOT "pbixproj.bim"
$MAKE_PBIT      = Join-Path $ROOT "make_pbit.py"
$TMDL_SRC       = Join-Path $ROOT "powerbi\semantic-model\definition"
$PBI_TOOLS_EXE  = "$env:LOCALAPPDATA\pbi-tools\pbi-tools.exe"

# ── Install pbi-tools if requested ────────────────────────────────────────────
if ($InstallPbiTools -and -not (Test-Path $PBI_TOOLS_EXE)) {
    Write-Host "Downloading pbi-tools 1.2.0 ..."
    $zip = "$env:TEMP\pbi-tools.zip"
    Invoke-WebRequest "https://github.com/pbi-tools/pbi-tools/releases/download/1.2.0/pbi-tools.1.2.0.zip" `
        -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath (Split-Path $PBI_TOOLS_EXE) -Force
    Write-Host "pbi-tools installed at $PBI_TOOLS_EXE"
}

if (-not (Test-Path $PBI_TOOLS_EXE)) {
    Write-Error "pbi-tools not found at $PBI_TOOLS_EXE. Run with -InstallPbiTools or install manually."
}

# ── Step 1: Sync TMDL files into pbixproj/Model ──────────────────────────────
Write-Host ""
Write-Host "=== Step 1: Sync TMDL to pbixproj/Model ===" -ForegroundColor Yellow

$modelDir = Join-Path $PBIXPROJ_DIR "Model"
New-Item "$modelDir\tables" -ItemType Directory -Force | Out-Null
Copy-Item "$TMDL_SRC\model.tmdl"          $modelDir -Force
Copy-Item "$TMDL_SRC\relationships.tmdl"  $modelDir -Force
Copy-Item "$TMDL_SRC\database.tmdl"       $modelDir -Force
Copy-Item "$TMDL_SRC\tables\*.tmdl"       "$modelDir\tables\" -Force
$count = (Get-ChildItem "$modelDir\tables\*.tmdl").Count
Write-Host "Synced $count table files"

# ── Step 2: Generate BIM ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Step 2: Generate BIM (TMSL JSON) ===" -ForegroundColor Yellow
& $PBI_TOOLS_EXE generate-bim $PBIXPROJ_DIR

if ($LASTEXITCODE -ne 0) {
    Write-Error "generate-bim failed (exit $LASTEXITCODE)"
}
Write-Host "BIM written to: $BIM_FILE"

# ── Step 3: Build PBIT ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Step 3: Build PBIT ===" -ForegroundColor Yellow
python $MAKE_PBIT

if ($LASTEXITCODE -ne 0) {
    Write-Error "make_pbit.py failed (exit $LASTEXITCODE)"
}

# ── Summary ───────────────────────────────────────────────────────────────────
$pbit = Join-Path $ROOT "QA-Pipeline-Report.pbit"
if (Test-Path $pbit) {
    $kb = [math]::Round((Get-Item $pbit).Length / 1KB, 1)
    Write-Host ""
    Write-Host "SUCCESS: $pbit ($kb KB)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Double-click QA-Pipeline-Report.pbit to open in Power BI Desktop"
    Write-Host "  2. Enter SQL Server credentials (127.0.0.1,1433 / Reporting_DB)"
    Write-Host "  3. Wait for data refresh"
    Write-Host "  4. File > Save As > QA-Pipeline-Report.pbix"
    Write-Host "  5. Start building your canvas!"
}
