"""
BIOPAC Trigger-Only Controller

Purpose:
- Standalone Python GUI for sending event triggers to an Arduino.
- Arduino sends TTL pulses to BIOPAC.
- Optional PyAutoGUI controls for clicking BIOPAC/video software or pressing hotkeys.

Recommended workflow:
1. Upload biopac_trigger_only_firmware.ino to Arduino.
2. Connect Arduino D7 to BIOPAC trigger/event input.
3. Connect Arduino GND to BIOPAC ground.
4. Run this Python GUI.
5. Connect to Arduino serial port.
6. Use trigger buttons or Start Full Trial.

Install dependencies:
    python -m pip install pyserial pyautogui pyobjc-core pyobjc
"""

import csv
import threading
import queue
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import serial
import serial.tools.list_ports

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False


class BiopacTriggerOnlyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("BIOPAC Trigger-Only Controller")
        self.root.geometry("980x650")
        self.root.minsize(900, 600)

        self.serial_conn = None
        self.reader_running = False
        self.reader_thread = None
        self.rx_queue = queue.Queue()

        self.event_rows = []
        self.trial_running = False
        self.trial_id = None
        self.trial_start_time = None

        self.build_ui()
        self.refresh_ports()
        self.root.after(100, self.process_rx_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI ----------------

    def build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="BIOPAC Trigger-Only Controller", font=("Arial", 20, "bold"))
        title.pack(anchor="w", pady=(0, 4))

        subtitle = ttk.Label(
            outer,
            text="Python GUI → Arduino serial command → TTL pulse to BIOPAC. Optional mouse/keyboard control for BIOPAC and video software.",
            font=("Arial", 10),
        )
        subtitle.pack(anchor="w", pady=(0, 12))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        self.tab_setup = ttk.Frame(notebook, padding=12)
        self.tab_trial = ttk.Frame(notebook, padding=12)
        self.tab_automation = ttk.Frame(notebook, padding=12)
        self.tab_log = ttk.Frame(notebook, padding=12)

        notebook.add(self.tab_setup, text="1. Arduino Setup")
        notebook.add(self.tab_trial, text="2. Trigger Trial")
        notebook.add(self.tab_automation, text="3. Mouse/Keyboard Control")
        notebook.add(self.tab_log, text="4. Event Log")

        self.build_setup_tab()
        self.build_trial_tab()
        self.build_automation_tab()
        self.build_log_tab()

    def build_setup_tab(self):
        frame = ttk.LabelFrame(self.tab_setup, text="Arduino Serial Connection", padding=12)
        frame.pack(fill="x", pady=(0, 12))

        ttk.Label(frame, text="Port").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=6)
        self.port_combo = ttk.Combobox(frame, state="readonly", width=30)
        self.port_combo.grid(row=0, column=1, sticky="w", pady=6)

        ttk.Button(frame, text="Refresh Ports", command=self.refresh_ports).grid(row=0, column=2, padx=8, pady=6)

        ttk.Label(frame, text="Baud").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=6)
        self.baud_var = tk.StringVar(value="115200")
        ttk.Entry(frame, textvariable=self.baud_var, width=14).grid(row=1, column=1, sticky="w", pady=6)

        self.connection_label = ttk.Label(frame, text="Disconnected")
        self.connection_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=10)

        ttk.Button(frame, text="Connect", command=self.connect_serial).grid(row=2, column=2, padx=8, pady=6)
        ttk.Button(frame, text="Disconnect", command=self.disconnect_serial).grid(row=2, column=3, padx=8, pady=6)
        ttk.Button(frame, text="Send PING", command=lambda: self.send_command("PING", event_name="PING")).grid(row=3, column=2, padx=8, pady=6)
        ttk.Button(frame, text="Test Trigger", command=lambda: self.send_trigger("TEST_TRIGGER")).grid(row=3, column=3, padx=8, pady=6)

        wiring = ttk.LabelFrame(self.tab_setup, text="Wiring", padding=12)
        wiring.pack(fill="x")
        ttk.Label(
            wiring,
            justify="left",
            text=(
                "Arduino D7  → BIOPAC trigger/event input\n"
                "Arduino GND → BIOPAC GND\n\n"
                "Default trigger pulse: 100 ms HIGH pulse.\n"
                "Confirm BIOPAC input voltage requirements before connecting. Most Arduino Nano boards output 5 V TTL."
            ),
        ).pack(anchor="w")

    def build_trial_tab(self):
        top = ttk.LabelFrame(self.tab_trial, text="Trial Metadata", padding=12)
        top.pack(fill="x", pady=(0, 12))

        ttk.Label(top, text="Participant ID").grid(row=0, column=0, sticky="w", pady=5)
        self.participant_var = tk.StringVar(value="P001")
        ttk.Entry(top, textvariable=self.participant_var, width=24).grid(row=0, column=1, sticky="w", padx=8, pady=5)

        ttk.Label(top, text="Condition").grid(row=0, column=2, sticky="w", pady=5)
        self.condition_var = tk.StringVar(value="breathing_video")
        ttk.Entry(top, textvariable=self.condition_var, width=28).grid(row=0, column=3, sticky="w", padx=8, pady=5)

        ttk.Label(top, text="Notes").grid(row=1, column=0, sticky="nw", pady=5)
        self.notes_text = tk.Text(top, height=4, width=70)
        self.notes_text.grid(row=1, column=1, columnspan=3, sticky="we", padx=8, pady=5)

        controls = ttk.LabelFrame(self.tab_trial, text="Trigger Controls", padding=12)
        controls.pack(fill="x", pady=(0, 12))

        ttk.Button(controls, text="Start Trial", command=self.start_trial).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(controls, text="Trigger: VIDEO_START", command=lambda: self.send_trigger("VIDEO_START")).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(controls, text="Trigger: INHALE", command=lambda: self.send_trigger("INHALE")).grid(row=0, column=2, padx=6, pady=6)
        ttk.Button(controls, text="Trigger: EXHALE", command=lambda: self.send_trigger("EXHALE")).grid(row=0, column=3, padx=6, pady=6)
        ttk.Button(controls, text="Trigger: VIDEO_END", command=lambda: self.send_trigger("VIDEO_END")).grid(row=0, column=4, padx=6, pady=6)
        ttk.Button(controls, text="End Trial", command=self.end_trial).grid(row=0, column=5, padx=6, pady=6)

        self.trial_status_label = ttk.Label(self.tab_trial, text="Trial status: idle", font=("Arial", 12, "bold"))
        self.trial_status_label.pack(anchor="w", pady=(8, 4))

        quick = ttk.LabelFrame(self.tab_trial, text="Simple Full Trial", padding=12)
        quick.pack(fill="x")
        ttk.Label(
            quick,
            justify="left",
            text=(
                "Use this if the video/BIOPAC apps are already ready. It sends START_TRIAL, waits briefly, then sends VIDEO_START.\n"
                "For exact video control, use the Mouse/Keyboard Control tab."
            ),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(quick, text="Delay before VIDEO_START trigger (s)").grid(row=1, column=0, sticky="w", pady=5)
        self.video_start_delay_var = tk.StringVar(value="0.5")
        ttk.Entry(quick, textvariable=self.video_start_delay_var, width=10).grid(row=1, column=1, sticky="w", padx=8, pady=5)
        ttk.Button(quick, text="Run Simple Full Trial", command=self.run_simple_full_trial).grid(row=1, column=2, padx=8, pady=5)

    def build_automation_tab(self):
        if not PYAUTOGUI_AVAILABLE:
            warning = ttk.Label(
                self.tab_automation,
                text="PyAutoGUI is not available. Install it with: python -m pip install pyautogui pyobjc-core pyobjc",
            )
            warning.pack(anchor="w", pady=(0, 10))

        settings = ttk.LabelFrame(self.tab_automation, text="Mouse/Keyboard Settings", padding=12)
        settings.pack(fill="x", pady=(0, 12))

        ttk.Label(settings, text="BIOPAC click X,Y").grid(row=0, column=0, sticky="w", pady=5)
        self.biopac_x_var = tk.StringVar(value="")
        self.biopac_y_var = tk.StringVar(value="")
        ttk.Entry(settings, textvariable=self.biopac_x_var, width=8).grid(row=0, column=1, sticky="w", padx=(8, 2), pady=5)
        ttk.Entry(settings, textvariable=self.biopac_y_var, width=8).grid(row=0, column=2, sticky="w", padx=(2, 8), pady=5)
        ttk.Button(settings, text="Click BIOPAC Position", command=self.click_biopac_position).grid(row=0, column=3, padx=8, pady=5)

        ttk.Label(settings, text="BIOPAC hotkey").grid(row=1, column=0, sticky="w", pady=5)
        self.biopac_hotkey_var = tk.StringVar(value="space")
        ttk.Entry(settings, textvariable=self.biopac_hotkey_var, width=16).grid(row=1, column=1, columnspan=2, sticky="w", padx=8, pady=5)
        ttk.Button(settings, text="Press BIOPAC Hotkey", command=self.press_biopac_hotkey).grid(row=1, column=3, padx=8, pady=5)

        ttk.Label(settings, text="Video click X,Y").grid(row=2, column=0, sticky="w", pady=5)
        self.video_x_var = tk.StringVar(value="")
        self.video_y_var = tk.StringVar(value="")
        ttk.Entry(settings, textvariable=self.video_x_var, width=8).grid(row=2, column=1, sticky="w", padx=(8, 2), pady=5)
        ttk.Entry(settings, textvariable=self.video_y_var, width=8).grid(row=2, column=2, sticky="w", padx=(2, 8), pady=5)
        ttk.Button(settings, text="Click Video Position", command=self.click_video_position).grid(row=2, column=3, padx=8, pady=5)

        ttk.Label(settings, text="Video hotkey").grid(row=3, column=0, sticky="w", pady=5)
        self.video_hotkey_var = tk.StringVar(value="space")
        ttk.Entry(settings, textvariable=self.video_hotkey_var, width=16).grid(row=3, column=1, columnspan=2, sticky="w", padx=8, pady=5)
        ttk.Button(settings, text="Press Video Hotkey", command=self.press_video_hotkey).grid(row=3, column=3, padx=8, pady=5)

        ttk.Button(settings, text="Show Current Mouse Position", command=self.show_mouse_position).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 5))

        sequence = ttk.LabelFrame(self.tab_automation, text="Automated Start Sequence", padding=12)
        sequence.pack(fill="x")
        ttk.Label(
            sequence,
            justify="left",
            text=(
                "Sequence: start trial log → click/press BIOPAC record → click/press video play → send VIDEO_START TTL trigger.\n"
                "This is useful when BIOPAC and the breathing video must be controlled by mouse/keyboard."
            ),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(sequence, text="Delay after BIOPAC action (s)").grid(row=1, column=0, sticky="w", pady=5)
        self.after_biopac_delay_var = tk.StringVar(value="1.0")
        ttk.Entry(sequence, textvariable=self.after_biopac_delay_var, width=10).grid(row=1, column=1, sticky="w", padx=8, pady=5)

        ttk.Label(sequence, text="Delay after video action (s)").grid(row=2, column=0, sticky="w", pady=5)
        self.after_video_delay_var = tk.StringVar(value="0.1")
        ttk.Entry(sequence, textvariable=self.after_video_delay_var, width=10).grid(row=2, column=1, sticky="w", padx=8, pady=5)

        ttk.Button(sequence, text="Run Automated Start Sequence", command=self.run_automated_start_sequence).grid(row=3, column=0, sticky="w", pady=(12, 5))

    def build_log_tab(self):
        buttons = ttk.Frame(self.tab_log)
        buttons.pack(fill="x", pady=(0, 8))
        ttk.Button(buttons, text="Save Event CSV", command=self.save_event_csv).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Clear Log", command=self.clear_log).pack(side="left")

        self.log_text = tk.Text(self.tab_log, height=25, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.tab_log, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    # ---------------- Serial ----------------

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_combo.get():
            self.port_combo.current(0)
        self.append_log(f"[SYSTEM] Ports refreshed: {', '.join(ports) if ports else 'none found'}")

    def connect_serial(self):
        if self.serial_conn and self.serial_conn.is_open:
            messagebox.showinfo("Already Connected", "Arduino serial is already connected.")
            return

        port = self.port_combo.get().strip()
        if not port:
            messagebox.showerror("Connection Error", "Select an Arduino serial port first.")
            return

        try:
            baud = int(self.baud_var.get().strip())
        except ValueError:
            messagebox.showerror("Connection Error", "Baud rate must be a number.")
            return

        try:
            self.serial_conn = serial.Serial(port, baud, timeout=0.2)
            time.sleep(2.0)
            self.reader_running = True
            self.reader_thread = threading.Thread(target=self.serial_reader, daemon=True)
            self.reader_thread.start()
            self.connection_label.config(text=f"Connected: {port} @ {baud}")
            self.append_log(f"[SYSTEM] Connected to Arduino on {port} @ {baud}")
            self.send_command("PING", event_name="CONNECT_PING")
        except Exception as e:
            self.serial_conn = None
            self.connection_label.config(text="Disconnected")
            messagebox.showerror("Connection Error", str(e))

    def disconnect_serial(self):
        self.reader_running = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.serial_conn = None
        self.connection_label.config(text="Disconnected")
        self.append_log("[SYSTEM] Disconnected")

    def serial_reader(self):
        while self.reader_running and self.serial_conn:
            try:
                if self.serial_conn.in_waiting:
                    line = self.serial_conn.readline().decode(errors="ignore").strip()
                    if line:
                        self.rx_queue.put(line)
                else:
                    time.sleep(0.01)
            except Exception as e:
                self.rx_queue.put(f"ERROR:serial_reader:{e}")
                break

    def process_rx_queue(self):
        while not self.rx_queue.empty():
            line = self.rx_queue.get()
            self.append_log(f"[RX] {line}")
        self.root.after(100, self.process_rx_queue)

    def send_command(self, command, event_name=None):
        if not self.serial_conn or not self.serial_conn.is_open:
            self.append_log(f"[WARN] Cannot send while disconnected: {command}")
            messagebox.showerror("Serial Error", "Connect to the Arduino first.")
            return False

        try:
            self.serial_conn.write((command + "\n").encode())
            self.append_log(f"[TX] {command}")
            if event_name:
                self.record_event(event_name, command)
            return True
        except Exception as e:
            self.append_log(f"[ERROR] Failed to send command: {e}")
            messagebox.showerror("Serial Error", str(e))
            return False

    # ---------------- Trigger Logic ----------------

    def start_trial(self):
        if self.trial_running:
            messagebox.showwarning("Trial Running", "A trial is already running.")
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        participant = self.participant_var.get().strip() or "participant"
        self.trial_id = f"{participant}_{stamp}"
        self.trial_start_time = time.time()
        self.trial_running = True
        self.trial_status_label.config(text=f"Trial status: running | {self.trial_id}")
        self.append_log(f"[TRIAL] Started {self.trial_id}")
        self.record_event("TRIAL_START", "LOCAL_ONLY")
        self.send_trigger("TRIAL_START")

    def end_trial(self):
        if not self.trial_running:
            messagebox.showinfo("No Trial", "No active trial is running.")
            return
        self.send_trigger("TRIAL_END")
        self.record_event("TRIAL_END", "LOCAL_ONLY")
        self.append_log(f"[TRIAL] Ended {self.trial_id}")
        self.trial_running = False
        self.trial_status_label.config(text="Trial status: idle")

    def send_trigger(self, event_name):
        # Arduino firmware treats any TRIGGER:<event_name> command as a TTL pulse.
        command = f"TRIGGER:{event_name}"
        return self.send_command(command, event_name=event_name)

    def run_simple_full_trial(self):
        self.start_trial()
        try:
            delay_s = float(self.video_start_delay_var.get().strip())
        except ValueError:
            delay_s = 0.5
        self.root.after(int(delay_s * 1000), lambda: self.send_trigger("VIDEO_START"))

    # ---------------- PyAutoGUI ----------------

    def require_pyautogui(self):
        if not PYAUTOGUI_AVAILABLE:
            messagebox.showerror("PyAutoGUI Missing", "Install PyAutoGUI first: python -m pip install pyautogui pyobjc-core pyobjc")
            return False
        return True

    def show_mouse_position(self):
        if not self.require_pyautogui():
            return
        x, y = pyautogui.position()
        messagebox.showinfo("Mouse Position", f"Current mouse position:\nX={x}, Y={y}")
        self.append_log(f"[PYAUTOGUI] Mouse position X={x}, Y={y}")

    def click_xy(self, x_var, y_var, label):
        if not self.require_pyautogui():
            return False
        try:
            x = int(x_var.get().strip())
            y = int(y_var.get().strip())
        except ValueError:
            messagebox.showerror("Click Error", f"Enter numeric X,Y values for {label}.")
            return False
        pyautogui.click(x=x, y=y)
        self.append_log(f"[PYAUTOGUI] Clicked {label} at X={x}, Y={y}")
        self.record_event(f"CLICK_{label.upper()}", f"CLICK:{x},{y}")
        return True

    def press_key(self, key_var, label):
        if not self.require_pyautogui():
            return False
        key = key_var.get().strip()
        if not key:
            messagebox.showerror("Hotkey Error", f"Enter a hotkey for {label}.")
            return False
        pyautogui.press(key)
        self.append_log(f"[PYAUTOGUI] Pressed {label} hotkey: {key}")
        self.record_event(f"HOTKEY_{label.upper()}", f"HOTKEY:{key}")
        return True

    def click_biopac_position(self):
        return self.click_xy(self.biopac_x_var, self.biopac_y_var, "BIOPAC")

    def click_video_position(self):
        return self.click_xy(self.video_x_var, self.video_y_var, "VIDEO")

    def press_biopac_hotkey(self):
        return self.press_key(self.biopac_hotkey_var, "BIOPAC")

    def press_video_hotkey(self):
        return self.press_key(self.video_hotkey_var, "VIDEO")

    def run_automated_start_sequence(self):
        if not PYAUTOGUI_AVAILABLE:
            messagebox.showerror("PyAutoGUI Missing", "Install PyAutoGUI first.")
            return

        self.start_trial()

        # Prefer click if X/Y provided, otherwise use hotkey.
        if self.biopac_x_var.get().strip() and self.biopac_y_var.get().strip():
            self.click_biopac_position()
        else:
            self.press_biopac_hotkey()

        try:
            delay1 = float(self.after_biopac_delay_var.get().strip())
        except ValueError:
            delay1 = 1.0

        try:
            delay2 = float(self.after_video_delay_var.get().strip())
        except ValueError:
            delay2 = 0.1

        def video_then_trigger():
            if self.video_x_var.get().strip() and self.video_y_var.get().strip():
                self.click_video_position()
            else:
                self.press_video_hotkey()
            self.root.after(int(delay2 * 1000), lambda: self.send_trigger("VIDEO_START"))

        self.root.after(int(delay1 * 1000), video_then_trigger)

    # ---------------- Logs ----------------

    def get_notes(self):
        return self.notes_text.get("1.0", "end").strip()

    def record_event(self, event_name, command):
        now = time.time()
        row = {
            "trial_id": self.trial_id or "NO_ACTIVE_TRIAL",
            "participant_id": self.participant_var.get().strip(),
            "condition": self.condition_var.get().strip(),
            "event_name": event_name,
            "command": command,
            "pc_timestamp_epoch": now,
            "pc_timestamp_iso": datetime.now().isoformat(timespec="milliseconds"),
            "time_since_trial_start_s": (now - self.trial_start_time) if self.trial_start_time else "",
            "notes": self.get_notes(),
        }
        self.event_rows.append(row)

    def append_log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert("end", f"[{timestamp}] {text}\n")
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    def save_event_csv(self):
        if not self.event_rows:
            messagebox.showinfo("No Data", "No event rows to save yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Save event log CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"biopac_trigger_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        fieldnames = list(self.event_rows[0].keys())
        try:
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.event_rows)
            messagebox.showinfo("Saved", f"Saved event CSV:\n{path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def on_close(self):
        try:
            if self.trial_running:
                self.send_trigger("TRIAL_END")
            self.disconnect_serial()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = BiopacTriggerOnlyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
