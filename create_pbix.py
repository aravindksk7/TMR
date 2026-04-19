#!/usr/bin/env python3
"""
Create PBIX file with Power BI semantic model using reliable UI automation
"""
import time
import subprocess
import os
from pathlib import Path

try:
    # Try to use pynput for more reliable keyboard/mouse control
    from pynput.keyboard import Controller, Key
    from pynput.mouse import Controller as MouseController
    
    keyboard = Controller()
    mouse = MouseController()
    use_pynput = True
    print("Using pynput for automation...")
except ImportError:
    use_pynput = False
    print("pynput not available, using pyautogui...")
    try:
        import pyautogui
    except ImportError:
        print("ERROR: Neither pynput nor pyautogui available. Install with:")
        print("  pip install pynput")
        print("  OR: pip install pyautogui")
        exit(1)

TARGET_PATH = r"c:\TM_PBI\qa_pipeline\QA-Pipeline-Report.pbix"
PBIX_FOLDER = r"c:\TM_PBI\qa_pipeline"

def save_pbix_with_pynput():
    """Use pynput to save PBIX"""
    time.sleep(2)  # Wait for PBI to be ready
    
    # Focus Power BI window (click somewhere in center)
    mouse.position = (500, 400)
    mouse.click()
    time.sleep(1)
    
    # Ctrl+Shift+S for Save As
    keyboard.press(Key.ctrl)
    keyboard.press(Key.shift)
    keyboard.press('s')
    keyboard.release('s')
    keyboard.release(Key.shift)
    keyboard.release(Key.ctrl)
    
    time.sleep(2)  # Wait for dialog
    
    # Type the file path
    keyboard.type(TARGET_PATH)
    time.sleep(1)
    
    # Press Enter
    keyboard.press(Key.enter)
    keyboard.release(Key.enter)
    
    time.sleep(4)  # Wait for save
    
    print("✓ Save command executed with pynput")

def save_pbix_with_pyautogui():
    """Fallback: Use pyautogui"""
    time.sleep(2)
    
    pyautogui.click(500, 400)
    time.sleep(1)
    
    pyautogui.hotkey('ctrl', 'shift', 's')
    time.sleep(2)
    
    pyautogui.typewrite(TARGET_PATH, interval=0.02)
    time.sleep(1)
    
    pyautogui.press('return')
    time.sleep(4)
    
    print("✓ Save command executed with pyautogui")

def verify_file_created():
    """Check if PBIX file was created and has proper size"""
    time.sleep(1)
    pbix_file = Path(TARGET_PATH)
    
    if pbix_file.exists():
        size_kb = pbix_file.stat().st_size / 1024
        size_mb = size_kb / 1024
        
        print(f"\n✓✓✓ SUCCESS! PBIX file created:")
        print(f"  Path: {pbix_file}")
        print(f"  Size: {size_kb:.2f} KB ({size_mb:.3f} MB)")
        
        if size_kb > 300:
            print(f"  ✓ File size is GOOD - model data included!")
            return True
        else:
            print(f"  ⚠ File size seems small - might not include model")
            return False
    else:
        print(f"\n✗ File not found at: {TARGET_PATH}")
        print(f"  Checking {PBIX_FOLDER}...")
        for pbix in Path(PBIX_FOLDER).glob("*.pbix"):
            print(f"    Found: {pbix.name} ({pbix.stat().st_size/1024:.2f} KB)")
        return False

def main():
    print("=" * 60)
    print("Power BI PBIX File Creator")
    print("=" * 60)
    
    # Verify Power BI is running
    try:
        result = subprocess.run(
            ['powershell', '-Command', 'Get-Process PBIDesktop | Select-Object -First 1'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if "PBIDesktop" not in result.stdout:
            print("✗ Power BI Desktop is not running!")
            print("Please start Power BI Desktop manually first.")
            exit(1)
        else:
            print("✓ Power BI Desktop is running")
    except Exception as e:
        print(f"⚠ Could not verify PBI: {e}")
    
    print("\nStarting save automation...")
    try:
        if use_pynput:
            save_pbix_with_pynput()
        else:
            save_pbix_with_pyautogui()
        
        # Verify
        success = verify_file_created()
        
        if success:
            print("\n" + "=" * 60)
            print("READY TO USE!")
            print("=" * 60)
            print(f"Your PBIX file is ready: {TARGET_PATH}")
            print("\nYou can now:")
            print("  1. Open the file in Power BI Desktop")
            print("  2. Refresh data (Home → Refresh)")
            print("  3. Start building report pages")
        else:
            print("\n⚠ File creation may have failed or file is empty")
            print("Please see MANUAL_PBIX_CREATION.md for manual steps")
            
    except Exception as e:
        print(f"✗ Error during automation: {e}")
        print("\nFallback: Follow MANUAL_PBIX_CREATION.md for manual steps")

if __name__ == "__main__":
    main()
