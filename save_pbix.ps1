# PowerShell script to save PBIX file from Power BI Desktop using COM interface
param(
    [string]$FilePath = "c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix"
)

try {
    # Load required assemblies
    [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
    
    # Get Power BI Desktop process
    $pbiProcess = Get-Process PBIDesktop -ErrorAction Stop
    
    # Focus the Power BI window
    $hwnd = $pbiProcess.MainWindowHandle
    
    # Use Windows API to set foreground window
    $sig = @'
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
'@
    $WinAPI = Add-Type -MemberDefinition $sig -Name WinEventHook -PassThru
    $WinAPI::SetForegroundWindow($hwnd) | Out-Null
    $WinAPI::ShowWindow($hwnd, 5) | Out-Null
    
    Start-Sleep -Milliseconds 500
    
    # Send keyboard sequence to trigger Save As: Ctrl+Shift+S
    [System.Windows.Forms.SendKeys]::SendWait("^+s")
    
    # Wait for dialog to appear
    Start-Sleep -Seconds 1
    
    # Type the full file path
    [System.Windows.Forms.SendKeys]::SendWait($FilePath)
    
    # Wait a moment
    Start-Sleep -Milliseconds 500
    
    # Press Enter to save
    [System.Windows.Forms.SendKeys]::SendWait("~")
    
    Write-Host "Save command sent. File should be saved to: $FilePath"
    Start-Sleep -Seconds 2
    
    # Verify file was created
    if (Test-Path $FilePath) {
        Write-Host "✓ PBIX file successfully saved: $FilePath"
        Write-Host "File size: $(Get-Item $FilePath).Length bytes"
    } else {
        Write-Host "⚠ File not found at $FilePath. Checking Documents folder..."
        $docPath = "$env:USERPROFILE\Documents\*.pbix"
        Get-ChildItem -Path $docPath -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object {
            Write-Host "Found recent PBIX: $($_.FullName)"
        }
    }
}
catch {
    Write-Host "Error: $($_.Exception.Message)"
}
