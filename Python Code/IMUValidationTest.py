import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import queue
import time
import csv
import math
import statistics
from datetime import datetime


class IMUValidationApp:
    """
    IMU-based phantom validation software.

    Main features:
    - Arduino serial connection
    - Motor selection and configuration presets
    - Pre-test checklist
    - Baseline calibration with motors off
    - Individual motor verification
    - Automatic validation sweep
    - Live IMU amplitude measurement
    - Peak/average/std-dev/time-to-peak summary metrics
    - Trial ID tracking
    - Notes field for observations
    - CSV export of raw samples and trial summaries

    Expected Arduino protocol:
    - TEST:START:M1:180:5000
    - TEST:START:M1,M3,M4:180:5000
    - TEST:STOP
    - STATUS
    - Arduino returns IMU lines as:
      IMU:<millis>,<ax>,<ay>,<az>,<gx>,<gy>,<gz>
    """

    def __init__(self, root):
        self.root = root
        self.root.title("IMU Phantom Validation Software")
        self.root.configure(bg="#202020")

        self.serial_conn = None
        self.reader_thread = None
        self.reader_running = False
        self.rx_queue = queue.Queue()

        self.motor_count = 4
        self.motor_vars = {i: tk.BooleanVar(value=False) for i in range(1, self.motor_count + 1)}
        self.motor_status_labels = {}
        self.last_status = {i: "OFF" for i in range(1, self.motor_count + 1)}

        self.is_test_running = False
        self.current_mode = "idle"  # idle, baseline, manual, verify, sweep
        self.active_trial_id = None
        self.trial_counter = 0
        self.test_start_time = None
        self.current_trial_metadata = {}

        self.log_rows = []
        self.trial_summaries = []
        self.current_trial_samples = []
        self.baseline_samples = []
        self.baseline_amplitude = 0.0
        self.baseline_ready = False

        # Test timing references
        self.t0 = None                  # test start time, set when a test starts
        self.t1 = None                  # test end time, set when a test ends
        self.tdelta = 0.0               # elapsed time between t0 and t1
        self.current_sample_count = 0

        # Cycle control references
        self.cycle_count = 1              # total cycles requested for a trial
        self.current_cycle = 0            # current cycle number during active trial
        self.cycle_force_stop = False     # true when user cancels/stops before all cycles finish
        self.base_intensity = 0           # starting intensity for cycle tests
        self.intensity_step = 0           # amount added to intensity each cycle
        self.current_cycle_intensity = 0  # actual PWM intensity used by the active cycle

        self.amp_history = []
        self.amp_window_size = 10

        self.pending_after_ids = []
        self.sweep_running = False
        self.sweep_plan = []
        self.sweep_index = 0

        self.build_ui()
        self.refresh_ports()
        self.root.after(100, self.process_incoming_messages)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())

    # ---------------- UI ----------------

    def build_ui(self):
        title = tk.Label(
            self.root,
            text="IMU Phantom Validation Software",
            bg="#202020",
            fg="white",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=(12, 4))

        subtitle = tk.Label(
            self.root,
            text="Motor intensity, phantom-pattern, and vibration-amplitude validation",
            bg="#202020",
            fg="#cfcfcf",
            font=("Arial", 10)
        )
        subtitle.pack(pady=(0, 10))

        top = tk.Frame(self.root, bg="#202020")
        top.pack(fill="x", padx=12)
        self.build_connection_frame(top)
        self.build_test_settings_frame(top)
        self.build_checklist_frame(top)

        middle = tk.Frame(self.root, bg="#202020")
        middle.pack(fill="both", expand=True, padx=12, pady=10)
        self.build_motor_selection_frame(middle)
        self.build_configurations_frame(middle)
        self.build_automation_frame(middle)

        bottom = tk.Frame(self.root, bg="#202020")
        bottom.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.build_status_frame(bottom)
        self.build_realtime_frame(bottom)
        self.build_log_frame(bottom)

    def build_connection_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Arduino / IMU Connection", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(frame, text="Serial Port", bg="#202020", fg="white").grid(row=0, column=0, sticky="w", pady=3)
        self.port_combo = ttk.Combobox(frame, state="readonly", width=20)
        self.port_combo.grid(row=0, column=1, padx=6, pady=3)
        tk.Button(frame, text="Refresh", width=10, command=self.refresh_ports).grid(row=0, column=2, padx=4, pady=3)

        tk.Label(frame, text="Baud Rate", bg="#202020", fg="white").grid(row=1, column=0, sticky="w", pady=3)
        self.baud_var = tk.StringVar(value="115200")
        tk.Entry(frame, textvariable=self.baud_var, width=12).grid(row=1, column=1, sticky="w", padx=6, pady=3)

        self.connection_status = tk.Label(frame, text="Disconnected", bg="#202020", fg="red", font=("Arial", 10, "bold"))
        self.connection_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 4))

        tk.Button(frame, text="Connect", width=12, command=self.connect_serial).grid(row=2, column=2, padx=4, pady=3)
        tk.Button(frame, text="Disconnect", width=12, command=self.disconnect_serial).grid(row=3, column=2, padx=4, pady=3)
        tk.Button(frame, text="Get Status", width=12, command=lambda: self.send_command("STATUS")).grid(row=4, column=2, padx=4, pady=3)

    def build_test_settings_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Test Settings", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 8))

        tk.Label(frame, text="Intensity (0-255)", bg="#202020", fg="white").grid(row=0, column=0, sticky="w", pady=3)
        self.intensity_var = tk.StringVar(value="180")
        tk.Entry(frame, textvariable=self.intensity_var, width=12).grid(row=0, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Duration per Cycle (ms)", bg="#202020", fg="white").grid(row=1, column=0, sticky="w", pady=3)
        self.duration_var = tk.StringVar(value="5000")
        tk.Entry(frame, textvariable=self.duration_var, width=12).grid(row=1, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Cycles", bg="#202020", fg="white").grid(row=2, column=0, sticky="w", pady=3)
        self.cycle_count_var = tk.StringVar(value="1")
        tk.Entry(frame, textvariable=self.cycle_count_var, width=12).grid(row=2, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Intensity Change / Cycle", bg="#202020", fg="white").grid(row=3, column=0, sticky="w", pady=3)
        self.intensity_step_var = tk.StringVar(value="0")
        tk.Entry(frame, textvariable=self.intensity_step_var, width=12).grid(row=3, column=1, sticky="w", padx=6, pady=3)
        tk.Label(frame, text="Use + to increase, - to decrease", bg="#202020", fg="#cfcfcf", font=("Arial", 8)).grid(row=3, column=2, sticky="w", pady=3)

        tk.Label(frame, text="Test Name", bg="#202020", fg="white").grid(row=4, column=0, sticky="w", pady=3)
        self.test_name_var = tk.StringVar(value="phantom_validation_run")
        tk.Entry(frame, textvariable=self.test_name_var, width=24).grid(row=4, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Trial Notes", bg="#202020", fg="white").grid(row=5, column=0, sticky="nw", pady=3)
        self.notes_text = tk.Text(frame, width=30, height=4, bg="#111111", fg="white", insertbackground="white")
        self.notes_text.grid(row=5, column=1, columnspan=2, sticky="w", padx=6, pady=3)

        tk.Button(frame, text="Start Test", width=12, command=self.start_manual_test).grid(row=6, column=0, pady=(10, 4))
        tk.Button(frame, text="Stop Test", width=12, command=self.stop_test).grid(row=6, column=1, pady=(10, 4), sticky="w")
        tk.Button(frame, text="Save Logs", width=12, command=self.save_logs).grid(row=6, column=2, pady=(10, 4))

        self.run_status = tk.Label(frame, text="Idle", bg="#202020", fg="#ffcc00", font=("Arial", 10, "bold"))
        self.run_status.grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def build_checklist_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Pre-Test Checklist", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.check_vars = {
            "IMU detected / no MPU error": tk.BooleanVar(value=False),
            "Serial connected": tk.BooleanVar(value=False),
            "Motor power connected": tk.BooleanVar(value=False),
            "Shared ground confirmed": tk.BooleanVar(value=False),
            "Motor driver/transistor connected": tk.BooleanVar(value=False),
            "CSV logging ready": tk.BooleanVar(value=False),
        }

        for idx, (label, var) in enumerate(self.check_vars.items()):
            cb = tk.Checkbutton(
                frame,
                text=label,
                variable=var,
                bg="#202020",
                fg="white",
                selectcolor="#202020",
                activebackground="#202020",
                activeforeground="white"
            )
            cb.grid(row=idx, column=0, sticky="w", pady=1)

        tk.Button(frame, text="Mark Manual Items Ready", command=self.mark_manual_checklist_ready).grid(row=6, column=0, sticky="w", pady=(8, 3))
        self.checklist_status = tk.Label(frame, text="Checklist incomplete", bg="#202020", fg="orange", font=("Arial", 10, "bold"))
        self.checklist_status.grid(row=7, column=0, sticky="w")

    def build_motor_selection_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Motor Selection / Pre-Test Arm State", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        for i in range(1, self.motor_count + 1):
            row = ((i - 1) // 2)
            col = ((i - 1) % 2)
            card = tk.Frame(frame, bg="#2c2c2c", bd=1, relief="solid", padx=10, pady=8)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            cb = tk.Checkbutton(
                card,
                text=f"Motor {i}",
                variable=self.motor_vars[i],
                bg="#2c2c2c",
                fg="white",
                selectcolor="#2c2c2c",
                activebackground="#2c2c2c",
                activeforeground="white",
                command=self.update_pretest_display,
                font=("Arial", 11, "bold")
            )
            cb.pack(anchor="w")

            status = tk.Label(card, text="ARMED: NO", bg="#2c2c2c", fg="red", font=("Arial", 10, "bold"))
            status.pack(anchor="w", pady=(6, 0))
            self.motor_status_labels[i] = status

        button_row = tk.Frame(frame, bg="#202020")
        button_row.grid(row=4, column=0, columnspan=2, pady=(10, 0), sticky="w")
        tk.Button(button_row, text="Select All", width=12, command=self.select_all_motors).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Clear All", width=12, command=self.clear_all_motors).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Odd Motors", width=12, command=lambda: self.set_motor_pattern([1, 3])).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Even Motors", width=12, command=lambda: self.set_motor_pattern([2, 4])).pack(side="left")

    def build_configurations_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Quick Configurations", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 8))

        configs = [
            ("All Motors", self.select_all_motors),
            ("Left Side (1,2)", lambda: self.set_motor_pattern([1, 2])),
            ("Right Side (3,4)", lambda: self.set_motor_pattern([3, 4])),
            ("Alternating A (1,3)", lambda: self.set_motor_pattern([1, 3])),
            ("Alternating B (2,4)", lambda: self.set_motor_pattern([2, 4])),
            ("Center Pair (2,3)", lambda: self.set_motor_pattern([2, 3])),
            ("Outer Pair (1,4)", lambda: self.set_motor_pattern([1, 4])),
        ]

        for idx, (label, action) in enumerate(configs):
            tk.Button(frame, text=label, width=22, command=action).grid(row=idx, column=0, sticky="w", padx=4, pady=4)

    def build_automation_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Validation Tools", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        tk.Button(frame, text="Baseline Calibration", width=24, command=self.start_baseline_calibration).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        tk.Button(frame, text="Individual Motor Check", width=24, command=self.start_individual_motor_check).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        tk.Button(frame, text="Run Full Validation Sweep", width=24, command=self.start_full_validation_sweep).grid(row=2, column=0, sticky="w", padx=4, pady=4)
        tk.Button(frame, text="Cancel Automation", width=24, command=self.cancel_automation).grid(row=3, column=0, sticky="w", padx=4, pady=4)

        self.baseline_label = tk.Label(frame, text="Baseline: not recorded", bg="#202020", fg="orange", justify="left", wraplength=240)
        self.baseline_label.grid(row=4, column=0, sticky="w", padx=4, pady=(10, 4))

        self.sweep_status_label = tk.Label(frame, text="Sweep: idle", bg="#202020", fg="#d0d0d0", justify="left", wraplength=240)
        self.sweep_status_label.grid(row=5, column=0, sticky="w", padx=4, pady=4)

    def build_status_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Current Selection / Amplitude Data", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.pretest_label = tk.Label(frame, text="Selected for next test: None", bg="#202020", fg="#00d7ff", font=("Arial", 11, "bold"), anchor="w", justify="left")
        self.pretest_label.pack(fill="x", pady=(0, 6))

        self.live_motor_state_label = tk.Label(frame, text="Live motor state: Unknown", bg="#202020", fg="white", anchor="w", justify="left")
        self.live_motor_state_label.pack(fill="x", pady=(0, 6))

        self.trial_label = tk.Label(frame, text="Active Trial: None", bg="#202020", fg="#d0d0d0", font=("Arial", 10, "bold"), anchor="w")
        self.trial_label.pack(fill="x", pady=(0, 6))

        self.amplitude_label = tk.Label(frame, text="Amplitude: 0.000 m/s²", bg="#202020", fg="lime", font=("Arial", 16, "bold"), anchor="w")
        self.amplitude_label.pack(fill="x", pady=(8, 4))

        self.smoothed_amplitude_label = tk.Label(frame, text="Smoothed Amplitude: 0.000 m/s²", bg="#202020", fg="#00d7ff", font=("Arial", 13, "bold"), anchor="w")
        self.smoothed_amplitude_label.pack(fill="x", pady=(0, 6))

        self.corrected_amplitude_label = tk.Label(frame, text="Baseline-Corrected Amp: 0.000 m/s²", bg="#202020", fg="#ffcc00", font=("Arial", 13, "bold"), anchor="w")
        self.corrected_amplitude_label.pack(fill="x", pady=(0, 8))

        self.summary_label = tk.Label(frame, text="Last Trial Summary: None", bg="#202020", fg="#d0d0d0", anchor="w", justify="left", wraplength=500)
        self.summary_label.pack(fill="x", pady=(4, 8))

        self.last_imu_label = tk.Label(frame, text="Last IMU sample: None", bg="#202020", fg="#d0d0d0", anchor="w", justify="left", wraplength=500)
        self.last_imu_label.pack(fill="x")

        self.update_pretest_display()

    def build_realtime_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Real-Time Timing", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 8))

        self.realtime_time_label = tk.Label(
            frame,
            text="Current Time: waiting for data",
            bg="#202020",
            fg="#d0d0d0",
            anchor="w",
            justify="left",
            wraplength=430
        )
        self.realtime_time_label.pack(fill="x", pady=(0, 6))

        self.timing_label = tk.Label(
            frame,
            text="t0: not set | t1: not set | tdelta: 0.000 s",
            bg="#202020",
            fg="#00d7ff",
            font=("Arial", 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=430
        )
        self.timing_label.pack(fill="x", pady=(0, 6))

        self.realtime_summary_label = tk.Label(
            frame,
            text="Live summary: timing not active",
            bg="#202020",
            fg="white",
            anchor="w",
            justify="left",
            wraplength=430
        )
        self.realtime_summary_label.pack(fill="x")

    def build_log_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Event / IMU Log", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.log_text = tk.Text(frame, height=20, width=75, bg="#111111", fg="#f0f0f0", insertbackground="white")
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    # ---------------- Checklist ----------------

    def mark_manual_checklist_ready(self):
        for key in ["Motor power connected", "Shared ground confirmed", "Motor driver/transistor connected", "CSV logging ready"]:
            self.check_vars[key].set(True)
        self.update_checklist_status()

    def update_checklist_status(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.check_vars["Serial connected"].set(True)
        else:
            self.check_vars["Serial connected"].set(False)

        if all(var.get() for var in self.check_vars.values()):
            self.checklist_status.config(text="Checklist complete", fg="lime")
        else:
            self.checklist_status.config(text="Checklist incomplete", fg="orange")

    # ---------------- Motor Selection ----------------

    def selected_motors(self):
        return [i for i in range(1, self.motor_count + 1) if self.motor_vars[i].get()]

    def update_pretest_display(self):
        selected = self.selected_motors()
        if selected:
            selected_text = ", ".join([f"M{i}" for i in selected])
            self.pretest_label.config(text=f"Selected for next test: {selected_text}")
        else:
            self.pretest_label.config(text="Selected for next test: None")

        for i in range(1, self.motor_count + 1):
            if self.motor_vars[i].get():
                self.motor_status_labels[i].config(text="ARMED: YES", fg="lime")
            else:
                self.motor_status_labels[i].config(text="ARMED: NO", fg="red")

    def select_all_motors(self):
        for i in range(1, self.motor_count + 1):
            self.motor_vars[i].set(True)
        self.update_pretest_display()

    def clear_all_motors(self):
        for i in range(1, self.motor_count + 1):
            self.motor_vars[i].set(False)
        self.update_pretest_display()

    def set_motor_pattern(self, motors):
        for i in range(1, self.motor_count + 1):
            self.motor_vars[i].set(i in motors)
        self.update_pretest_display()

    # ---------------- Serial ----------------

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports:
            self.port_combo.current(0)

    def connect_serial(self):
        if self.serial_conn and self.serial_conn.is_open:
            messagebox.showinfo("Info", "Already connected")
            return

        port = self.port_combo.get().strip()
        if not port:
            messagebox.showerror("Error", "Select a serial port first")
            return

        try:
            baud = int(self.baud_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Baud rate must be a number")
            return

        try:
            self.serial_conn = serial.Serial(port, baud, timeout=0.2)
            time.sleep(2)
            self.reader_running = True
            self.reader_thread = threading.Thread(target=self.serial_reader, daemon=True)
            self.reader_thread.start()
            self.connection_status.config(text=f"Connected: {port}", fg="lime")
            self.append_log(f"[SYSTEM] Connected to {port} @ {baud}")
            self.send_command("PING")
            self.send_command("STATUS")
            self.update_checklist_status()
        except Exception as e:
            self.serial_conn = None
            self.update_checklist_status()
            messagebox.showerror("Connection Error", str(e))

    def disconnect_serial(self):
        self.reader_running = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.serial_conn = None
        self.connection_status.config(text="Disconnected", fg="red")
        self.append_log("[SYSTEM] Disconnected")
        self.update_checklist_status()

    def send_command(self, cmd):
        if not self.serial_conn or not self.serial_conn.is_open:
            self.append_log(f"[WARN] Cannot send command while disconnected: {cmd}")
            return False
        try:
            self.serial_conn.write((cmd + "\n").encode())
            self.append_log(f"[TX] {cmd}")
            return True
        except Exception as e:
            self.append_log(f"[ERROR] Failed to send command: {e}")
            return False

    def serial_reader(self):
        while self.reader_running and self.serial_conn:
            try:
                if self.serial_conn.in_waiting:
                    raw = self.serial_conn.readline().decode(errors="ignore").strip()
                    if raw:
                        self.rx_queue.put(raw)
                else:
                    time.sleep(0.02)
            except Exception as e:
                self.rx_queue.put(f"ERROR:Serial reader failure: {e}")
                break

    # ---------------- Validation Helpers ----------------

    def validate_test_inputs(self, require_motor=True):
        motors = self.selected_motors()
        if require_motor and not motors:
            messagebox.showerror("Error", "Select at least one motor before starting a test")
            return None

        try:
            intensity = int(self.intensity_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Intensity must be an integer")
            return None

        try:
            duration_ms = int(self.duration_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Duration must be an integer in milliseconds")
            return None

        try:
            cycle_count = int(self.cycle_count_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Cycles must be an integer")
            return None

        try:
            intensity_step = int(self.intensity_step_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Intensity Change / Cycle must be an integer. Use positive numbers to increase or negative numbers to decrease.")
            return None

        if not (0 <= intensity <= 255):
            messagebox.showerror("Error", "Intensity must be between 0 and 255")
            return None
        if duration_ms <= 0:
            messagebox.showerror("Error", "Duration per cycle must be greater than 0")
            return None
        if cycle_count <= 0:
            messagebox.showerror("Error", "Cycles must be 1 or greater")
            return None
        if not self.serial_conn or not self.serial_conn.is_open:
            messagebox.showerror("Error", "Connect to the Arduino first")
            return None

        return motors, intensity, duration_ms, cycle_count, intensity_step

    def new_trial_id(self, prefix="TRIAL"):
        self.trial_counter += 1
        return f"{prefix}_{self.trial_counter:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def get_notes(self):
        return self.notes_text.get("1.0", "end").strip()

    # ---------------- Manual Test ----------------

    def start_manual_test(self):
        validated = self.validate_test_inputs(require_motor=True)
        if not validated:
            return
        motors, intensity, duration_ms, cycle_count, intensity_step = validated
        self.start_trial(motors, intensity, duration_ms, mode="manual", label="Manual Test", cycle_count=cycle_count, intensity_step=intensity_step)

    def start_trial(self, motors, intensity, duration_ms, mode, label, auto_next_callback=None, cycle_count=None, intensity_step=None):
        if self.is_test_running:
            messagebox.showerror("Error", "A test is already running")
            return False

        if cycle_count is None:
            try:
                cycle_count = int(self.cycle_count_var.get().strip())
            except Exception:
                cycle_count = 1
        if cycle_count < 1:
            cycle_count = 1

        if intensity_step is None:
            try:
                intensity_step = int(self.intensity_step_var.get().strip())
            except Exception:
                intensity_step = 0

        motor_string = ",".join([f"M{i}" for i in motors])
        current_cycle_intensity = self.clamp_intensity(intensity)
        command = f"TEST:START:{motor_string}:{current_cycle_intensity}:{duration_ms}"

        self.active_trial_id = self.new_trial_id(label.replace(" ", "_").upper())
        self.current_mode = mode
        self.current_trial_samples = []
        self.amp_history = []
        self.t0 = time.time()
        self.t1 = None
        self.tdelta = 0.0
        self.current_sample_count = 0
        self.test_start_time = self.t0
        self.is_test_running = True

        self.cycle_count = cycle_count
        self.current_cycle = 1
        self.cycle_force_stop = False
        self.base_intensity = self.clamp_intensity(intensity)
        self.intensity_step = intensity_step
        self.current_cycle_intensity = current_cycle_intensity

        self.current_trial_metadata = {
            "trial_id": self.active_trial_id,
            "test_name": self.test_name_var.get().strip(),
            "mode": mode,
            "label": label,
            "selected_motors": motor_string,
            "base_intensity": self.base_intensity,
            "intensity": self.current_cycle_intensity,
            "intensity_step_per_cycle": self.intensity_step,
            "duration_ms": duration_ms,
            "cycle_count": self.cycle_count,
            "notes": self.get_notes(),
            "t0": datetime.fromtimestamp(self.t0).isoformat(timespec="milliseconds") if self.t0 else "",
            "t1": "",
            "tdelta_s": "",
            "auto_next_callback": auto_next_callback,
            "cycle_command": command,
        }

        self.run_status.config(text=f"Running: {label} | Cycle {self.current_cycle}/{self.cycle_count} | Intensity {self.current_cycle_intensity}", fg="lime")
        self.trial_label.config(text=f"Active Trial: {self.active_trial_id}")
        self.append_log(f"[TEST] Starting {label}")
        self.append_log(f"[TEST] Trial ID: {self.active_trial_id}")
        self.append_log(f"[TEST] Motors selected before start: {motor_string}")
        self.append_log(f"[TEST] Starting intensity: {self.base_intensity}")
        self.append_log(f"[TEST] Intensity change per cycle: {self.intensity_step}")
        self.append_log(f"[TEST] Duration per cycle (ms): {duration_ms}")
        self.append_log(f"[TEST] Cycles: {self.cycle_count}")
        self.append_log(f"[TEST] Test name: {self.current_trial_metadata.get('test_name', '')}")
        if self.current_trial_metadata.get("notes", ""):
            self.append_log("[TEST] Notes captured for this trial")
        self.append_log(f"[CYCLE] Starting cycle {self.current_cycle}/{self.cycle_count} at intensity {self.current_cycle_intensity}")

        self.timing_label.config(
            text=(
                f"t0: {datetime.fromtimestamp(self.t0).strftime('%H:%M:%S.%f')[:-3] if self.t0 else 'not set'} | "
                f"t1: running | "
                f"tdelta: {self.tdelta:.3f} s"
            )
        )
        self.realtime_summary_label.config(text=f"Live summary: cycle {self.current_cycle}/{self.cycle_count} running | intensity {self.current_cycle_intensity}")

        if not self.send_command(command):
            self.is_test_running = False
            self.current_mode = "idle"
            return False
        return True

    def clamp_intensity(self, value):
        try:
            value = int(value)
        except Exception:
            value = 0
        return max(0, min(255, value))

    def get_cycle_intensity(self, cycle_number):
        return self.clamp_intensity(self.base_intensity + ((cycle_number - 1) * self.intensity_step))

    def build_cycle_command(self):
        motor_string = self.current_trial_metadata.get("selected_motors", "")
        duration_ms = self.current_trial_metadata.get("duration_ms", "")
        self.current_cycle_intensity = self.get_cycle_intensity(self.current_cycle)
        self.current_trial_metadata["intensity"] = self.current_cycle_intensity
        return f"TEST:START:{motor_string}:{self.current_cycle_intensity}:{duration_ms}"

    def start_next_cycle(self):
        if not self.is_test_running or not self.current_trial_metadata:
            return

        command = self.build_cycle_command()
        label = self.current_trial_metadata.get("label", "Test")
        if not command:
            self.finish_current_trial(reason="cycle_command_missing")
            return

        self.run_status.config(text=f"Running: {label} | Cycle {self.current_cycle}/{self.cycle_count} | Intensity {self.current_cycle_intensity}", fg="lime")
        self.realtime_summary_label.config(text=f"Live summary: cycle {self.current_cycle}/{self.cycle_count} running | intensity {self.current_cycle_intensity}")
        self.append_log(f"[CYCLE] Starting cycle {self.current_cycle}/{self.cycle_count} at intensity {self.current_cycle_intensity}")

        if not self.send_command(command):
            self.finish_current_trial(reason="cycle_start_failed")

    def handle_cycle_stop(self, reason="arduino_stop_ack"):
        if self.cycle_force_stop:
            self.finish_current_trial(reason=reason)
            return

        if self.is_test_running and self.current_cycle < self.cycle_count:
            self.append_log(f"[CYCLE] Completed cycle {self.current_cycle}/{self.cycle_count}")
            self.current_cycle += 1
            after_id = self.root.after(250, self.start_next_cycle)
            self.pending_after_ids.append(after_id)
        else:
            self.finish_current_trial(reason=reason)

    def stop_test(self):
        self.cycle_force_stop = True
        self.send_command("TEST:STOP")
        self.finish_current_trial(reason="stopped_by_user")
        self.run_status.config(text="Stopped", fg="orange")
        self.append_log("[TEST] Stop requested")

    # ---------------- Baseline Calibration ----------------

    def start_baseline_calibration(self):
        if not self.serial_conn or not self.serial_conn.is_open:
            messagebox.showerror("Error", "Connect to the Arduino first")
            return
        if self.is_test_running:
            messagebox.showerror("Error", "A test is already running")
            return

        self.send_command("TEST:STOP")
        self.baseline_samples = []
        self.t0 = time.time()
        self.t1 = None
        self.tdelta = 0.0
        self.current_sample_count = 0
        self.current_mode = "baseline"
        self.active_trial_id = self.new_trial_id("BASELINE")
        self.test_start_time = self.t0
        self.is_test_running = True
        self.run_status.config(text="Recording baseline", fg="#00d7ff")
        self.trial_label.config(text=f"Active Trial: {self.active_trial_id}")
        self.append_log("[BASELINE] Recording 5-second motors-off baseline")

        after_id = self.root.after(5000, self.finish_baseline_calibration)
        self.pending_after_ids.append(after_id)

    def finish_baseline_calibration(self):
        if self.current_mode != "baseline":
            return

        self.is_test_running = False
        self.current_mode = "idle"
        self.run_status.config(text="Idle", fg="#ffcc00")

        if self.baseline_samples:
            self.baseline_amplitude = statistics.mean(self.baseline_samples)
            self.baseline_ready = True
            self.baseline_label.config(text=f"Baseline: {self.baseline_amplitude:.4f} m/s²", fg="lime")
            self.check_vars["IMU detected / no MPU error"].set(True)
            self.append_log(f"[BASELINE] Complete. Mean baseline amplitude = {self.baseline_amplitude:.4f} m/s²")
        else:
            self.baseline_ready = False
            self.baseline_label.config(text="Baseline failed: no IMU samples", fg="red")
            self.append_log("[BASELINE] Failed: no IMU samples received")

        self.active_trial_id = None
        self.trial_label.config(text="Active Trial: None")
        self.update_checklist_status()

    # ---------------- Automation ----------------

    def start_individual_motor_check(self):
        if not self.serial_conn or not self.serial_conn.is_open:
            messagebox.showerror("Error", "Connect to the Arduino first")
            return
        if self.is_test_running:
            messagebox.showerror("Error", "A test is already running")
            return

        self.sweep_plan = []
        for intensity in [80, 120, 180, 255]:
            for motor in range(1, self.motor_count + 1):
                self.sweep_plan.append({"motors": [motor], "intensity": intensity, "duration_ms": 2000, "label": f"Verify M{motor} @ {intensity}"})

        self.sweep_running = True
        self.sweep_index = 0
        self.current_mode = "verify"
        self.append_log("[VERIFY] Starting individual motor verification")
        self.run_next_sweep_trial()

    def start_full_validation_sweep(self):
        if not self.serial_conn or not self.serial_conn.is_open:
            messagebox.showerror("Error", "Connect to the Arduino first")
            return
        if self.is_test_running:
            messagebox.showerror("Error", "A test is already running")
            return

        configurations = [
            ([1], "M1"), ([2], "M2"), ([3], "M3"), ([4], "M4"),
            ([1, 2], "M1+M2"), ([2, 3], "M2+M3"), ([3, 4], "M3+M4"),
            ([1, 3], "Alternating A"), ([2, 4], "Alternating B"),
            ([1, 2], "Left Side"), ([3, 4], "Right Side"),
            ([2, 3], "Center Pair"), ([1, 4], "Outer Pair"),
            ([1, 2, 3, 4], "All Motors"),
        ]
        intensities = [80, 120, 180, 255]

        self.sweep_plan = []
        for intensity in intensities:
            for motors, label in configurations:
                self.sweep_plan.append({"motors": motors, "intensity": intensity, "duration_ms": 2500, "label": f"Sweep {label} @ {intensity}"})

        self.sweep_running = True
        self.sweep_index = 0
        self.current_mode = "sweep"
        self.append_log("[SWEEP] Starting full validation sweep")
        self.run_next_sweep_trial()

    def run_next_sweep_trial(self):
        if not self.sweep_running:
            return

        if self.sweep_index >= len(self.sweep_plan):
            self.sweep_running = False
            self.current_mode = "idle"
            self.sweep_status_label.config(text="Sweep: complete", fg="lime")
            self.run_status.config(text="Idle", fg="#ffcc00")
            self.append_log("[SWEEP] Complete")
            return

        item = self.sweep_plan[self.sweep_index]
        self.sweep_status_label.config(text=f"Sweep: {self.sweep_index + 1}/{len(self.sweep_plan)}\n{item['label']}", fg="#00d7ff")
        self.set_motor_pattern(item["motors"])
        self.start_trial(
            item["motors"],
            item["intensity"],
            item["duration_ms"],
            mode=self.current_mode,
            label=item["label"],
            auto_next_callback=self.schedule_next_sweep_trial,
            cycle_count=int(self.cycle_count_var.get().strip()) if self.cycle_count_var.get().strip().isdigit() else 1,
            intensity_step=int(self.intensity_step_var.get().strip()) if self.intensity_step_var.get().strip().lstrip("+-").isdigit() else 0
        )

    def schedule_next_sweep_trial(self):
        self.sweep_index += 1
        after_id = self.root.after(1000, self.run_next_sweep_trial)
        self.pending_after_ids.append(after_id)

    def cancel_automation(self):
        self.sweep_running = False
        self.cycle_force_stop = True
        for after_id in self.pending_after_ids:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self.pending_after_ids = []
        self.send_command("TEST:STOP")
        self.finish_current_trial(reason="automation_cancelled")
        self.current_mode = "idle"
        self.sweep_status_label.config(text="Sweep: cancelled", fg="orange")
        self.run_status.config(text="Idle", fg="#ffcc00")
        self.append_log("[SYSTEM] Automation cancelled")

    # ---------------- Incoming Message Parsing ----------------

    def process_incoming_messages(self):
        while not self.rx_queue.empty():
            line = self.rx_queue.get()
            self.handle_message(line)
        self.root.after(100, self.process_incoming_messages)

    def handle_message(self, line):
        self.append_log(f"[RX] {line}")

        if line.startswith("STATUS:"):
            self.parse_status_line(line)
        elif line.startswith("IMU:"):
            self.parse_imu_line(line)
        elif line.startswith("EVENT:"):
            self.parse_event_line(line)
        elif line.startswith("ACK:TEST_STOP"):
            self.handle_cycle_stop(reason="arduino_stop_ack")
        elif line.startswith("ACK:TEST_START"):
            self.run_status.config(text=f"Running: {self.current_trial_metadata.get('label', 'Test')}", fg="lime")
        elif line.startswith("READY") or line.startswith("FIRMWARE"):
            pass
        elif line.startswith("ERROR:"):
            self.run_status.config(text="Error", fg="red")
            if "MPU6050" in line:
                self.check_vars["IMU detected / no MPU error"].set(False)
                self.update_checklist_status()

    def parse_status_line(self, line):
        payload = line.replace("STATUS:", "", 1)
        entries = [x.strip() for x in payload.split(",") if x.strip()]
        parsed = {}

        for entry in entries:
            if "=" not in entry:
                continue
            motor_name, state = entry.split("=", 1)
            motor_name = motor_name.strip().upper().replace("M", "")
            state = state.strip().upper()
            if motor_name.isdigit():
                parsed[int(motor_name)] = state

        if parsed:
            self.last_status.update(parsed)
            state_text = ", ".join([f"M{i}={self.last_status[i]}" for i in range(1, self.motor_count + 1)])
            self.live_motor_state_label.config(text=f"Live motor state: {state_text}")

    def parse_event_line(self, line):
        parts = line.split(":")
        if len(parts) >= 3:
            motor_name = parts[1]
            state = parts[2]
            self.live_motor_state_label.config(text=f"Live motor state: {motor_name} changed to {state}")

    def parse_imu_line(self, line):
        payload = line.replace("IMU:", "", 1)
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) < 7:
            return

        try:
            timestamp_raw, ax, ay, az, gx, gy, gz = parts[:7]
            ax = float(ax)
            ay = float(ay)
            az = float(az)
            gx = float(gx)
            gy = float(gy)
            gz = float(gz)
        except ValueError:
            self.append_log("[ERROR] Could not parse IMU values")
            return

        raw_magnitude = math.sqrt(ax**2 + ay**2 + az**2)
        amplitude = abs(raw_magnitude - 9.81)

        self.amp_history.append(amplitude)
        if len(self.amp_history) > self.amp_window_size:
            self.amp_history.pop(0)

        smoothed_amplitude = sum(self.amp_history) / len(self.amp_history)
        corrected_amplitude = max(0.0, smoothed_amplitude - self.baseline_amplitude)

        now_pc = time.time()
        now_iso = datetime.now().isoformat(timespec="milliseconds")
        self.current_sample_count += 1

        if self.t0 is not None and self.t1 is None:
            self.tdelta = now_pc - self.t0

        selected = self.selected_motors()
        selected_text = ",".join([f"M{i}" for i in selected]) if selected else "None"

        self.amplitude_label.config(text=f"Amplitude: {amplitude:.3f} m/s²")
        self.smoothed_amplitude_label.config(text=f"Smoothed Amplitude: {smoothed_amplitude:.3f} m/s²")
        self.corrected_amplitude_label.config(text=f"Baseline-Corrected Amp: {corrected_amplitude:.3f} m/s²")
        self.last_imu_label.config(
            text=f"Last IMU sample: ax={ax:.2f}, ay={ay:.2f}, az={az:.2f}, gx={gx:.2f}, gy={gy:.2f}, gz={gz:.2f}"
        )

        self.realtime_time_label.config(text=f"Current Time: {now_iso}")
        self.timing_label.config(
            text=(
                f"t0: {datetime.fromtimestamp(self.t0).strftime('%H:%M:%S.%f')[:-3] if self.t0 else 'not set'} | "
                f"t1: {'running' if self.t1 is None else datetime.fromtimestamp(self.t1).strftime('%H:%M:%S.%f')[:-3]} | "
                f"tdelta: {self.tdelta:.3f} s"
            )
        )
        self.realtime_summary_label.config(
            text=(
                f"Live summary: sample #{self.current_sample_count} | "
                f"cycle={self.current_cycle}/{self.cycle_count} | "
                f"intensity={self.current_cycle_intensity} | "
                f"tdelta={self.tdelta:.3f} s"
            )
        )

        row = {
            "trial_id": self.active_trial_id or "None",
            "mode": self.current_mode,
            "test_name": self.current_trial_metadata.get("test_name", self.test_name_var.get().strip()),
            "selected_motors": selected_text,
            "base_intensity": self.current_trial_metadata.get("base_intensity", ""),
            "intensity_step_per_cycle": self.current_trial_metadata.get("intensity_step_per_cycle", ""),
            "intensity": self.current_cycle_intensity,
            "cycle_count": self.cycle_count,
            "current_cycle": self.current_cycle,
            "ax": ax,
            "ay": ay,
            "az": az,
            "gx": gx,
            "gy": gy,
            "gz": gz,
            "raw_accel_magnitude": raw_magnitude,
            "amplitude": amplitude,
        }

        self.log_rows.append(row)
        if self.is_test_running and self.current_mode != "baseline":
            self.current_trial_samples.append(row)

        if self.current_mode == "baseline" and self.is_test_running:
            self.baseline_samples.append(amplitude)

        if self.current_mode != "baseline":
            self.check_vars["IMU detected / no MPU error"].set(True)
            self.update_checklist_status()

    # ---------------- Trial Summary ----------------


    def estimate_vibration_frequency(self, samples):
        """
        Estimate vibration frequency from the amplitude signal for the completed trial.

        Method:
        - Uses the saved amplitude values from the trial.
        - Finds local amplitude peaks above an adaptive threshold.
        - Converts peak count into Hz using the total trial duration.

        Note:
        This is an estimated vibration frequency, not the IMU sampling frequency.
        """
        if not samples or len(samples) < 3 or not self.tdelta or self.tdelta <= 0:
            return 0.0, 0, "insufficient_data"

        try:
            amplitudes = [float(row.get("amplitude", 0.0)) for row in samples]
        except Exception:
            return 0.0, 0, "invalid_amplitude_data"

        if len(amplitudes) < 3:
            return 0.0, 0, "insufficient_data"

        mean_amp = statistics.mean(amplitudes)
        std_amp = statistics.stdev(amplitudes) if len(amplitudes) > 1 else 0.0

        # Adaptive threshold: only count peaks that rise above normal signal variation.
        threshold = mean_amp + (0.5 * std_amp)

        peak_count = 0
        last_peak_index = -999999

        # Basic spacing guard to avoid counting tiny noise wiggles as separate peaks.
        # This assumes the IMU sample rate is relatively stable.
        min_samples_between_peaks = 2

        for i in range(1, len(amplitudes) - 1):
            is_local_peak = amplitudes[i] > amplitudes[i - 1] and amplitudes[i] >= amplitudes[i + 1]
            is_above_threshold = amplitudes[i] > threshold
            is_spaced = (i - last_peak_index) >= min_samples_between_peaks

            if is_local_peak and is_above_threshold and is_spaced:
                peak_count += 1
                last_peak_index = i

        estimated_frequency_hz = peak_count / self.tdelta if self.tdelta > 0 else 0.0
        return estimated_frequency_hz, peak_count, "amplitude_peak_count_over_tdelta"

    def finish_current_trial(self, reason="completed"):
        if not self.is_test_running and self.current_mode not in ["manual", "verify", "sweep"]:
            return

        self.t1 = time.time()
        if self.t0 is not None:
            self.tdelta = self.t1 - self.t0

        metadata = self.current_trial_metadata.copy()
        samples = self.current_trial_samples.copy()
        callback = metadata.get("auto_next_callback")

        trial_date = datetime.fromtimestamp(self.t0).strftime("%Y-%m-%d") if self.t0 else ""
        t0_text = datetime.fromtimestamp(self.t0).strftime("%H:%M:%S.%f")[:-3] if self.t0 else ""
        t1_text = datetime.fromtimestamp(self.t1).strftime("%H:%M:%S.%f")[:-3] if self.t1 else ""

        estimated_frequency_hz, frequency_peak_count, frequency_method = self.estimate_vibration_frequency(samples)

        # Capture the latest text box values at the moment the trial finishes.
        # This fixes cases where the test name or notes were edited after pressing Start.
        final_test_name = self.test_name_var.get().strip() or metadata.get("test_name", "phantom_validation_run")
        final_notes = self.get_notes() or metadata.get("notes", "")

        if metadata:
            # Keep metadata updated so both the metadata section and summary CSV match.
            metadata["test_name"] = final_test_name
            metadata["notes"] = final_notes

            summary = {
                "trial_id": metadata.get("trial_id", self.active_trial_id),
                "test_name": final_test_name,
                "mode": metadata.get("mode", self.current_mode),
                "label": metadata.get("label", ""),
                "selected_motors": metadata.get("selected_motors", ""),
                "base_intensity": metadata.get("base_intensity", ""),
                "intensity_step_per_cycle": metadata.get("intensity_step_per_cycle", ""),
                "final_cycle_intensity": self.current_cycle_intensity,
                "duration_per_cycle_ms": metadata.get("duration_ms", ""),
                "cycle_count": metadata.get("cycle_count", self.cycle_count),
                "completed_cycles": self.current_cycle,
                "date": trial_date,
                "t0": t0_text,
                "t1": t1_text,
                "tdelta_s": self.tdelta,
                "sample_count": len(samples),
                "estimated_frequency_hz": estimated_frequency_hz,
                "frequency_peak_count": frequency_peak_count,
                "frequency_method": frequency_method,
                "completion_reason": reason,
                "notes": final_notes,
            }
            self.trial_summaries.append(summary)
            self.summary_label.config(
                text=(
                    f"Last Trial Summary:\n"
                    f"{summary['label']} | cycles={summary['completed_cycles']}/{summary['cycle_count']} | "
                    f"t0={t0_text} | t1={t1_text} | tdelta={self.tdelta:.3f}s | freq={estimated_frequency_hz:.3f} Hz"
                )
            )
            self.append_log(
                f"[SUMMARY] {summary['label']} | cycles={summary['completed_cycles']}/{summary['cycle_count']}, "
                f"t0={t0_text}, t1={t1_text}, tdelta={self.tdelta:.3f}s, estimated_frequency={estimated_frequency_hz:.3f}Hz"
            )

        self.timing_label.config(
            text=(
                f"t0: {t0_text if t0_text else 'not set'} | "
                f"t1: {t1_text if t1_text else 'not set'} | "
                f"tdelta: {self.tdelta:.3f} s"
            )
        )
        self.realtime_summary_label.config(text="Live summary: test complete")

        self.is_test_running = False
        self.current_trial_samples = []
        self.current_trial_metadata = {}
        self.active_trial_id = None
        self.trial_label.config(text="Active Trial: None")

        if self.sweep_running and callback:
            callback()
        elif not self.sweep_running:
            self.current_mode = "idle"
            self.run_status.config(text="Idle", fg="#ffcc00")

    # ---------------- Logging / Export ----------------

    def append_log(self, text):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def save_logs(self):
        if not self.log_rows and not self.trial_summaries:
            messagebox.showinfo("Info", "No log data available to save yet")
            return

        folder = filedialog.askdirectory(title="Choose folder for validation logs")
        if not folder:
            return

        base = self.test_name_var.get().strip() or "phantom_validation"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_path = f"{folder}/{base}_{stamp}_raw_imu.csv"
        summary_path = f"{folder}/{base}_{stamp}_trial_summary.csv"

        try:
            if self.log_rows:
                with open(raw_path, "w", newline="") as f:
                    metadata_fields = [
                        "trial_id",
                        "test_name",
                        "mode",
                        "label",
                        "selected_motors",
                        "base_intensity",
                        "intensity_step_per_cycle",
                        "duration_per_cycle_ms",
                        "cycle_count",
                        "completed_cycles",
                        "date",
                        "t0",
                        "t1",
                        "tdelta_s",
                        "sample_count",
                        "estimated_frequency_hz",
                        "frequency_peak_count",
                        "frequency_method",
                        "completion_reason",
                        "notes",
                    ]

                    f.write("TRIAL METADATA AND NOTES\n")
                    if self.trial_summaries:
                        metadata_writer = csv.DictWriter(f, fieldnames=metadata_fields, extrasaction="ignore")
                        metadata_writer.writeheader()
                        metadata_writer.writerows(self.trial_summaries)
                    else:
                        f.write("No completed trial metadata available yet.\n")

                    f.write("\nRAW IMU DATA\n")
                    raw_writer = csv.DictWriter(f, fieldnames=list(self.log_rows[0].keys()))
                    raw_writer.writeheader()
                    raw_writer.writerows(self.log_rows)

            if self.trial_summaries:
                with open(summary_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(self.trial_summaries[0].keys()))
                    writer.writeheader()
                    writer.writerows(self.trial_summaries)

            messagebox.showinfo("Saved", f"Saved logs:\n{raw_path}\n{summary_path}")
            self.check_vars["CSV logging ready"].set(True)
            self.update_checklist_status()
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ---------------- Cleanup ----------------

    def on_close(self):
        try:
            self.cancel_automation()
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.send_command("STOP")
                    time.sleep(0.1)
                except Exception:
                    pass
            self.disconnect_serial()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = IMUValidationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
