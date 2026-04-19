
# Try using Direct COM access to Power BI
try {
    # Try to access Power BI via COM
    $pbi = New-Object -ComObject "PBIDesktop.Application" -ErrorAction Stop
    Write-Host "Connected to Power BI Desktop via COM"
    
    # Try to save the file
    $pbi.ActiveWorkbook.SaveAs("c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix")
    Write-Host "File saved via COM"
}
catch {
    Write-Host "COM approach failed, trying alternative..."
    
    # Alternative: Use Process redirection
    $pbi = Get-Process PBIDesktop -ErrorAction SilentlyContinue
    if ($pbi) {
        # Get the window and try WM_COMMAND message
        Add-Type -AssemblyName System.Windows.Forms
        
        $sig = @'
        [DllImport("user32.dll")]
        public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
        
        [DllImport("user32.dll")]
        public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, IntPtr lParam);
'@
        $Win32 = Add-Type -MemberDefinition $sig -Name Win32 -PassThru
        
        # Try finding Power BI window
        $hwnd = $Win32::FindWindow("XLMAIN", $null)
        if ($hwnd -ne 0) {
            Write-Host "Found window: $hwnd"
            
            # Send File > Save As command (Alt+F, A or using menu ID)
            # This is the traditional way but requires menu IDs
        }
    }
}
