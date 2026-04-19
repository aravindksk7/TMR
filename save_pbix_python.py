import subprocess
import time
import os
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    
    # Wait for Power BI to be ready
    time.sleep(3)
    
    # Click on Power BI window to focus it
    pyautogui.click(500, 400)
    time.sleep(1)
    
    # Send Ctrl+Shift+S for Save As
    pyautogui.hotkey('ctrl', 'shift', 's')
    time.sleep(2)
    
    # Type the full path and filename
    filepath = r'c:\TM_PBI\qa_pipeline\QA-Pipeline-Report'
    pyautogui.typewrite(filepath, interval=0.05)
    time.sleep(1)
    
    # Press Enter to save
    pyautogui.press('return')
    time.sleep(3)
    
    # Verify file was created
    pbix_file = Path(r'c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix')
    if pbix_file.exists():
        size_kb = pbix_file.stat().st_size / 1024
        print(f"✓ SUCCESS: PBIX file created!")
        print(f"  Path: {pbix_file}")
        print(f"  Size: {size_kb:.2f} KB")
        if size_kb > 50:
            print(f"  ✓ File size indicates model is included")
    else:
        print("✗ File not created")
        
except ImportError:
    print("pyautogui not installed, trying alternative method...")
    # Fallback to PowerShell method
    subprocess.run(['powershell', '-Command', '''
    Add-Type -AssemblyName System.Windows.Forms
    $pbi = Get-Process PBIDesktop
    if ($pbi) {
        $hwnd = $pbi.MainWindowHandle
        $sig = "[DllImport(\\"user32.dll\\")] public static extern bool SetForegroundWindow(IntPtr hWnd);"
        $WinAPI = Add-Type -MemberDefinition $sig -Name WinEvent -PassThru
        $WinAPI::SetForegroundWindow($hwnd) | Out-Null
        Start-Sleep -Milliseconds 300
        
        # Ctrl+Shift+S
        [System.Windows.Forms.SendKeys]::SendWait("^+s")
        Start-Sleep -Seconds 2
        
        # Type filename with backslashes as forward slashes for the dialog
        [System.Windows.Forms.SendKeys]::SendWait("c:/TM_PBI/qa_pipeline/QA-Pipeline-Report")
        Start-Sleep -Milliseconds 500
        
        # Press Enter
        [System.Windows.Forms.SendKeys]::SendWait("~")
        Start-Sleep -Seconds 3
        
        Write-Host "Save command executed"
    }
    '''])
except Exception as e:
    print(f"Error: {e}")
