Add-Type -AssemblyName System.Windows.Forms

$pbi = Get-Process PBIDesktop -ErrorAction SilentlyContinue
if ($pbi) {
    $hwnd = $pbi.MainWindowHandle
    
    # Activate window
    $sig = "[DllImport(`"user32.dll`")] public static extern bool SetForegroundWindow(IntPtr hWnd);"
    $Win32 = Add-Type -MemberDefinition $sig -Name Win32 -PassThru
    $Win32::SetForegroundWindow($hwnd) | Out-Null
    
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("^+s")
    Start-Sleep -Seconds 2
    
    # Type filename
    $filename = "c:\TM_PBI\qa_pipeline\QA-Pipeline-Report"
    [System.Windows.Forms.SendKeys]::SendWait($filename)
    Start-Sleep -Milliseconds 500
    
    # Save
    [System.Windows.Forms.SendKeys]::SendWait("~")
    Start-Sleep -Seconds 4
    
    # Verify
    $pbixFile = Get-Item "c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix" -ErrorAction SilentlyContinue
    if ($pbixFile) {
        Write-Host "OK: File saved - $([Math]::Round($pbixFile.Length/1024,2)) KB"
    }
}
