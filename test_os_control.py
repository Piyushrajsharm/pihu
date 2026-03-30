"""
Quick test: Does Pihu actually have OS control?
This will:
1. Open Notepad
2. Wait for it
3. Type a message
"""
import subprocess
import time
import pyautogui
import pyperclip

print("=== OS Control Test ===")

# 1. Open Notepad
print("[1] Opening Notepad...")
subprocess.Popen("notepad", shell=True)
time.sleep(2)

# 2. Type using pyperclip + Ctrl+V (supports Unicode/Hindi)
print("[2] Typing text via clipboard...")
text = "Hello! Main Pihu hoon. Yeh OS control test hai! 🎉"
pyperclip.copy(text)
pyautogui.hotkey("ctrl", "v")
time.sleep(0.5)

# 3. Press Enter and type more
pyautogui.press("enter")
time.sleep(0.3)
text2 = "Agar yeh dikh raha hai toh OS control kaam kar raha hai!"
pyperclip.copy(text2)
pyautogui.hotkey("ctrl", "v")

print("[3] Done! Check if Notepad has the text.")
print("=== Test Complete ===")
