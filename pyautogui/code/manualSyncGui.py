"""
Manual BIOPAC Sync GUI
"""

import tkinter as tk
from tkinter import messagebox
import serial
import time
from datetime import datetime
import pyautogui

# ===================== USER SETTINGS =====================

SERIAL_PORT = "COM4"
BAUD_RATE = 115200

SYNC_COMMAND = "1"
STOP_COMMAND = "0"

BIOPAC_CLICK_X = 82
BIOPAC_CLICK_Y = 145

ENABLE_BIOPAC_CLICK = True
DELAY_AFTER_BIOPAC_CLICK_S = 0.5

pyautogui.FAILSAFE = True

# =========================================================


class ManualSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("BIOPAC Manual Sync")
        self.root.geometry("520x300")
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

        button_frame = tk.Frame(root)
        button_frame.pack(pady=22)

        self.sync_button = tk.Button(
            button_frame,
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
        self.sync_button.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_button = tk.Button(
            button_frame,
            text="STOP",
            font=("Arial", 12, "bold"),
            width=7,
            height=1,
            command=self.stop_motors,
            bg="#d9534f",
            fg="white",
            activebackground="#b52b27",
            activeforeground="white"
        )
        self.stop_button.pack(side=tk.LEFT)

        self.log_label = tk.Label(
            root,
            text="Last action: none",
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
            time.sleep(2)
            self.status_label.config(
                text=f"Serial: Connected to {SERIAL_PORT}",
                fg="green"
            )
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
            self.log_label.config(text=f"Last action: SYNC at {timestamp}")
            print(f"[SYNC] Sent {SYNC_COMMAND} at {timestamp}")

        except pyautogui.FailSafeException:
            messagebox.showwarning(
                "PyAutoGUI Failsafe",
                "Mouse moved to the top-left corner. Action aborted."
            )
        except Exception as e:
            messagebox.showerror("Sync Error", str(e))

    def stop_motors(self):
        if not self.arduino or not self.arduino.is_open:
            messagebox.showerror("Error", "Arduino is not connected.")
            return

        try:
            self.arduino.write((STOP_COMMAND + "\n").encode())

            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.log_label.config(text=f"Last action: STOP at {timestamp}")
            print(f"[STOP] Sent {STOP_COMMAND} at {timestamp}")

        except Exception as e:
            messagebox.showerror("Stop Error", str(e))

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