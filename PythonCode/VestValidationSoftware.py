import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import time


class MotorTestGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("14 Motor Haptic Test Software")
        self.root.geometry("700x650")

        self.serial_conn = None

        self.build_gui()

    def build_gui(self):
        connection_frame = ttk.LabelFrame(self.root, text="Serial Connection")
        connection_frame.pack(fill="x", padx=10, pady=10)

        self.port_var = tk.StringVar()
        self.port_dropdown = ttk.Combobox(connection_frame, textvariable=self.port_var, width=25)
        self.port_dropdown.pack(side="left", padx=5, pady=5)

        ttk.Button(connection_frame, text="Refresh Ports", command=self.refresh_ports).pack(side="left", padx=5)
        ttk.Button(connection_frame, text="Connect", command=self.connect_serial).pack(side="left", padx=5)
        ttk.Button(connection_frame, text="Disconnect", command=self.disconnect_serial).pack(side="left", padx=5)

        settings_frame = ttk.LabelFrame(self.root, text="Test Settings")
        settings_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(settings_frame, text="Intensity:").grid(row=0, column=0, padx=5, pady=5)
        self.intensity_var = tk.IntVar(value=180)
        ttk.Entry(settings_frame, textvariable=self.intensity_var, width=10).grid(
        row=0, column=1, padx=5, pady=5, sticky="w"
        )

        ttk.Label(settings_frame, text="Duration ms:").grid(row=1, column=0, padx=5, pady=5)
        self.duration_var = tk.IntVar(value=1000)
        ttk.Entry(settings_frame, textvariable=self.duration_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky="w")

        settings_frame.columnconfigure(1, weight=1)

        motor_frame = ttk.LabelFrame(self.root, text="Individual Motor Tests")
        motor_frame.pack(fill="x", padx=10, pady=10)

        for i in range(14):
            motor_num = i + 1
            btn = ttk.Button(
                motor_frame,
                text=f"Motor {motor_num}",
                command=lambda m=motor_num: self.test_motor(m)
            )
            btn.grid(row=i // 7, column=i % 7, padx=5, pady=5, sticky="ew")

        pattern_frame = ttk.LabelFrame(self.root, text="Pattern Tests")
        pattern_frame.pack(fill="x", padx=10, pady=10)

        patterns = [
            ("All Motors", "ALL"),
            ("Odd Motors", "ODD"),
            ("Even Motors", "EVEN"),
            ("Sweep", "SWEEP"),
            ("1st Half", "FIRST_HALF"),
            ("2nd Half", "SECOND_HALF"),
        ]

        for i, (label, command) in enumerate(patterns):
            ttk.Button(
                pattern_frame,
                text=label,
                command=lambda p=command: self.test_pattern(p)
            ).grid(row=i // 3, column=i % 3, padx=5, pady=5, sticky="ew")

        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", padx=10, pady=10)

        stop_button = tk.Button(
            control_frame,
            text="STOP ALL",
            bg="red",
            fg="white",
            font=("Arial", 14, "bold"),
            command=self.stop_all
        )
        stop_button.pack(fill="x", pady=5)

        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_box = tk.Text(log_frame, height=10)
        self.log_box.pack(fill="both", expand=True)

        self.refresh_ports()

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports]
        self.port_dropdown["values"] = port_names

        if port_names:
            self.port_var.set(port_names[0])

    def connect_serial(self):
        port = self.port_var.get()

        if not port:
            messagebox.showerror("Error", "No serial port selected.")
            return

        try:
            self.serial_conn = serial.Serial(port, 115200, timeout=1)
            time.sleep(2)
            self.log(f"Connected to {port}")
            self.send_command("PING")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def disconnect_serial(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.log("Disconnected.")

    def send_command(self, command):
        if not self.serial_conn or not self.serial_conn.is_open:
            messagebox.showerror("Error", "Serial device not connected.")
            return

        try:
            self.serial_conn.write((command + "\n").encode())
            self.log(f"SENT: {command}")

            response = self.serial_conn.readline().decode(errors="ignore").strip()
            if response:
                self.log(f"RECV: {response}")

        except Exception as e:
            messagebox.showerror("Serial Error", str(e))

    def test_motor(self, motor_num):
        intensity = self.intensity_var.get()
        duration = self.duration_var.get()
        intensity = max(0, min(255, self.intensity_var.get()))
        duration = max(1, self.duration_var.get())

        command = f"MOTOR:{motor_num}:{intensity}:{duration}"
        self.send_command(command)

    def test_pattern(self, pattern):
        intensity = self.intensity_var.get()
        duration = self.duration_var.get()
        intensity = max(0, min(255, self.intensity_var.get()))
        duration = max(1, self.duration_var.get())

        command = f"PATTERN:{pattern}:{intensity}:{duration}"
        self.send_command(command)

    def stop_all(self):
        self.send_command("STOP")

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")


if __name__ == "__main__":
    root = tk.Tk()
    app = MotorTestGUI(root)
    root.mainloop()