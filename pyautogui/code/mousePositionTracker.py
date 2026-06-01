import pyautogui
import time

print("Printing mouse X/Y position every second.")
print("Press Ctrl + C to stop.\n")

try:
    while True:
        x, y = pyautogui.position()
        print(f"Mouse position: x={x}, y={y}")
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopped mouse position tracker.")