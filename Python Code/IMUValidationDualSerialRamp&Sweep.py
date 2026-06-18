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


class DualSerialIMUValidationApp:
    """
    Dual-serial IMU validation software.

    Purpose:
    - Serial port 1 controls the motor microcontroller.
    - Serial port 2 reads data from the IMU sensor microcontroller.
    - Supports 5 separate 9-axis IMU sensors.
    - Each IMU sample contains 45 sensor values:
        5 sensors x (ax, ay, az, gx, gy, gz, mx, my, mz)

    Recommended IMU serial format from IMU microcontroller:
        IMU9:<45 comma-separated values>

    Optional supported format with timestamp:
        IMU9:<imu_timestamp>,<45 comma-separated values>

    Example:
        IMU9:0.01,0.02,9.81,0.1,0.2,0.3,12.1,8.4,34.2,... total 45 values

    Motor serial commands sent to motor microcontroller:
        TEST:START:M1:180:5000
        TEST:START:M1,M3,M4:180:5000
        TEST:STOP
        STATUS
    """

    SENSOR_COUNT = 5
    AXES = ["ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz"]

    def __init__(self, root):
        self.root = root
        self.root.title("Dual Serial IMU Phantom Validation Software")
        self.root.configure(bg="#202020")

        # Serial connections
        self.motor_serial = None
        self.imu_serial = None

        self.motor_reader_running = False
        self.imu_reader_running = False

        self.motor_reader_thread = None
        self.imu_reader_thread = None

        self.motor_queue = queue.Queue()
        self.imu_queue = queue.Queue()

        # Motor state
        self.motor_count = 4
        self.motor_vars = {i: tk.BooleanVar(value=False) for i in range(1, self.motor_count + 1)}
        self.motor_status_labels = {}
        self.last_status = {i: "OFF" for i in range(1, self.motor_count + 1)}

        # Trial state
        self.is_test_running = False
        self.current_mode = "idle"
        self.active_trial_id = None
        self.trial_counter = 0

        self.t0 = None
        self.t1 = None
        self.tdelta = 0.0
        self.current_sample_count = 0

        # Cycle state
        self.cycle_count = 1
        self.current_cycle = 0
        self.cycle_force_stop = False
        self.base_intensity = 0
        self.intensity_step = 0
        self.current_cycle_intensity = 0

        # Within-cycle ramp state
        self.ramp_mode = "None"
        self.ramp_end_intensity = 0
        self.ramp_update_ms = 250
        self.ramp_active = False
        self.ramp_segments = []
        self.ramp_segment_index = 0
        self.current_ramp_segment = 0
        self.current_segment_motors = []
        self.current_motor_intensities = {i: 0 for i in range(1, self.motor_count + 1)}

        # Within-cycle motor sweep state
        self.motor_sweep_mode = "None"
        self.motor_sweep_step_ms = 500
        self.current_segment_motors = []
        self.current_motor_intensities = {i: 0 for i in range(1, self.motor_count + 1)}

        # Data storage
        self.log_rows = []
        self.trial_summaries = []
        self.current_trial_samples = []
        self.current_trial_metadata = {}

        # Frequency estimate support
        self.frequency_signal = []
        self.frequency_times = []
        self.peak_threshold_ratio = 0.30

        self.pending_after_ids = []
        self.sweep_running = False
        self.sweep_plan = []
        self.sweep_index = 0

        self.build_ui()
        self.refresh_ports()

        self.root.after(100, self.process_queues)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())

    # ---------------- UI ----------------

    def build_ui(self):
        title = tk.Label(
            self.root,
            text="Dual Serial IMU Phantom Validation Software",
            bg="#202020",
            fg="white",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=(12, 4))

        subtitle = tk.Label(
            self.root,
            text="Motor controller serial + 5-sensor 9-axis IMU serial logging",
            bg="#202020",
            fg="#cfcfcf",
            font=("Arial", 10)
        )
        subtitle.pack(pady=(0, 10))

        top = tk.Frame(self.root, bg="#202020")
        top.pack(fill="x", padx=12)

        self.build_motor_connection_frame(top)
        self.build_imu_connection_frame(top)
        self.build_test_settings_frame(top)

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

    def build_motor_connection_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Motor Controller Serial", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(frame, text="Port", bg="#202020", fg="white").grid(row=0, column=0, sticky="w", pady=3)
        self.motor_port_combo = ttk.Combobox(frame, state="readonly", width=18)
        self.motor_port_combo.grid(row=0, column=1, padx=6, pady=3)

        tk.Button(frame, text="Refresh", width=10, command=self.refresh_ports).grid(row=0, column=2, padx=4, pady=3)

        tk.Label(frame, text="Baud", bg="#202020", fg="white").grid(row=1, column=0, sticky="w", pady=3)
        self.motor_baud_var = tk.StringVar(value="115200")
        tk.Entry(frame, textvariable=self.motor_baud_var, width=12).grid(row=1, column=1, sticky="w", padx=6, pady=3)

        self.motor_connection_status = tk.Label(frame, text="Disconnected", bg="#202020", fg="red", font=("Arial", 10, "bold"))
        self.motor_connection_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 4))

        tk.Button(frame, text="Connect", width=12, command=self.connect_motor_serial).grid(row=2, column=2, padx=4, pady=3)
        tk.Button(frame, text="Disconnect", width=12, command=self.disconnect_motor_serial).grid(row=3, column=2, padx=4, pady=3)
        tk.Button(frame, text="Get Status", width=12, command=lambda: self.send_motor_command("STATUS")).grid(row=4, column=2, padx=4, pady=3)
        tk.Button(frame, text="Test Port", width=12, command=self.test_motor_serial_port).grid(row=5, column=2, padx=4, pady=3)

    def build_imu_connection_frame(self, parent):
        frame = tk.LabelFrame(parent, text="IMU Sensor Controller Serial", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 8))

        tk.Label(frame, text="Port", bg="#202020", fg="white").grid(row=0, column=0, sticky="w", pady=3)
        self.imu_port_combo = ttk.Combobox(frame, state="readonly", width=18)
        self.imu_port_combo.grid(row=0, column=1, padx=6, pady=3)

        tk.Button(frame, text="Refresh", width=10, command=self.refresh_ports).grid(row=0, column=2, padx=4, pady=3)

        tk.Label(frame, text="Baud", bg="#202020", fg="white").grid(row=1, column=0, sticky="w", pady=3)
        self.imu_baud_var = tk.StringVar(value="115200")
        tk.Entry(frame, textvariable=self.imu_baud_var, width=12).grid(row=1, column=1, sticky="w", padx=6, pady=3)

        self.imu_connection_status = tk.Label(frame, text="Disconnected", bg="#202020", fg="red", font=("Arial", 10, "bold"))
        self.imu_connection_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 4))

        tk.Button(frame, text="Connect", width=12, command=self.connect_imu_serial).grid(row=2, column=2, padx=4, pady=3)
        tk.Button(frame, text="Disconnect", width=12, command=self.disconnect_imu_serial).grid(row=3, column=2, padx=4, pady=3)
        tk.Button(frame, text="Send PING", width=12, command=lambda: self.send_imu_command("PING")).grid(row=4, column=2, padx=4, pady=3)
        tk.Button(frame, text="Test Port", width=12, command=self.test_imu_serial_port).grid(row=5, column=2, padx=4, pady=3)

    def build_test_settings_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Test Settings", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

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

        tk.Label(frame, text="Ramp Within Cycle", bg="#202020", fg="white").grid(row=4, column=0, sticky="w", pady=3)
        self.ramp_mode_var = tk.StringVar(value="None")
        self.ramp_mode_combo = ttk.Combobox(
            frame,
            textvariable=self.ramp_mode_var,
            state="readonly",
            width=14,
            values=["None", "Ramp Up", "Ramp Down", "Custom"]
        )
        self.ramp_mode_combo.grid(row=4, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Ramp End Intensity", bg="#202020", fg="white").grid(row=5, column=0, sticky="w", pady=3)
        self.ramp_end_intensity_var = tk.StringVar(value="255")
        tk.Entry(frame, textvariable=self.ramp_end_intensity_var, width=12).grid(row=5, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Ramp Step Time (ms)", bg="#202020", fg="white").grid(row=6, column=0, sticky="w", pady=3)
        self.ramp_update_ms_var = tk.StringVar(value="250")
        tk.Entry(frame, textvariable=self.ramp_update_ms_var, width=12).grid(row=6, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Motor Sweep Within Cycle", bg="#202020", fg="white").grid(row=7, column=0, sticky="w", pady=3)
        self.motor_sweep_mode_var = tk.StringVar(value="None")
        self.motor_sweep_mode_combo = ttk.Combobox(
            frame,
            textvariable=self.motor_sweep_mode_var,
            state="readonly",
            width=18,
            values=["None", "Sequential Selected", "All Single Motors", "Pairs Selected", "All Then Singles"]
        )
        self.motor_sweep_mode_combo.grid(row=7, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Motor Sweep Step (ms)", bg="#202020", fg="white").grid(row=8, column=0, sticky="w", pady=3)
        self.motor_sweep_step_ms_var = tk.StringVar(value="500")
        tk.Entry(frame, textvariable=self.motor_sweep_step_ms_var, width=12).grid(row=8, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Test Name", bg="#202020", fg="white").grid(row=9, column=0, sticky="w", pady=3)
        self.test_name_var = tk.StringVar(value="phantom_validation_run")
        tk.Entry(frame, textvariable=self.test_name_var, width=24).grid(row=9, column=1, sticky="w", padx=6, pady=3)

        tk.Label(frame, text="Trial Notes", bg="#202020", fg="white").grid(row=10, column=0, sticky="nw", pady=3)
        self.notes_text = tk.Text(frame, width=30, height=4, bg="#111111", fg="white", insertbackground="white")
        self.notes_text.grid(row=10, column=1, columnspan=2, sticky="w", padx=6, pady=3)

        tk.Button(frame, text="Start Test", width=12, command=self.start_manual_test).grid(row=11, column=0, pady=(10, 4))
        tk.Button(frame, text="Stop Test", width=12, command=self.stop_test).grid(row=11, column=1, pady=(10, 4), sticky="w")
        tk.Button(frame, text="Save Logs", width=12, command=self.save_logs).grid(row=11, column=2, pady=(10, 4))

        self.run_status = tk.Label(frame, text="Idle", bg="#202020", fg="#ffcc00", font=("Arial", 10, "bold"))
        self.run_status.grid(row=12, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def build_motor_selection_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Motor Selection / Pre-Test Arm State", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        for i in range(1, self.motor_count + 1):
            row = (i - 1) // 2
            col = (i - 1) % 2

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

        tk.Button(frame, text="Individual Motor Check", width=24, command=self.start_individual_motor_check).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        tk.Button(frame, text="Run Full Validation Sweep", width=24, command=self.start_full_validation_sweep).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        tk.Button(frame, text="Cancel Automation", width=24, command=self.cancel_automation).grid(row=2, column=0, sticky="w", padx=4, pady=4)

        self.sweep_status_label = tk.Label(frame, text="Sweep: idle", bg="#202020", fg="#d0d0d0", justify="left", wraplength=240)
        self.sweep_status_label.grid(row=3, column=0, sticky="w", padx=4, pady=(10, 4))

        self.imu_format_label = tk.Label(
            frame,
            text="IMU expected: IMU9:<45 values> or IMU9:<timestamp>,<45 values>",
            bg="#202020",
            fg="#cfcfcf",
            justify="left",
            wraplength=260
        )
        self.imu_format_label.grid(row=4, column=0, sticky="w", padx=4, pady=4)

    def build_status_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Current State / IMU Data", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.pretest_label = tk.Label(frame, text="Selected for next test: None", bg="#202020", fg="#00d7ff", font=("Arial", 11, "bold"), anchor="w", justify="left")
        self.pretest_label.pack(fill="x", pady=(0, 6))

        self.live_motor_state_label = tk.Label(frame, text="Live motor state: Unknown", bg="#202020", fg="white", anchor="w", justify="left")
        self.live_motor_state_label.pack(fill="x", pady=(0, 6))

        self.trial_label = tk.Label(frame, text="Active Trial: None", bg="#202020", fg="#d0d0d0", font=("Arial", 10, "bold"), anchor="w")
        self.trial_label.pack(fill="x", pady=(0, 6))

        self.sample_label = tk.Label(frame, text="Samples: 0", bg="#202020", fg="lime", font=("Arial", 16, "bold"), anchor="w")
        self.sample_label.pack(fill="x", pady=(8, 4))

        self.last_imu_label = tk.Label(frame, text="Last IMU sample: None", bg="#202020", fg="#d0d0d0", anchor="w", justify="left", wraplength=520)
        self.last_imu_label.pack(fill="x", pady=(4, 8))

        self.summary_label = tk.Label(frame, text="Last Trial Summary: None", bg="#202020", fg="#d0d0d0", anchor="w", justify="left", wraplength=520)
        self.summary_label.pack(fill="x", pady=(4, 8))

        self.update_pretest_display()

    def build_realtime_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Real-Time Timing", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 8))

        self.realtime_time_label = tk.Label(frame, text="Current Time: waiting for data", bg="#202020", fg="#d0d0d0", anchor="w", justify="left", wraplength=430)
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

        self.realtime_summary_label = tk.Label(frame, text="Live summary: timing not active", bg="#202020", fg="white", anchor="w", justify="left", wraplength=430)
        self.realtime_summary_label.pack(fill="x")

    def build_log_frame(self, parent):
        frame = tk.LabelFrame(parent, text="Event Log", bg="#202020", fg="white", padx=10, pady=10)
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.log_text = tk.Text(frame, height=20, width=75, bg="#111111", fg="#f0f0f0", insertbackground="white")
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    # ---------------- Port / Serial ----------------

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.motor_port_combo["values"] = ports
        self.imu_port_combo["values"] = ports

        if ports:
            if not self.motor_port_combo.get():
                self.motor_port_combo.current(0)
            if len(ports) > 1 and not self.imu_port_combo.get():
                self.imu_port_combo.current(1)
            elif not self.imu_port_combo.get():
                self.imu_port_combo.current(0)

    def connect_motor_serial(self):
        self.motor_serial = self._connect_serial(
            port_combo=self.motor_port_combo,
            baud_var=self.motor_baud_var,
            status_label=self.motor_connection_status,
            label="MOTOR",
            queue_target=self.motor_queue,
            running_attr="motor_reader_running",
            thread_attr="motor_reader_thread"
        )
        if self.motor_serial:
            self.send_motor_command("PING")
            self.send_motor_command("STATUS")

    def connect_imu_serial(self):
        self.imu_serial = self._connect_serial(
            port_combo=self.imu_port_combo,
            baud_var=self.imu_baud_var,
            status_label=self.imu_connection_status,
            label="IMU",
            queue_target=self.imu_queue,
            running_attr="imu_reader_running",
            thread_attr="imu_reader_thread"
        )
        if self.imu_serial:
            self.send_imu_command("PING")

    def _connect_serial(self, port_combo, baud_var, status_label, label, queue_target, running_attr, thread_attr):
        existing = self.motor_serial if label == "MOTOR" else self.imu_serial
        if existing and existing.is_open:
            messagebox.showinfo("Info", f"{label} serial is already connected")
            return existing

        port = port_combo.get().strip()
        if not port:
            messagebox.showerror("Error", f"Select a {label} serial port first")
            return None

        try:
            baud = int(baud_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", f"{label} baud rate must be a number")
            return None

        try:
            conn = serial.Serial(port, baud, timeout=0.2)
            time.sleep(2)

            setattr(self, running_attr, True)
            reader_thread = threading.Thread(
                target=self.serial_reader,
                args=(conn, queue_target, running_attr, label),
                daemon=True
            )
            setattr(self, thread_attr, reader_thread)
            reader_thread.start()

            status_label.config(text=f"Connected: {port}", fg="lime")
            self.append_log(f"[SYSTEM] {label} connected to {port} @ {baud}")
            return conn
        except Exception as e:
            status_label.config(text="Disconnected", fg="red")
            messagebox.showerror(f"{label} Connection Error", str(e))
            return None

    def disconnect_motor_serial(self):
        self.motor_reader_running = False
        if self.motor_serial and self.motor_serial.is_open:
            try:
                self.motor_serial.close()
            except Exception:
                pass
        self.motor_serial = None
        self.motor_connection_status.config(text="Disconnected", fg="red")
        self.append_log("[SYSTEM] MOTOR disconnected")

    def disconnect_imu_serial(self):
        self.imu_reader_running = False
        if self.imu_serial and self.imu_serial.is_open:
            try:
                self.imu_serial.close()
            except Exception:
                pass
        self.imu_serial = None
        self.imu_connection_status.config(text="Disconnected", fg="red")
        self.append_log("[SYSTEM] IMU disconnected")

    def serial_reader(self, conn, queue_target, running_attr, label):
        while getattr(self, running_attr, False) and conn:
            try:
                if conn.in_waiting:
                    raw = conn.readline().decode(errors="ignore").strip()
                    if raw:
                        queue_target.put(raw)
                else:
                    time.sleep(0.01)
            except Exception as e:
                queue_target.put(f"ERROR:{label} serial reader failure: {e}")
                break

    def send_motor_command(self, cmd):
        return self._send_command(self.motor_serial, cmd, "MOTOR")

    def send_imu_command(self, cmd):
        return self._send_command(self.imu_serial, cmd, "IMU")

    def _send_command(self, conn, cmd, label):
        if not conn or not conn.is_open:
            self.append_log(f"[WARN] Cannot send {label} command while disconnected: {cmd}")
            return False

        try:
            conn.write((cmd + "\n").encode())
            self.append_log(f"[TX:{label}] {cmd}")
            return True
        except Exception as e:
            self.append_log(f"[ERROR] Failed to send {label} command: {e}")
            return False

    def test_motor_serial_port(self):
        self._test_serial_port(
            port_combo=self.motor_port_combo,
            baud_var=self.motor_baud_var,
            active_conn=self.motor_serial,
            label="MOTOR",
            test_commands=["PING", "STATUS"]
        )

    def test_imu_serial_port(self):
        self._test_serial_port(
            port_combo=self.imu_port_combo,
            baud_var=self.imu_baud_var,
            active_conn=self.imu_serial,
            label="IMU",
            test_commands=["PING"]
        )

    def _test_serial_port(self, port_combo, baud_var, active_conn, label, test_commands):
        """
        Tests one serial port by itself.
        This does not require the other controller to be connected.
        If the port is already connected inside the app, it sends the test command through that connection.
        If it is not connected, it briefly opens the selected port, sends the command, reads any response, and closes it.
        """
        port = port_combo.get().strip()
        if not port:
            messagebox.showerror("Port Test Error", f"Select a {label} serial port first")
            return

        try:
            baud = int(baud_var.get().strip())
        except ValueError:
            messagebox.showerror("Port Test Error", f"{label} baud rate must be a number")
            return

        # If already connected through the app, use the existing connection.
        if active_conn and active_conn.is_open:
            sent = []
            for cmd in test_commands:
                try:
                    active_conn.write((cmd + "\n").encode())
                    sent.append(cmd)
                    self.append_log(f"[TEST:{label}] Sent {cmd} on already-connected port {port}")
                except Exception as e:
                    messagebox.showerror("Port Test Failed", f"{label} port is connected, but command failed:\n{e}")
                    self.append_log(f"[ERROR] {label} connected-port test failed: {e}")
                    return

            messagebox.showinfo(
                "Port Test Sent",
                f"{label} port is already connected. Sent: {', '.join(sent)}\n\nCheck the Event Log for RX responses."
            )
            return

        # Otherwise, briefly open the selected port by itself.
        try:
            test_conn = serial.Serial(port, baud, timeout=0.2)
            time.sleep(2)

            for cmd in test_commands:
                test_conn.write((cmd + "\n").encode())
                self.append_log(f"[TEST:{label}] Sent {cmd} to temporary port test on {port}")
                time.sleep(0.15)

            responses = []
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if test_conn.in_waiting:
                    raw = test_conn.readline().decode(errors="ignore").strip()
                    if raw:
                        responses.append(raw)
                        self.append_log(f"[TEST:{label}:RX] {raw}")
                else:
                    time.sleep(0.05)

            test_conn.close()

            if responses:
                messagebox.showinfo(
                    "Port Test Successful",
                    f"{label} port opened successfully: {port} @ {baud}\n\nResponse received:\n" + "\n".join(responses[:8])
                )
            else:
                messagebox.showwarning(
                    "Port Opened, No Response",
                    f"{label} port opened successfully: {port} @ {baud}, but no response was received.\n\n"
                    f"This can still mean the port works, but the device firmware may not respond to PING/STATUS."
                )
        except Exception as e:
            messagebox.showerror("Port Test Failed", f"Could not test {label} port {port}:\n{e}")
            self.append_log(f"[ERROR] {label} temporary port test failed on {port}: {e}")

    # ---------------- Motor Selection ----------------

    def selected_motors(self):
        return [i for i in range(1, self.motor_count + 1) if self.motor_vars[i].get()]

    def update_pretest_display(self):
        selected = self.selected_motors()
        selected_text = ", ".join([f"M{i}" for i in selected]) if selected else "None"
        self.pretest_label.config(text=f"Selected for next test: {selected_text}")

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

    # ---------------- Test Helpers ----------------

    def validate_test_inputs(self, require_motor=True):
        motors = self.selected_motors()
        if require_motor and not motors:
            messagebox.showerror("Error", "Select at least one motor before starting a test")
            return None

        try:
            intensity = int(self.intensity_var.get().strip())
            duration_ms = int(self.duration_var.get().strip())
            cycle_count = int(self.cycle_count_var.get().strip())
            intensity_step = int(self.intensity_step_var.get().strip())
            ramp_end_intensity = int(self.ramp_end_intensity_var.get().strip())
            ramp_update_ms = int(self.ramp_update_ms_var.get().strip())
            motor_sweep_step_ms = int(self.motor_sweep_step_ms_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Intensity, duration, cycles, intensity step, ramp end intensity, ramp step time, and motor sweep step time must be integers")
            return None

        ramp_mode = self.ramp_mode_var.get().strip() or "None"
        motor_sweep_mode = self.motor_sweep_mode_var.get().strip() or "None"

        if not (0 <= intensity <= 255):
            messagebox.showerror("Error", "Intensity must be between 0 and 255")
            return None
        if not (0 <= ramp_end_intensity <= 255):
            messagebox.showerror("Error", "Ramp end intensity must be between 0 and 255")
            return None
        if duration_ms <= 0:
            messagebox.showerror("Error", "Duration per cycle must be greater than 0")
            return None
        if cycle_count <= 0:
            messagebox.showerror("Error", "Cycles must be 1 or greater")
            return None
        if ramp_update_ms <= 0:
            messagebox.showerror("Error", "Ramp step time must be greater than 0 ms")
            return None
        if motor_sweep_step_ms <= 0:
            messagebox.showerror("Error", "Motor sweep step time must be greater than 0 ms")
            return None
        if not self.motor_serial or not self.motor_serial.is_open:
            messagebox.showerror("Error", "Connect to the motor controller first")
            return None
        if not self.imu_serial or not self.imu_serial.is_open:
            messagebox.showerror("Error", "Connect to the IMU sensor controller first")
            return None

        return motors, intensity, duration_ms, cycle_count, intensity_step, ramp_mode, ramp_end_intensity, ramp_update_ms, motor_sweep_mode, motor_sweep_step_ms

    def new_trial_id(self, prefix="TRIAL"):
        self.trial_counter += 1
        return f"{prefix}_{self.trial_counter:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def get_notes(self):
        return self.notes_text.get("1.0", "end").strip()

    def clamp_intensity(self, value):
        try:
            value = int(value)
        except Exception:
            value = 0
        return max(0, min(255, value))

    def get_cycle_intensity(self, cycle_number):
        return self.clamp_intensity(self.base_intensity + ((cycle_number - 1) * self.intensity_step))

    # ---------------- Test Start / Cycle Control ----------------

    def start_manual_test(self):
        validated = self.validate_test_inputs(require_motor=True)
        if not validated:
            return
        motors, intensity, duration_ms, cycle_count, intensity_step, ramp_mode, ramp_end_intensity, ramp_update_ms, motor_sweep_mode, motor_sweep_step_ms = validated
        self.start_trial(
            motors=motors,
            intensity=intensity,
            duration_ms=duration_ms,
            mode="manual",
            label="Manual Test",
            cycle_count=cycle_count,
            intensity_step=intensity_step,
            ramp_mode=ramp_mode,
            ramp_end_intensity=ramp_end_intensity,
            ramp_update_ms=ramp_update_ms,
            motor_sweep_mode=motor_sweep_mode,
            motor_sweep_step_ms=motor_sweep_step_ms
        )

    def start_trial(self, motors, intensity, duration_ms, mode, label, auto_next_callback=None, cycle_count=None, intensity_step=None, ramp_mode="None", ramp_end_intensity=None, ramp_update_ms=None, motor_sweep_mode="None", motor_sweep_step_ms=500):
        if self.is_test_running:
            messagebox.showerror("Error", "A test is already running")
            return False

        if cycle_count is None:
            cycle_count = 1
        if intensity_step is None:
            intensity_step = 0
        if ramp_end_intensity is None:
            ramp_end_intensity = intensity
        if ramp_update_ms is None:
            ramp_update_ms = 250
        if motor_sweep_step_ms is None:
            motor_sweep_step_ms = 500

        motor_string = ",".join([f"M{i}" for i in motors])

        self.active_trial_id = self.new_trial_id(label.replace(" ", "_").upper())
        self.current_mode = mode
        self.current_trial_samples = []
        self.frequency_signal = []
        self.frequency_times = []

        self.t0 = time.time()
        self.t1 = None
        self.tdelta = 0.0
        self.current_sample_count = 0
        self.is_test_running = True

        self.cycle_count = max(1, int(cycle_count))
        self.current_cycle = 1
        self.cycle_force_stop = False
        self.base_intensity = self.clamp_intensity(intensity)
        self.intensity_step = int(intensity_step)
        self.current_cycle_intensity = self.get_cycle_intensity(self.current_cycle)
        self.ramp_mode = ramp_mode or "None"
        self.ramp_end_intensity = self.clamp_intensity(ramp_end_intensity)
        self.ramp_update_ms = max(1, int(ramp_update_ms))
        self.ramp_active = False
        self.ramp_segments = []
        self.ramp_segment_index = 0
        self.current_ramp_segment = 0
        self.current_segment_motors = []
        self.current_motor_intensities = {i: 0 for i in range(1, self.motor_count + 1)}
        self.motor_sweep_mode = motor_sweep_mode or "None"
        self.motor_sweep_step_ms = max(1, int(motor_sweep_step_ms))
        self.current_segment_motors = []
        self.current_motor_intensities = {i: 0 for i in range(1, self.motor_count + 1)}

        self.current_trial_metadata = {
            "trial_id": self.active_trial_id,
            "test_name": self.test_name_var.get().strip(),
            "mode": mode,
            "label": label,
            "selected_motors": motor_string,
            "selected_motor_numbers": list(motors),
            "base_intensity": self.base_intensity,
            "intensity_step_per_cycle": self.intensity_step,
            "duration_ms": duration_ms,
            "cycle_count": self.cycle_count,
            "ramp_mode": self.ramp_mode,
            "ramp_start_intensity": self.base_intensity,
            "ramp_end_intensity": self.ramp_end_intensity,
            "ramp_update_ms": self.ramp_update_ms,
            "motor_sweep_mode": self.motor_sweep_mode,
            "motor_sweep_step_ms": self.motor_sweep_step_ms,
            "notes": self.get_notes(),
            "motor_port": self.motor_port_combo.get().strip(),
            "imu_port": self.imu_port_combo.get().strip(),
            "auto_next_callback": auto_next_callback,
        }

        self.run_status.config(
            text=f"Running: {label} | Cycle {self.current_cycle}/{self.cycle_count} | Intensity {self.current_cycle_intensity}",
            fg="lime"
        )
        self.trial_label.config(text=f"Active Trial: {self.active_trial_id}")

        self.append_log(f"[TEST] Starting {label}")
        self.append_log(f"[TEST] Trial ID: {self.active_trial_id}")
        self.append_log(f"[TEST] Motors: {motor_string}")
        self.append_log(f"[TEST] Duration per cycle: {duration_ms} ms")
        self.append_log(f"[TEST] Cycles: {self.cycle_count}")
        self.append_log(f"[TEST] Intensity: {self.base_intensity} step {self.intensity_step}")

        self.update_timing_labels()
        return self.start_next_cycle(send_first=True)

    def build_motor_groups_for_cycle(self, selected_motors):
        """Return the motor group sequence used inside each cycle."""
        selected = list(selected_motors) if selected_motors else []
        mode = (self.motor_sweep_mode or "None").lower()

        if not selected:
            return []
        if mode == "none":
            return [selected]
        if mode == "sequential selected":
            return [[m] for m in selected]
        if mode == "all single motors":
            return [[m] for m in range(1, self.motor_count + 1)]
        if mode == "pairs selected":
            if len(selected) < 2:
                return [[m] for m in selected]
            return [[selected[i], selected[i + 1]] for i in range(len(selected) - 1)]
        if mode == "all then singles":
            return [selected] + [[m] for m in selected]
        return [selected]

    def build_ramp_intensities(self, start_intensity, end_intensity, segment_count):
        """Return intensity values across a set of within-cycle segments."""
        ramp_mode = (self.ramp_mode or "None").lower()
        start_intensity = self.clamp_intensity(start_intensity)
        end_intensity = self.clamp_intensity(end_intensity)
        segment_count = max(1, int(segment_count))

        if ramp_mode == "none" or segment_count == 1:
            return [start_intensity] * segment_count

        if ramp_mode == "ramp up":
            final_intensity = max(start_intensity, end_intensity)
        elif ramp_mode == "ramp down":
            final_intensity = min(start_intensity, end_intensity)
        else:
            final_intensity = end_intensity

        values = []
        for i in range(segment_count):
            fraction = i / (segment_count - 1) if segment_count > 1 else 0
            values.append(self.clamp_intensity(round(start_intensity + ((final_intensity - start_intensity) * fraction))))
        return values

    def distribute_duration(self, total_duration_ms, segment_count):
        total_duration_ms = max(1, int(total_duration_ms))
        segment_count = max(1, int(segment_count))
        base = total_duration_ms // segment_count
        remainder = total_duration_ms % segment_count
        return [max(1, base + (1 if i < remainder else 0)) for i in range(segment_count)]

    def build_cycle_segments(self, selected_motors, start_intensity, end_intensity, duration_ms):
        """
        Create the command segments for one cycle.

        Each segment contains:
        - motors: active motor list for that segment
        - intensity: command intensity for the active motors
        - duration_ms: segment duration

        This supports two styles at the same time:
        1. Ramp within cycle: intensity changes across segments.
        2. Motor sweep within cycle: active motor/group changes across segments.
        """
        motor_groups = self.build_motor_groups_for_cycle(selected_motors)
        if not motor_groups:
            return []

        ramp_mode = (self.ramp_mode or "None").lower()
        motor_sweep_mode = (self.motor_sweep_mode or "None").lower()

        if ramp_mode == "none" and motor_sweep_mode == "none":
            segment_count = 1
        elif motor_sweep_mode != "none" and ramp_mode == "none":
            segment_count = len(motor_groups)
        elif motor_sweep_mode == "none" and ramp_mode != "none":
            segment_count = max(2, math.ceil(int(duration_ms) / max(1, int(self.ramp_update_ms))))
        else:
            # Combined motor sweep + ramp: one intensity point per motor/group step.
            segment_count = max(2, len(motor_groups))

        durations = self.distribute_duration(duration_ms, segment_count)
        intensities = self.build_ramp_intensities(start_intensity, end_intensity, segment_count)

        segments = []
        for i in range(segment_count):
            motors = motor_groups[i % len(motor_groups)]
            intensity = intensities[i]
            segments.append({
                "motors": motors,
                "motor_string": ",".join([f"M{m}" for m in motors]),
                "intensity": self.clamp_intensity(intensity),
                "duration_ms": durations[i],
            })
        return segments

    def set_current_motor_intensities(self, active_motors, intensity):
        """Track per-motor intensity for CSV output."""
        active = set(active_motors or [])
        intensity = self.clamp_intensity(intensity)
        self.current_segment_motors = sorted(active)
        self.current_motor_intensities = {
            i: (intensity if i in active else 0)
            for i in range(1, self.motor_count + 1)
        }

    def get_motor_intensity_fields(self):
        return {f"m{i}_intensity": self.current_motor_intensities.get(i, 0) for i in range(1, self.motor_count + 1)}

    def start_next_cycle(self, send_first=False):
        if not self.is_test_running or not self.current_trial_metadata:
            return False

        duration_ms = self.current_trial_metadata.get("duration_ms", "")
        selected_motors = self.current_trial_metadata.get("selected_motor_numbers", [])
        self.current_cycle_intensity = self.get_cycle_intensity(self.current_cycle)
        cycle_start_intensity = self.current_cycle_intensity

        self.ramp_segments = self.build_cycle_segments(selected_motors, cycle_start_intensity, self.ramp_end_intensity, duration_ms)
        self.ramp_segment_index = 0
        self.current_ramp_segment = 1
        self.ramp_active = len(self.ramp_segments) > 1

        label = self.current_trial_metadata.get("label", "Test")
        self.run_status.config(
            text=f"Running: {label} | Cycle {self.current_cycle}/{self.cycle_count} | Intensity {self.current_cycle_intensity}",
            fg="lime"
        )
        self.realtime_summary_label.config(
            text=(
                f"Live summary: cycle {self.current_cycle}/{self.cycle_count} running | "
                f"ramp={self.ramp_mode} | motor sweep={self.motor_sweep_mode}"
            )
        )
        self.append_log(
            f"[CYCLE] Starting cycle {self.current_cycle}/{self.cycle_count} | "
            f"ramp={self.ramp_mode} | motor_sweep={self.motor_sweep_mode} | segments={len(self.ramp_segments)}"
        )

        return self.send_current_ramp_segment()

    def send_current_ramp_segment(self):
        if not self.is_test_running or not self.current_trial_metadata:
            return False
        if self.ramp_segment_index >= len(self.ramp_segments):
            return False

        segment = self.ramp_segments[self.ramp_segment_index]
        motor_string = segment["motor_string"]
        active_motors = segment["motors"]
        intensity = segment["intensity"]
        segment_duration_ms = segment["duration_ms"]

        self.current_cycle_intensity = self.clamp_intensity(intensity)
        self.current_ramp_segment = self.ramp_segment_index + 1
        self.set_current_motor_intensities(active_motors, self.current_cycle_intensity)

        command = f"TEST:START:{motor_string}:{self.current_cycle_intensity}:{segment_duration_ms}"
        self.append_log(
            f"[SEGMENT] Cycle {self.current_cycle}/{self.cycle_count} | "
            f"segment {self.current_ramp_segment}/{len(self.ramp_segments)} | "
            f"motors={motor_string} | intensity={self.current_cycle_intensity} | duration={segment_duration_ms} ms"
        )
        self.run_status.config(
            text=(
                f"Running: {self.current_trial_metadata.get('label', 'Test')} | "
                f"Cycle {self.current_cycle}/{self.cycle_count} | "
                f"Segment {self.current_ramp_segment}/{len(self.ramp_segments)} | "
                f"{motor_string} @ {self.current_cycle_intensity}"
            ),
            fg="lime"
        )

        if not self.send_motor_command(command):
            self.finish_current_trial(reason="segment_start_failed")
            return False
        return True

    def handle_cycle_stop(self, reason="motor_stop_ack"):
        if self.cycle_force_stop:
            self.finish_current_trial(reason=reason)
            return

        # If ramping within a cycle, each ramp segment ends with its own TEST_STOP ACK.
        # Advance to the next segment first; only complete the cycle after the final segment.
        if self.is_test_running and self.ramp_segments and self.ramp_segment_index < len(self.ramp_segments) - 1:
            self.ramp_segment_index += 1
            self.send_current_ramp_segment()
            return

        self.ramp_active = False
        self.ramp_segments = []
        self.ramp_segment_index = 0
        self.current_ramp_segment = 0
        self.current_segment_motors = []
        self.current_motor_intensities = {i: 0 for i in range(1, self.motor_count + 1)}

        if self.is_test_running and self.current_cycle < self.cycle_count:
            self.append_log(f"[CYCLE] Completed cycle {self.current_cycle}/{self.cycle_count}")
            self.current_cycle += 1
            after_id = self.root.after(250, self.start_next_cycle)
            self.pending_after_ids.append(after_id)
        else:
            self.finish_current_trial(reason=reason)

    def stop_test(self):
        self.cycle_force_stop = True
        self.ramp_active = False
        self.ramp_segments = []
        self.ramp_segment_index = 0
        self.current_ramp_segment = 0
        self.current_segment_motors = []
        self.current_motor_intensities = {i: 0 for i in range(1, self.motor_count + 1)}
        self.send_motor_command("TEST:STOP")
        self.finish_current_trial(reason="stopped_by_user")
        self.run_status.config(text="Stopped", fg="orange")
        self.append_log("[TEST] Stop requested")

    # ---------------- Automation ----------------

    def start_individual_motor_check(self):
        if self.is_test_running:
            messagebox.showerror("Error", "A test is already running")
            return
        if not self.motor_serial or not self.motor_serial.is_open or not self.imu_serial or not self.imu_serial.is_open:
            messagebox.showerror("Error", "Connect both serial ports first")
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
        if self.is_test_running:
            messagebox.showerror("Error", "A test is already running")
            return
        if not self.motor_serial or not self.motor_serial.is_open or not self.imu_serial or not self.imu_serial.is_open:
            messagebox.showerror("Error", "Connect both serial ports first")
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

        try:
            cycle_count = int(self.cycle_count_var.get().strip())
        except Exception:
            cycle_count = 1
        try:
            intensity_step = int(self.intensity_step_var.get().strip())
        except Exception:
            intensity_step = 0

        self.start_trial(
            item["motors"],
            item["intensity"],
            item["duration_ms"],
            mode=self.current_mode,
            label=item["label"],
            auto_next_callback=self.schedule_next_sweep_trial,
            cycle_count=cycle_count,
            intensity_step=intensity_step,
            ramp_mode=self.ramp_mode_var.get().strip() or "None",
            ramp_end_intensity=int(self.ramp_end_intensity_var.get().strip() or item["intensity"]),
            ramp_update_ms=int(self.ramp_update_ms_var.get().strip() or 250),
            motor_sweep_mode=self.motor_sweep_mode_var.get().strip() or "None",
            motor_sweep_step_ms=int(self.motor_sweep_step_ms_var.get().strip() or 500)
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
        self.send_motor_command("TEST:STOP")
        self.finish_current_trial(reason="automation_cancelled")
        self.current_mode = "idle"
        self.sweep_status_label.config(text="Sweep: cancelled", fg="orange")
        self.run_status.config(text="Idle", fg="#ffcc00")
        self.append_log("[SYSTEM] Automation cancelled")

    # ---------------- Incoming Messages ----------------

    def process_queues(self):
        while not self.motor_queue.empty():
            line = self.motor_queue.get()
            self.handle_motor_message(line)

        while not self.imu_queue.empty():
            line = self.imu_queue.get()
            self.handle_imu_message(line)

        self.root.after(100, self.process_queues)

    def handle_motor_message(self, line):
        self.append_log(f"[RX:MOTOR] {line}")

        if line.startswith("STATUS:"):
            self.parse_status_line(line)
        elif line.startswith("EVENT:"):
            self.parse_event_line(line)
        elif line.startswith("ACK:TEST_STOP"):
            self.handle_cycle_stop(reason="motor_stop_ack")
        elif line.startswith("ACK:TEST_START"):
            label = self.current_trial_metadata.get("label", "Test")
            self.run_status.config(text=f"Running: {label}", fg="lime")
        elif line.startswith("ERROR:"):
            self.run_status.config(text="Motor Error", fg="red")

    def handle_imu_message(self, line):
        # Avoid flooding the text log with every IMU row.
        if line.startswith("IMU9:"):
            self.parse_imu9_line(line)
        elif self.parse_legacy_imu_line(line):
            # Supports the older one-IMU format that produced:
            # ax, ay, az, gx, gy, gz, raw_accel_magnitude, amplitude
            pass
        elif line.startswith("READY") or line.startswith("FIRMWARE"):
            self.append_log(f"[RX:IMU] {line}")
        elif line.startswith("ERROR:"):
            self.append_log(f"[RX:IMU] {line}")
            self.run_status.config(text="IMU Error", fg="red")
        else:
            # Show unknown IMU lines, but they are not logged as samples.
            self.append_log(f"[RX:IMU] {line}")

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
            state_text = ", ".join([f"M{i}={self.last_status.get(i, 'OFF')}" for i in range(1, self.motor_count + 1)])
            self.live_motor_state_label.config(text=f"Live motor state: {state_text}")

    def parse_event_line(self, line):
        parts = line.split(":")
        if len(parts) >= 3:
            motor_name = parts[1]
            state = parts[2]
            self.live_motor_state_label.config(text=f"Live motor state: {motor_name} changed to {state}")

    # ---------------- 9-Axis IMU Parsing ----------------

    def get_imu_column_names(self):
        names = []
        for sensor_idx in range(1, self.SENSOR_COUNT + 1):
            for axis in self.AXES:
                names.append(f"s{sensor_idx}_{axis}")
        return names

    def blank_imu_row(self):
        return {name: "" for name in self.get_imu_column_names()}

    def parse_legacy_imu_line(self, line):
        """
        Backward-compatible parser for the older single-IMU firmware format.

        Supported examples:
            IMU:ax,ay,az,gx,gy,gz
            DATA:ax,ay,az,gx,gy,gz
            ax,ay,az,gx,gy,gz
            timestamp,ax,ay,az,gx,gy,gz

        This restores the old CSV columns:
            ax, ay, az, gx, gy, gz, raw_accel_magnitude, amplitude
        """
        cleaned = line.strip()
        upper = cleaned.upper()

        # Do not consume known status/system lines.
        known_prefixes = ("READY", "FIRMWARE", "ERROR:", "STATUS:", "EVENT:", "ACK:", "PING", "PONG")
        if upper.startswith(known_prefixes):
            return False

        # Remove a common single-IMU prefix if present.
        for prefix in ("IMU:", "DATA:", "SENSOR:", "CSV:"):
            if upper.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break

        parts = [p.strip() for p in cleaned.split(",") if p.strip() != ""]
        if len(parts) not in (6, 7):
            return False

        imu_timestamp = ""
        value_parts = parts
        if len(parts) == 7:
            # Treat the first value as an IMU-side timestamp only if all remaining
            # six values are numeric sensor values.
            imu_timestamp = parts[0]
            value_parts = parts[1:]

        try:
            ax, ay, az, gx, gy, gz = [float(v) for v in value_parts]
        except ValueError:
            return False

        now_pc = time.time()
        now_iso = datetime.now().isoformat(timespec="milliseconds")

        if self.is_test_running and self.t0 is not None and self.t1 is None:
            self.tdelta = now_pc - self.t0

        self.current_sample_count += 1

        raw_accel_magnitude = math.sqrt(ax * ax + ay * ay + az * az)
        amplitude = abs(raw_accel_magnitude - 9.81)

        if self.is_test_running and self.current_mode != "idle":
            self.frequency_signal.append(amplitude)
            self.frequency_times.append(self.tdelta)

        selected = self.selected_motors()
        selected_text = ",".join([f"M{i}" for i in selected]) if selected else "None"

        self.sample_label.config(text=f"Samples: {self.current_sample_count}")
        self.last_imu_label.config(
            text=(
                f"Last legacy IMU sample: {now_iso} | "
                f"ax={ax:.3f}, ay={ay:.3f}, az={az:.3f} | "
                f"raw accel magnitude={raw_accel_magnitude:.3f}"
            )
        )

        self.realtime_time_label.config(text=f"Current Time: {now_iso}")
        self.update_timing_labels()
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
            "motor_port": self.current_trial_metadata.get("motor_port", self.motor_port_combo.get().strip()),
            "imu_port": self.current_trial_metadata.get("imu_port", self.imu_port_combo.get().strip()),
            "selected_motors": selected_text,
            "active_segment_motors": ",".join([f"M{i}" for i in self.current_segment_motors]) if self.current_segment_motors else "None",
            "base_intensity": self.current_trial_metadata.get("base_intensity", ""),
            "intensity_step_per_cycle": self.current_trial_metadata.get("intensity_step_per_cycle", ""),
            "ramp_mode": self.current_trial_metadata.get("ramp_mode", "None"),
            "ramp_start_intensity": self.current_trial_metadata.get("ramp_start_intensity", ""),
            "ramp_end_intensity": self.current_trial_metadata.get("ramp_end_intensity", ""),
            "ramp_update_ms": self.current_trial_metadata.get("ramp_update_ms", ""),
            "motor_sweep_mode": self.current_trial_metadata.get("motor_sweep_mode", "None"),
            "motor_sweep_step_ms": self.current_trial_metadata.get("motor_sweep_step_ms", ""),
            "ramp_segment": self.current_ramp_segment,
            "ramp_segment_count": len(self.ramp_segments) if self.ramp_segments else 1,
            "intensity": self.current_cycle_intensity,
            "cycle_count": self.cycle_count,
            "current_cycle": self.current_cycle,
            "sample_number": self.current_sample_count,
            "ax": ax,
            "ay": ay,
            "az": az,
            "gx": gx,
            "gy": gy,
            "gz": gz,
            "raw_accel_magnitude": raw_accel_magnitude,
            "amplitude": amplitude,
        }

        row.update(self.get_motor_intensity_fields())

        if imu_timestamp:
            row["imu_timestamp"] = imu_timestamp

        self.log_rows.append(row)

        if self.is_test_running and self.current_mode != "baseline":
            self.current_trial_samples.append(row)

        return True

    def parse_imu9_line(self, line):
        payload = line.replace("IMU9:", "", 1)
        parts = [p.strip() for p in payload.split(",") if p.strip() != ""]

        if len(parts) == 45:
            imu_timestamp = ""
            value_parts = parts
        elif len(parts) == 46:
            imu_timestamp = parts[0]
            value_parts = parts[1:]
        else:
            self.append_log(f"[ERROR] Bad IMU9 packet. Expected 45 values or timestamp+45 values, got {len(parts)} values.")
            return

        try:
            values = [float(v) for v in value_parts]
        except ValueError:
            self.append_log("[ERROR] Could not parse IMU9 numeric values")
            return

        now_pc = time.time()
        now_iso = datetime.now().isoformat(timespec="milliseconds")

        if self.is_test_running and self.t0 is not None and self.t1 is None:
            self.tdelta = now_pc - self.t0

        self.current_sample_count += 1

        imu_values = dict(zip(self.get_imu_column_names(), values))

        # Frequency estimate signal: average acceleration magnitude across all five sensors.
        accel_magnitudes = []
        for sensor_idx in range(1, self.SENSOR_COUNT + 1):
            ax = imu_values[f"s{sensor_idx}_ax"]
            ay = imu_values[f"s{sensor_idx}_ay"]
            az = imu_values[f"s{sensor_idx}_az"]
            accel_magnitudes.append(math.sqrt(ax * ax + ay * ay + az * az))

        avg_accel_magnitude = statistics.mean(accel_magnitudes)
        avg_amplitude = abs(avg_accel_magnitude - 9.81)

        if self.is_test_running and self.current_mode != "idle":
            self.frequency_signal.append(avg_amplitude)
            self.frequency_times.append(self.tdelta)

        selected = self.selected_motors()
        selected_text = ",".join([f"M{i}" for i in selected]) if selected else "None"

        self.sample_label.config(text=f"Samples: {self.current_sample_count}")
        self.last_imu_label.config(
            text=(
                f"Last IMU9 sample: {now_iso} | "
                f"S1 ax={imu_values['s1_ax']:.3f}, ay={imu_values['s1_ay']:.3f}, az={imu_values['s1_az']:.3f} | "
                f"avg accel magnitude={avg_accel_magnitude:.3f}"
            )
        )

        self.realtime_time_label.config(text=f"Current Time: {now_iso}")
        self.update_timing_labels()
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
            "motor_port": self.current_trial_metadata.get("motor_port", self.motor_port_combo.get().strip()),
            "imu_port": self.current_trial_metadata.get("imu_port", self.imu_port_combo.get().strip()),
            "selected_motors": selected_text,
            "active_segment_motors": ",".join([f"M{i}" for i in self.current_segment_motors]) if self.current_segment_motors else "None",
            "base_intensity": self.current_trial_metadata.get("base_intensity", ""),
            "intensity_step_per_cycle": self.current_trial_metadata.get("intensity_step_per_cycle", ""),
            "ramp_mode": self.current_trial_metadata.get("ramp_mode", "None"),
            "ramp_start_intensity": self.current_trial_metadata.get("ramp_start_intensity", ""),
            "ramp_end_intensity": self.current_trial_metadata.get("ramp_end_intensity", ""),
            "ramp_update_ms": self.current_trial_metadata.get("ramp_update_ms", ""),
            "motor_sweep_mode": self.current_trial_metadata.get("motor_sweep_mode", "None"),
            "motor_sweep_step_ms": self.current_trial_metadata.get("motor_sweep_step_ms", ""),
            "ramp_segment": self.current_ramp_segment,
            "ramp_segment_count": len(self.ramp_segments) if self.ramp_segments else 1,
            "intensity": self.current_cycle_intensity,
            "cycle_count": self.cycle_count,
            "current_cycle": self.current_cycle,
            "sample_number": self.current_sample_count,
        }

        # Optional timestamp from the IMU controller.
        # Leave it out if you only want the 45 sensor columns plus trial fields.
        row.update(self.get_motor_intensity_fields())

        if imu_timestamp:
            row["imu_timestamp"] = imu_timestamp

        row["avg_accel_magnitude"] = avg_accel_magnitude
        row["avg_amplitude"] = avg_amplitude

        row.update(imu_values)

        self.log_rows.append(row)

        if self.is_test_running and self.current_mode != "baseline":
            self.current_trial_samples.append(row)

    # ---------------- Timing / Summary ----------------

    def update_timing_labels(self):
        t0_text = datetime.fromtimestamp(self.t0).strftime("%H:%M:%S.%f")[:-3] if self.t0 else "not set"
        t1_text = "running" if self.t1 is None and self.is_test_running else (
            datetime.fromtimestamp(self.t1).strftime("%H:%M:%S.%f")[:-3] if self.t1 else "not set"
        )

        self.timing_label.config(
            text=f"t0: {t0_text} | t1: {t1_text} | tdelta: {self.tdelta:.3f} s"
        )

    def estimate_frequency_from_peaks(self):
        signal = self.frequency_signal
        times = self.frequency_times

        if len(signal) < 5 or len(times) < 5:
            return 0.0, 0, "not_enough_samples"

        min_v = min(signal)
        max_v = max(signal)
        amplitude_range = max_v - min_v

        if amplitude_range <= 1e-9:
            return 0.0, 0, "flat_signal"

        threshold = min_v + (self.peak_threshold_ratio * amplitude_range)

        peak_times = []
        for i in range(1, len(signal) - 1):
            if signal[i] > threshold and signal[i] > signal[i - 1] and signal[i] > signal[i + 1]:
                # Avoid counting tiny jitter peaks too close together.
                if not peak_times or (times[i] - peak_times[-1]) > 0.05:
                    peak_times.append(times[i])

        peak_count = len(peak_times)
        duration = times[-1] - times[0] if times else 0.0

        if duration <= 0 or peak_count < 2:
            return 0.0, peak_count, "peak_count_duration"

        frequency_hz = peak_count / duration
        return frequency_hz, peak_count, "avg_accel_magnitude_peak_count"

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

        estimated_frequency_hz, frequency_peak_count, frequency_method = self.estimate_frequency_from_peaks()

        if metadata:
            summary = {
                "trial_id": metadata.get("trial_id", self.active_trial_id),
                "test_name": self.test_name_var.get().strip() or metadata.get("test_name", ""),
                "motor_port": metadata.get("motor_port", ""),
                "imu_port": metadata.get("imu_port", ""),
                "mode": metadata.get("mode", self.current_mode),
                "label": metadata.get("label", ""),
                "selected_motors": metadata.get("selected_motors", ""),
                "base_intensity": metadata.get("base_intensity", ""),
                "intensity_step_per_cycle": metadata.get("intensity_step_per_cycle", ""),
                "ramp_mode": metadata.get("ramp_mode", "None"),
                "ramp_start_intensity": metadata.get("ramp_start_intensity", ""),
                "ramp_end_intensity": metadata.get("ramp_end_intensity", ""),
                "ramp_update_ms": metadata.get("ramp_update_ms", ""),
                "motor_sweep_mode": metadata.get("motor_sweep_mode", "None"),
                "motor_sweep_step_ms": metadata.get("motor_sweep_step_ms", ""),
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
                "notes": self.get_notes() or metadata.get("notes", ""),
            }

            self.trial_summaries.append(summary)

            self.summary_label.config(
                text=(
                    f"Last Trial Summary:\n"
                    f"{summary['label']} | samples={summary['sample_count']} | "
                    f"t0={t0_text} | t1={t1_text} | tdelta={self.tdelta:.3f}s | "
                    f"freq={estimated_frequency_hz:.3f} Hz"
                )
            )

            self.append_log(
                f"[SUMMARY] {summary['label']} | samples={summary['sample_count']}, "
                f"tdelta={self.tdelta:.3f}s, freq={estimated_frequency_hz:.3f}Hz"
            )

        self.update_timing_labels()
        self.realtime_summary_label.config(text="Live summary: test complete")

        self.is_test_running = False
        self.current_trial_samples = []
        self.current_trial_metadata = {}
        self.ramp_active = False
        self.ramp_segments = []
        self.ramp_segment_index = 0
        self.current_ramp_segment = 0
        self.current_segment_motors = []
        self.current_motor_intensities = {i: 0 for i in range(1, self.motor_count + 1)}
        self.active_trial_id = None
        self.trial_label.config(text="Active Trial: None")

        if self.sweep_running and callback:
            callback()
        elif not self.sweep_running:
            self.current_mode = "idle"
            self.run_status.config(text="Idle", fg="#ffcc00")

    # ---------------- Save Logs ----------------

    def get_raw_fieldnames(self):
        base_fields = [
            "trial_id",
            "mode",
            "test_name",
            "motor_port",
            "imu_port",
            "selected_motors",
            "active_segment_motors",
            "base_intensity",
            "intensity_step_per_cycle",
            "ramp_mode",
            "ramp_start_intensity",
            "ramp_end_intensity",
            "ramp_update_ms",
            "motor_sweep_mode",
            "motor_sweep_step_ms",
            "ramp_segment",
            "ramp_segment_count",
            "intensity",
            "cycle_count",
            "current_cycle",
            "sample_number",
            "m1_intensity",
            "m2_intensity",
            "m3_intensity",
            "m4_intensity",
        ]

        optional_fields = []
        if any("imu_timestamp" in row for row in self.log_rows):
            optional_fields.append("imu_timestamp")

        legacy_fields = ["ax", "ay", "az", "gx", "gy", "gz", "raw_accel_magnitude", "amplitude"]
        imu9_summary_fields = ["avg_accel_magnitude", "avg_amplitude"]
        imu9_fields = self.get_imu_column_names()

        ordered = base_fields + optional_fields
        for field in legacy_fields + imu9_summary_fields + imu9_fields:
            if any(field in row for row in self.log_rows):
                ordered.append(field)

        # Safety: include any extra keys that appear in rows but are not already ordered.
        for row in self.log_rows:
            for key in row.keys():
                if key not in ordered:
                    ordered.append(key)

        return ordered

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

        metadata_fields = [
            "trial_id",
            "test_name",
            "motor_port",
            "imu_port",
            "mode",
            "label",
            "selected_motors",
            "active_segment_motors",
            "base_intensity",
            "intensity_step_per_cycle",
            "ramp_mode",
            "ramp_start_intensity",
            "ramp_end_intensity",
            "ramp_update_ms",
            "motor_sweep_mode",
            "motor_sweep_step_ms",
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

        try:
            # Always create the raw file if there is anything to save.
            # If no IMU rows were captured, the file still gets created with headers and a clear note.
            with open(raw_path, "w", newline="") as f:
                f.write("TRIAL METADATA AND NOTES\n")
                if self.trial_summaries:
                    metadata_writer = csv.DictWriter(f, fieldnames=metadata_fields, extrasaction="ignore")
                    metadata_writer.writeheader()
                    metadata_writer.writerows(self.trial_summaries)
                else:
                    f.write("No completed trial metadata available yet.\n")

                f.write("\nRAW IMU DATA\n")
                raw_writer = csv.DictWriter(f, fieldnames=self.get_raw_fieldnames(), extrasaction="ignore")
                raw_writer.writeheader()
                if self.log_rows:
                    raw_writer.writerows(self.log_rows)
                else:
                    f.write("No raw IMU samples captured. Check that the IMU controller is connected and sending IMU9 packets or legacy ax,ay,az,gx,gy,gz packets.\n")

            summary_saved = False
            if self.trial_summaries:
                with open(summary_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(self.trial_summaries[0].keys()), extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(self.trial_summaries)
                summary_saved = True

            saved_message = (
                f"Saved logs:\n{raw_path}\n"
                f"Raw IMU rows: {len(self.log_rows)}\n"
            )
            if summary_saved:
                saved_message += f"{summary_path}\nSummary rows: {len(self.trial_summaries)}"
            else:
                saved_message += "No completed trial summary file was needed."

            messagebox.showinfo("Saved", saved_message)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ---------------- Cleanup ----------------

    def append_log(self, text):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def on_close(self):
        try:
            self.cancel_automation()
            if self.motor_serial and self.motor_serial.is_open:
                try:
                    self.send_motor_command("TEST:STOP")
                    time.sleep(0.1)
                except Exception:
                    pass
            self.disconnect_motor_serial()
            self.disconnect_imu_serial()
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = DualSerialIMUValidationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
