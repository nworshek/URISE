"""
Manual BIOPAC Sync GUI

Purpose:
- Shows one large SYNC NOW button.
- When clicked, it can automatically click a fixed BIOPAC screen position.
- Then it sends a GO command to the Arduino over serial.
- Designed for a dedicated Windows lab laptop where COM port and BIOPAC coordinates stay consistent.

Required installs:
    pip install pyserial pyautogui

Before running:
1. Update SERIAL_PORT to match the Arduino COM port, for example COM3 or COM4.
2. Use mouse_position_tracker.py to find the BIOPAC record/start button coordinates.
3. Update BIOPAC_CLICK_X and BIOPAC_CLICK_Y.
4. Keep BIOPAC in the same window position during testing.
"""

import tkinter as tk
from tkinter import messagebox
import serial
import time
from datetime import datetime
import pyautogui

# ===================== USER SETTINGS =====================

# Windows Arduino serial port. Change this to the lab laptop's COM port.
# Examples: "COM3", "COM4", "COM5"
SERIAL_PORT = "COM4"
BAUD_RATE = 115200

# Command sent to Arduino firmware.
SYNC_COMMAND = "GO"

# BIOPAC button position. Use mouse_position_tracker.py to find these values.
BIOPAC_CLICK_X = 850
BIOPAC_CLICK_Y = 420

# Set to True if you want Python to click BIOPAC before sending GO.
# Set to False if you only want to send the Arduino trigger.
ENABLE_BIOPAC_CLICK = True

# Delay after clicking BIOPAC and before sending GO to Arduino.
# Increase slightly if BIOPAC needs time to begin recording.
DELAY_AFTER_BIOPAC_CLICK_S = 0.5

# Optional safety: moving mouse to top-left corner aborts pyautogui actions.
pyautogui.FAILSAFE = True

# =========================================================


class ManualSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("BIOPAC Manual Sync")
        self.root.geometry("460x300")
        self.root.resizable(False, False)

        self.arduino = None

        title = tk.Label(
            root,
            text="BIOPAC Manual Sync",
            font=("Arial", 22, "bold")
        )
        title.pack(pady=(25, 8))

        self.status_label = tk.Label(
            root,
            text="Serial: Disconnected",
            fg="red",
            font=("Arial", 11, "bold")
        )
        self.status_label.pack(pady=4)

        self.coordinate_label = tk.Label(
            root,
            text=f"BIOPAC click: X={BIOPAC_CLICK_X}, Y={BIOPAC_CLICK_Y}",
            font=("Arial", 10)
        )
        self.coordinate_label.pack(pady=2)

        self.sync_button = tk.Button(
            root,
            text="SYNC NOW",
            font=("Arial", 22, "bold"),
            width=16,
            height=2,
            command=self.sync_now,
            bg="#2f7df6",
            fg="white",
            activebackground="#1e5fc0",
            activeforeground="white"
        )
        self.sync_button.pack(pady=22)

        self.log_label = tk.Label(
            root,
            text="Last sync: none",
            font=("Arial", 10)
        )
        self.log_label.pack(pady=4)

        self.note_label = tk.Label(
            root,
            text="Failsafe: move mouse to top-left corner to abort PyAutoGUI.",
            font=("Arial", 9),
            fg="gray"
        )
        self.note_label.pack(pady=(8, 0))

        self.connect_serial()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def connect_serial(self):
        try:
            self.arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Arduino resets when serial opens
            self.status_label.config(text=f"Serial: Connected to {SERIAL_PORT}", fg="green")
            print(f"[SYSTEM] Connected to Arduino on {SERIAL_PORT} @ {BAUD_RATE}")
        except Exception as e:
            self.arduino = None
            self.status_label.config(text="Serial: Disconnected", fg="red")
            messagebox.showerror(
                "Serial Connection Error",
                f"Could not connect to Arduino on {SERIAL_PORT}.\n\n{e}"
            )

    def sync_now(self):
        if not self.arduino or not self.arduino.is_open:
            messagebox.showerror("Error", "Arduino is not connected.")
            return

        try:
            if ENABLE_BIOPAC_CLICK:
                print(f"[BIOPAC] Clicking X={BIOPAC_CLICK_X}, Y={BIOPAC_CLICK_Y}")
                pyautogui.click(BIOPAC_CLICK_X, BIOPAC_CLICK_Y)
                time.sleep(DELAY_AFTER_BIOPAC_CLICK_S)

            self.arduino.write((SYNC_COMMAND + "\n").encode())

            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.log_label.config(text=f"Last sync: {timestamp}")
            print(f"[SYNC] Sent {SYNC_COMMAND} at {timestamp}")

        except pyautogui.FailSafeException:
            messagebox.showwarning(
                "PyAutoGUI Failsafe",
                "Mouse moved to the top-left corner. Action aborted."
            )
        except Exception as e:
            messagebox.showerror("Sync Error", str(e))

    def on_close(self):
        try:
            if self.arduino and self.arduino.is_open:
                self.arduino.close()
                print("[SYSTEM] Serial connection closed")
        finally:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ManualSyncApp(root)
    root.mainloop()
