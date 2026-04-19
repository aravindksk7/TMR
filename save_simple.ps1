
$ErrorActionPreference = "SilentlyContinue"

# Find Power BI Desktop window
$pbiProcess = Get-Process -Name PBIDesktop -ErrorAction Stop

if ($pbiProcess) {
    Write-Host "Found Power BI Desktop process (PID: $($pbiProcess.Id))"
    
    # Get window handle
    $hwnd = $pbiProcess.MainWindowHandle
    
    # Load Windows API
    Add-Type -AssemblyName System.Windows.Forms
    
    $sig = @'
[DllImport("user32.dll")]
public static extern bool SetForegroundWindow(IntPtr hWnd);

[DllImport("user32.dll")]
public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

[DllImport("user32.dll")]
public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
'@
    
    $Win32 = Add-Type -MemberDefinition $sig -Name Win32 -PassThru
    
    # Activate the window
    $Win32::SetForegroundWindow($hwnd) | Out-Null
    $Win32::ShowWindow($hwnd, 5) | Out-Null
    
    Start-Sleep -Milliseconds 500
    
    # Send Ctrl+S first to ensure focus
    [System.Windows.Forms.SendKeys]::SendWait("^s")
    Start-Sleep -Seconds 1
    
    Write-Host "Save triggered"
}
