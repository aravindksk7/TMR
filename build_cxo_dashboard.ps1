#Requires -Version 5.1
<#
.SYNOPSIS
    Build P1 | CXO Quality Dashboard -- full end-to-end pipeline.

.DESCRIPTION
    Step 1  Inject CXO dashboard layout (ETMI visuals) into QA-Pipeline-Report.pbix
    Step 2  Sync TMDL sources (incl. ETMI measures) to pbixproj/Model
    Step 3  Compile TMDL -> BIM via pbi-tools generate-bim
    Step 4  Pack BIM + patched layout -> QA-Pipeline-Report.pbit via make_pbit.py
    Step 5  Open the PBIT in Power BI Desktop

    ETMI = (Automation Coverage pct x 0.4) + (Regression Automation pct x 0.3) + (Execution Efficiency pct x 0.3)

.EXAMPLE
    .\build_cxo_dashboard.ps1
    .\build_cxo_dashboard.ps1 -SkipOpen
#>
param(
    [switch]$SkipOpen
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ROOT          = $PSScriptRoot
$TMDL_SRC      = Join-Path $ROOT "powerbi\semantic-model\definition"
$PBIXPROJ_DIR  = Join-Path $ROOT "pbixproj"
$BIM_FILE      = Join-Path $ROOT "pbixproj.bim"
$MAKE_PBIT     = Join-Path $ROOT "make_pbit.py"
$LAYOUT_SCRIPT = Join-Path $ROOT "scripts\build_p1_layout.py"
$PBIX_FILE     = Join-Path $ROOT "QA-Pipeline-Report.pbix"
$PBIT_OUT      = Join-Path $ROOT "QA-Pipeline-Report.pbit"
$PBI_TOOLS_EXE = "$env:LOCALAPPDATA\pbi-tools\pbi-tools.exe"

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "=== Step ${n}: $msg ===" -ForegroundColor Yellow
}

if (-not (Test-Path $PBIX_FILE)) {
    Write-Error "QA-Pipeline-Report.pbix not found at $PBIX_FILE"
}
if (-not (Test-Path $PBI_TOOLS_EXE)) {
    Write-Error "pbi-tools not found at $PBI_TOOLS_EXE. Run build_pbix.ps1 -InstallPbiTools first."
}

# Check if PBIX is locked by Power BI Desktop
try {
    $stream = [System.IO.File]::Open($PBIX_FILE, 'Open', 'ReadWrite', 'None')
    $stream.Close()
} catch {
    Write-Host ""
    Write-Host "ERROR: QA-Pipeline-Report.pbix is open in Power BI Desktop." -ForegroundColor Red
    Write-Host "       Close Power BI Desktop first, then re-run this script." -ForegroundColor Red
    exit 1
}

# Step 1: Inject CXO layout into PBIX
Write-Step 1 "Inject CXO Quality Dashboard layout into PBIX"
python $LAYOUT_SCRIPT
if ($LASTEXITCODE -ne 0) { Write-Error "build_p1_layout.py failed (exit $LASTEXITCODE)" }
Write-Host "Layout patched OK" -ForegroundColor Green

# Step 2: Sync TMDL to pbixproj/Model
Write-Step 2 "Sync TMDL sources to pbixproj/Model"
$modelDir = Join-Path $PBIXPROJ_DIR "Model"
New-Item "$modelDir\tables" -ItemType Directory -Force | Out-Null
Copy-Item "$TMDL_SRC\model.tmdl"         $modelDir -Force
Copy-Item "$TMDL_SRC\relationships.tmdl" $modelDir -Force
Copy-Item "$TMDL_SRC\database.tmdl"      $modelDir -Force
Copy-Item "$TMDL_SRC\tables\*.tmdl"      "$modelDir\tables\" -Force
$count = (Get-ChildItem "$modelDir\tables\*.tmdl").Count
Write-Host "Synced $count table TMDL files" -ForegroundColor Green

# Step 3: Generate BIM
Write-Step 3 "Generate BIM (TMSL JSON) from TMDL"
& $PBI_TOOLS_EXE generate-bim $PBIXPROJ_DIR
if ($LASTEXITCODE -ne 0) { Write-Error "pbi-tools generate-bim failed (exit $LASTEXITCODE)" }
Write-Host "BIM written OK" -ForegroundColor Green

# Step 4: Build PBIT
Write-Step 4 "Pack PBIT (model + layout)"
python $MAKE_PBIT
if ($LASTEXITCODE -ne 0) { Write-Error "make_pbit.py failed (exit $LASTEXITCODE)" }

if (-not (Test-Path $PBIT_OUT)) {
    Write-Error "PBIT not created -- check make_pbit.py output above"
}
$sizeKb = [math]::Round((Get-Item $PBIT_OUT).Length / 1KB, 1)
Write-Host "PBIT built ($sizeKb KB)" -ForegroundColor Green

# Step 5: Open in Power BI Desktop
if (-not $SkipOpen) {
    Write-Step 5 "Opening QA-Pipeline-Report.pbit in Power BI Desktop"
    Start-Process $PBIT_OUT
    Write-Host "Power BI Desktop launching ..." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "BUILD COMPLETE" -ForegroundColor Green
Write-Host ""
Write-Host "Applied:" -ForegroundColor Cyan
Write-Host "  Model   : 7 new ETMI DAX measures in vw_p1_qa_health_by_release"
Write-Host "            (Automation Coverage %, Regression Automation %,"
Write-Host "             Execution Efficiency %, ETMI Score, ETMI Band,"
Write-Host "             ETMI Target, ETMI Status)"
Write-Host "  Layout  : P1 | CXO Quality Dashboard"
Write-Host "            ETMI gauge + 3 component cards + Band + Status"
Write-Host "            ETMI trend by release + Release ETMI Breakdown table"
Write-Host ""
Write-Host "Next steps in Power BI Desktop:" -ForegroundColor Cyan
Write-Host "  1. Enter SQL Server credentials (127.0.0.1,1433 / Reporting_DB)"
Write-Host "  2. Click Refresh to load data"
Write-Host "  3. Verify ETMI Score gauge and component cards"
Write-Host "  4. File > Save As > QA-Pipeline-Report.pbix"
Write-Host ""
Write-Host "Note: If Regression Automation % shows 0, confirm dim_test_type has"
Write-Host "      a row where test_type_name = 'Regression' in your database."
