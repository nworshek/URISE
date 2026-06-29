import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import queue
import time
import csv
from datetime import datetime


class IMUValidationApp:
    """
    Separate desktop software for phantom-based electrical validation testing.

    Purpose:
    - Connect to a dedicated Arduino handling IMU sensing and motor test execution
    - Let the operator test motors individually or in grouped configurations
    - Clearly show which motors are armed / selected before starting a test
    - Log incoming IMU data for later validation analysis

    Assumed serial protocol from Arduino:
    ------------------------------------
    Commands sent from Python:
      PING
      STOP
      STATUS
      TEST:START:M1[,M2,M3...]:<intensity>:<duration_ms>
      TEST:STOP

    Example:
      TEST:START:M1,M3,M5:180:5000

    Expected Arduino responses (examples):
      READY
      ACK:TEST_START
      ACK:TEST_STOP
      STATUS:M1=OFF,M2=ON,M3=OFF,M4=OFF,M5=OFF,M6=OFF
      IMU:1712590000,ax,ay,az,gx,gy,gz
      EVENT:M3:ON
      EVENT:M3:OFF
      ERROR:<message>

    Notes:
    - Update the protocol here if your Arduino firmware uses a different format.
    - pyserial is required: pip install pyserial
    """

    def __init__(self, root):
        self.root = root
        self.root.title("IMU Validation Control")
        self.root.configure(bg="#202020")

        self.serial_conn = None
        self.reader_thread = None
        self.reader_running = False
        self.rx_queue = queue.Queue()

        self.motor_count = 6
        self.motor_vars = {i: tk.BooleanVar(value=False) for i in range(1, self.motor_count + 1)}
        self.motor_status_labels = {}

        self.is_test_running = False
        self.last_status = {i: "OFF" for i in range(1, self.motor_count + 1)}
        self.log_rows = []
        self.test_start_time = None

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
        title.pack(pady=(12, 6))

        subtitle = tk.Label(
            self.root,
            text="Separate software for IMU-based motor intensity validation",
            bg="#202020",
            fg="#cfcfcf",
            font=("Arial", 10)
        )
        subtitle.pack(pady=(0, 12))

        top = tk.Frame(self.root, bg="#202020")
        top.pack(fill="x", padx=12)

        self.build_connection_frame(top)
        self.build_test_settings_frame(top)

        middle = tk.Frame(self.root, bg="#202020")
        middle.pack(fill="both", expand=True, padx=12, pady=10)

        self.build_motor_selection_frame(middle)
        self.build_configurations_frame(middle)

        bottom = tk.Frame(self.root, bg="#202020")
        bottom.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.build_status_frame(bottom)
        self.build_log_frame(bottom)

    def build_connection_frame(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="Arduino / IMU Connection",
            bg="#202020",
            fg="white",
            padx=10,
            pady=10,
            font=("Arial", 10, "bold")
        )
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(frame, text="Serial Port", bg="#202020", fg="white").grid(row=0, column=0, sticky="w", pady=4)
        self.port_combo = ttk.Combobox(frame, state="readonly", width=20)
        self.port_combo.grid(row=0, column=1, padx=6, pady=4)

        tk.Button(frame, text="Refresh", width=10, command=self.refresh_ports).grid(row=0, column=2, padx=4, pady=4)

        tk.Label(frame, text="Baud Rate", bg="#202020", fg="white").grid(row=1, column=0, sticky="w", pady=4)
        self.baud_var = tk.StringVar(value="115200")
        tk.Entry(frame, textvariable=self.baud_var, width=12).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        self.connection_status = tk.Label(frame, text="Disconnected", bg="#202020", fg="red", font=("Arial", 10, "bold"))
        self.connection_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 4))

        tk.Button(frame, text="Connect", width=12, command=self.connect_serial).grid(row=2, column=2, padx=4, pady=4)
        tk.Button(frame, text="Disconnect", width=12, command=self.disconnect_serial).grid(row=3, column=2, padx=4, pady=4)
        tk.Button(frame, text="Get Status", width=12, command=lambda: self.send_command("STATUS")).grid(row=4, column=2, padx=4, pady=4)

    def build_test_settings_frame(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="Test Settings",
            bg="#202020",
            fg="white",
            padx=10,
            pady=10,
            font=("Arial", 10, "bold")
        )
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        tk.Label(frame, text="Intensity (0-255)", bg="#202020", fg="white").grid(row=0, column=0, sticky="w", pady=4)
        self.intensity_var = tk.StringVar(value="180")
        tk.Entry(frame, textvariable=self.intensity_var, width=12).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        tk.Label(frame, text="Duration (ms)", bg="#202020", fg="white").grid(row=1, column=0, sticky="w", pady=4)
        self.duration_var = tk.StringVar(value="5000")
        tk.Entry(frame, textvariable=self.duration_var, width=12).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        tk.Label(frame, text="Test Name", bg="#202020", fg="white").grid(row=2, column=0, sticky="w", pady=4)
        self.test_name_var = tk.StringVar(value="phantom_validation_run")
        tk.Entry(frame, textvariable=self.test_name_var, width=24).grid(row=2, column=1, sticky="w", padx=6, pady=4)

        tk.Button(frame, text="Start Test", width=12, command=self.start_test).grid(row=3, column=0, padx=4, pady=(10, 4))
        tk.Button(frame, text="Stop Test", width=12, command=self.stop_test).grid(row=3, column=1, padx=4, pady=(10, 4), sticky="w")
        tk.Button(frame, text="Save Log", width=12, command=self.save_log).grid(row=3, column=2, padx=4, pady=(10, 4))

        self.run_status = tk.Label(frame, text="Idle", bg="#202020", fg="#ffcc00", font=("Arial", 10, "bold"))
        self.run_status.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))

    def build_motor_selection_frame(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="Motor Selection / Pre-Test Arm State",
            bg="#202020",
            fg="white",
            padx=10,
            pady=10,
            font=("Arial", 10, "bold")
        )
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        instructions = tk.Label(
            frame,
            text="Selected motors below are the motors that will be active for the next test.",
            bg="#202020",
            fg="#d0d0d0",
            anchor="w",
            justify="left"
        )
        instructions.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        for i in range(1, self.motor_count + 1):
            row = ((i - 1) // 2) + 1
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
        button_row.grid(row=5, column=0, columnspan=2, pady=(10, 0), sticky="w")

        tk.Button(button_row, text="Select All", width=12, command=self.select_all_motors).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Clear All", width=12, command=self.clear_all_motors).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Odd Motors", width=12, command=lambda: self.set_motor_pattern([1, 3, 5])).pack(side="left", padx=(0, 8))
        tk.Button(button_row, text="Even Motors", width=12, command=lambda: self.set_motor_pattern([2, 4, 6])).pack(side="left")

    def build_configurations_frame(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="Quick Configurations",
            bg="#202020",
            fg="white",
            padx=10,
            pady=10,
            font=("Arial", 10, "bold")
        )
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        configs = [
            ("Single Motor Sweep", self.single_motor_prompt),
            ("All Motors", self.select_all_motors),
            ("Left Side (1,2,3)", lambda: self.set_motor_pattern([1, 2, 3])),
            ("Right Side (4,5,6)", lambda: self.set_motor_pattern([4, 5, 6])),
            ("Alternating A (1,3,5)", lambda: self.set_motor_pattern([1, 3, 5])),
            ("Alternating B (2,4,6)", lambda: self.set_motor_pattern([2, 4, 6])),
            ("Center Pair (3,4)", lambda: self.set_motor_pattern([3, 4])),
            ("Outer Pair (1,6)", lambda: self.set_motor_pattern([1, 6])),
        ]

        for idx, (label, action) in enumerate(configs):
            tk.Button(frame, text=label, width=22, command=action).grid(row=idx, column=0, sticky="w", padx=4, pady=4)

        info = tk.Label(
            frame,
            text="Use these presets to test motors in repeatable patterns for phantom validation runs.",
            bg="#202020",
            fg="#d0d0d0",
            justify="left",
            wraplength=260
        )
        info.grid(row=len(configs), column=0, sticky="w", pady=(12, 0))

    def build_status_frame(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="Current Selection / Live Status",
            bg="#202020",
            fg="white",
            padx=10,
            pady=10,
            font=("Arial", 10, "bold")
        )
        frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.pretest_label = tk.Label(
            frame,
            text="Selected for next test: None",
            bg="#202020",
            fg="#00d7ff",
            font=("Arial", 11, "bold"),
            anchor="w",
            justify="left"
        )
        self.pretest_label.pack(fill="x", pady=(0, 8))

        self.live_motor_state_label = tk.Label(
            frame,
            text="Live motor state: Unknown",
            bg="#202020",
            fg="white",
            anchor="w",
            justify="left"
        )
        self.live_motor_state_label.pack(fill="x", pady=(0, 8))

        self.last_imu_label = tk.Label(
            frame,
            text="Last IMU sample: None",
            bg="#202020",
            fg="#d0d0d0",
            anchor="w",
            justify="left",
            wraplength=420
        )
        self.last_imu_label.pack(fill="x")

        self.update_pretest_display()

    def build_log_frame(self, parent):
        frame = tk.LabelFrame(
            parent,
            text="Event / IMU Log",
            bg="#202020",
            fg="white",
            padx=10,
            pady=10,
            font=("Arial", 10, "bold")
        )
        frame.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.log_text = tk.Text(frame, height=18, width=70, bg="#111111", fg="#f0f0f0", insertbackground="white")
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

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

    def single_motor_prompt(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Single Motor")
        dialog.configure(bg="#202020")
        dialog.grab_set()

        tk.Label(dialog, text="Select one motor for the next test", bg="#202020", fg="white", font=("Arial", 11, "bold")).pack(padx=16, pady=(16, 10))

        selected_var = tk.IntVar(value=1)
        for i in range(1, self.motor_count + 1):
            tk.Radiobutton(
                dialog,
                text=f"Motor {i}",
                variable=selected_var,
                value=i,
                bg="#202020",
                fg="white",
                selectcolor="#202020",
                activebackground="#202020",
                activeforeground="white"
            ).pack(anchor="w", padx=20, pady=2)

        def apply_selection():
            self.set_motor_pattern([selected_var.get()])
            dialog.destroy()

        tk.Button(dialog, text="Apply", width=12, command=apply_selection).pack(pady=16)

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
        except Exception as e:
            self.serial_conn = None
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

    def send_command(self, cmd):
        if not self.serial_conn or not self.serial_conn.is_open:
            self.append_log(f"[WARN] Cannot send command while disconnected: {cmd}")
            return
        try:
            self.serial_conn.write((cmd + "\n").encode())
            self.append_log(f"[TX] {cmd}")
        except Exception as e:
            self.append_log(f"[ERROR] Failed to send command: {e}")

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

    # ---------------- Test Control ----------------

    def validate_test_inputs(self):
        motors = self.selected_motors()
        if not motors:
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

        if not (0 <= intensity <= 255):
            messagebox.showerror("Error", "Intensity must be between 0 and 255")
            return None

        if duration_ms <= 0:
            messagebox.showerror("Error", "Duration must be greater than 0")
            return None

        if not self.serial_conn or not self.serial_conn.is_open:
            messagebox.showerror("Error", "Connect to the Arduino first")
            return None

        return motors, intensity, duration_ms

    def start_test(self):
        validated = self.validate_test_inputs()
        if not validated:
            return

        motors, intensity, duration_ms = validated
        motor_string = ",".join([f"M{i}" for i in motors])
        command = f"TEST:START:{motor_string}:{intensity}:{duration_ms}"

        self.log_rows = []
        self.test_start_time = time.time()
        self.is_test_running = True
        self.run_status.config(text="Running", fg="lime")

        self.append_log("[TEST] Starting new validation run")
        self.append_log(f"[TEST] Motors selected before start: {motor_string}")
        self.append_log(f"[TEST] Intensity: {intensity}")
        self.append_log(f"[TEST] Duration (ms): {duration_ms}")

        self.send_command(command)

    def stop_test(self):
        self.send_command("TEST:STOP")
        self.is_test_running = False
        self.run_status.config(text="Stopped", fg="orange")
        self.append_log("[TEST] Stop requested")

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
            self.is_test_running = False
            self.run_status.config(text="Idle", fg="#ffcc00")
        elif line.startswith("ACK:TEST_START"):
            self.run_status.config(text="Running", fg="lime")
        elif line.startswith("READY"):
            pass
        elif line.startswith("ERROR:"):
            self.run_status.config(text="Error", fg="red")

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
        # Example: EVENT:M3:ON
        parts = line.split(":")
        if len(parts) >= 3:
            motor_name = parts[1]
            state = parts[2]
            self.live_motor_state_label.config(text=f"Live motor state: {motor_name} changed to {state}")

    def parse_imu_line(self, line):
        # Example: IMU:1712590000,ax,ay,az,gx,gy,gz
        payload = line.replace("IMU:", "", 1)
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) < 7:
            return

        timestamp_raw, ax, ay, az, gx, gy, gz = parts[:7]
        selected = self.selected_motors()
        selected_text = ",".join([f"M{i}" for i in selected]) if selected else "None"
        elapsed = round(time.time() - self.test_start_time, 3) if self.test_start_time else 0.0

        self.last_imu_label.config(
            text=f"Last IMU sample: t={timestamp_raw}, ax={ax}, ay={ay}, az={az}, gx={gx}, gy={gy}, gz={gz}"
        )

        self.log_rows.append({
            "pc_timestamp": datetime.now().isoformat(),
            "elapsed_s": elapsed,
            "imu_timestamp": timestamp_raw,
            "selected_motors": selected_text,
            "ax": ax,
            "ay": ay,
            "az": az,
            "gx": gx,
            "gy": gy,
            "gz": gz,
        })

    # ---------------- Logging ----------------

    def append_log(self, text):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def save_log(self):
        if not self.log_rows:
            messagebox.showinfo("Info", "No IMU log data available to save yet")
            return

        default_name = f"{self.test_name_var.get().strip()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(
            title="Save IMU log",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")]
        )
        if not path:
            return

        fieldnames = list(self.log_rows[0].keys())
        try:
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.log_rows)
            messagebox.showinfo("Saved", f"Log saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ---------------- Cleanup ----------------

    def on_close(self):
        try:
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
