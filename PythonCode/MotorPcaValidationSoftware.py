import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import time


class MotorValidationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("16-Motor PCA9685 Validation Tool")
        self.root.geometry("620x520")

        self.ser = None

        self.port_var = tk.StringVar()
        self.intensity_var = tk.IntVar(value=180)
        self.duration_var = tk.IntVar(value=500)

        self.build_gui()
        self.refresh_ports()

    def build_gui(self):
        connection_frame = ttk.LabelFrame(self.root, text="Serial Connection")
        connection_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(connection_frame, text="Port:").pack(side="left", padx=5)

        self.port_menu = ttk.Combobox(connection_frame, textvariable=self.port_var, width=30)
        self.port_menu.pack(side="left", padx=5)

        ttk.Button(connection_frame, text="Refresh", command=self.refresh_ports).pack(side="left", padx=5)
        ttk.Button(connection_frame, text="Connect", command=self.connect_serial).pack(side="left", padx=5)
        ttk.Button(connection_frame, text="Disconnect", command=self.disconnect_serial).pack(side="left", padx=5)

        settings_frame = ttk.LabelFrame(self.root, text="Motor Settings")
        settings_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(settings_frame, text="Intensity 0-255:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.intensity_var, width=10).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="Duration ms:").grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.duration_var, width=10).grid(row=0, column=3, padx=5, pady=5)

        motor_frame = ttk.LabelFrame(self.root, text="Individual Motor Test")
        motor_frame.pack(fill="both", expand=True, padx=10, pady=10)

        for i in range(16):
            btn = ttk.Button(
                motor_frame,
                text=f"Motor {i}",
                command=lambda m=i: self.test_motor(m)
            )
            btn.grid(row=i // 4, column=i % 4, padx=10, pady=10, sticky="ew")

        pattern_frame = ttk.LabelFrame(self.root, text="Pattern Tests")
        pattern_frame.pack(fill="x", padx=10, pady=10)

        patterns = [
            ("All", "ALL"),
            ("Odd", "ODD"),
            ("Even", "EVEN"),
            ("Sweep", "SWEEP"),
            ("1st Half", "FIRST_HALF"),
            ("2nd Half", "SECOND_HALF")
        ]

        for i, (label, command) in enumerate(patterns):
            ttk.Button(
                pattern_frame,
                text=label,
                command=lambda p=command: self.test_pattern(p)
            ).grid(row=0, column=i, padx=5, pady=5)

        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(control_frame, text="STOP / ALL OFF", command=self.stop_all).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Ping ESP32S3", command=self.ping).pack(side="left", padx=5)

        self.log_box = tk.Text(self.root, height=8)
        self.log_box.pack(fill="both", padx=10, pady=10)

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_names = [p.device for p in ports]
        self.port_menu["values"] = port_names

        if port_names:
            self.port_var.set(port_names[0])

    def connect_serial(self):
        port = self.port_var.get()

        if not port:
            messagebox.showerror("Error", "No serial port selected.")
            return

        try:
            self.ser = serial.Serial(port, 115200, timeout=1)
            time.sleep(2)
            self.log(f"Connected to {port}")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def disconnect_serial(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.log("Disconnected")

    def send_command(self, command):
        if not self.ser or not self.ser.is_open:
            messagebox.showerror("Error", "Serial port not connected.")
            return

        try:
            self.ser.write((command + "\n").encode())
            self.log(f"> {command}")

            time.sleep(0.1)

            while self.ser.in_waiting:
                response = self.ser.readline().decode(errors="ignore").strip()
                if response:
                    self.log(f"< {response}")

        except Exception as e:
            messagebox.showerror("Serial Error", str(e))

    def get_settings(self):
        intensity = self.intensity_var.get()
        duration = self.duration_var.get()

        intensity = max(0, min(255, intensity))
        duration = max(10, duration)

        return intensity, duration

    def test_motor(self, motor_index):
        intensity, duration = self.get_settings()
        self.send_command(f"MOTOR:{motor_index}:{intensity}:{duration}")

    def test_pattern(self, pattern):
        intensity, duration = self.get_settings()
        self.send_command(f"PATTERN:{pattern}:{intensity}:{duration}")

    def stop_all(self):
        self.send_command("STOP")

    def ping(self):
        self.send_command("PING")

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")


if __name__ == "__main__":
    root = tk.Tk()
    app = MotorValidationGUI(root)
    root.mainloop()