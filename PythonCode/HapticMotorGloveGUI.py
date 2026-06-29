import tkinter as tk
from tkinter import ttk
from pathlib import Path
from PIL import Image, ImageTk
import serial
import serial.tools.list_ports
import time

BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "glove_clean.png"

MOTOR_OFF = "gray"
MOTOR_ON = "lime green"


class HapticGloveGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Haptic Glove Visual Motor Control")

        self.serial_connection = None

        self.motor_positions = {
            1:  (145, 300),
            2:  (160, 360),
            3:  (175, 430),

            4:  (225, 200),
            5:  (240, 270),
            6:  (250, 350),

            7:  (335, 190),
            8:  (335, 260),
            9:  (325, 350),

            10: (450, 240),
            11: (425, 315),
            12: (400, 380),

            13: (515, 500),
        }

        self.motor_states = {}
        self.motor_circles = {}
        self.motor_labels = {}

        self.setup_layout()
        self.load_glove_image()
        self.create_motors()
        self.refresh_ports()

    def setup_layout(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            main_frame,
            width=600,
            height=850,
            bg="white"
        )
        self.canvas.pack(side="left")

        control_frame = tk.Frame(main_frame, padx=15, pady=15)
        control_frame.pack(side="right", fill="y")

        tk.Label(control_frame, text="Serial Connection", font=("Arial", 14, "bold")).pack(anchor="w")

        self.port_box = ttk.Combobox(control_frame, width=25)
        self.port_box.pack(pady=5)

        tk.Button(control_frame, text="Refresh Ports", command=self.refresh_ports).pack(fill="x", pady=2)
        tk.Button(control_frame, text="Connect", command=self.connect_serial).pack(fill="x", pady=2)
        tk.Button(control_frame, text="Disconnect", command=self.disconnect_serial).pack(fill="x", pady=2)

        self.connection_label = tk.Label(control_frame, text="Not Connected", fg="red")
        self.connection_label.pack(anchor="w", pady=8)

        ttk.Separator(control_frame).pack(fill="x", pady=10)

        tk.Label(control_frame, text="Motor Settings", font=("Arial", 14, "bold")).pack(anchor="w")

        tk.Label(control_frame, text="Intensity 0-255").pack(anchor="w")
        self.intensity_entry = tk.Entry(control_frame)
        self.intensity_entry.insert(0, "180")
        self.intensity_entry.pack(fill="x", pady=3)

        tk.Label(control_frame, text="Duration ms").pack(anchor="w")
        self.duration_entry = tk.Entry(control_frame)
        self.duration_entry.insert(0, "1000")
        self.duration_entry.pack(fill="x", pady=3)

        ttk.Separator(control_frame).pack(fill="x", pady=10)

        tk.Label(control_frame, text="Patterns", font=("Arial", 14, "bold")).pack(anchor="w")

        tk.Button(control_frame, text="All On", command=self.all_on).pack(fill="x", pady=2)
        tk.Button(control_frame, text="All Off", command=self.all_off).pack(fill="x", pady=2)
        tk.Button(control_frame, text="Sweep", command=self.sweep_pattern).pack(fill="x", pady=2)
        tk.Button(control_frame, text="Odd Motors", command=self.odd_pattern).pack(fill="x", pady=2)
        tk.Button(control_frame, text="Even Motors", command=self.even_pattern).pack(fill="x", pady=2)
        tk.Button(control_frame, text="STOP", bg="red", fg="white", command=self.stop_all).pack(fill="x", pady=8)

        ttk.Separator(control_frame).pack(fill="x", pady=10)

        tk.Label(control_frame, text="Console", font=("Arial", 14, "bold")).pack(anchor="w")

        self.console = tk.Text(control_frame, height=14, width=35)
        self.console.pack()

    def load_glove_image(self):
        image = Image.open(IMAGE_PATH)
        image = image.resize((600, 850))
        self.glove_photo = ImageTk.PhotoImage(image)

        self.canvas.create_image(
            0,
            0,
            anchor="nw",
            image=self.glove_photo
        )

    def create_motors(self):
        for motor_id, (x, y) in self.motor_positions.items():
            self.motor_states[motor_id] = False

            circle = self.canvas.create_oval(
                x - 18,
                y - 18,
                x + 18,
                y + 18,
                fill=MOTOR_OFF,
                outline="black",
                width=2
            )

            label = self.canvas.create_text(
                x,
                y,
                text=str(motor_id),
                fill="white",
                font=("Arial", 10, "bold")
            )

            self.motor_circles[motor_id] = circle
            self.motor_labels[motor_id] = label

            self.canvas.tag_bind(circle, "<Button-1>", lambda event, m=motor_id: self.toggle_motor(m))
            self.canvas.tag_bind(label, "<Button-1>", lambda event, m=motor_id: self.toggle_motor(m))

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports]
        self.port_box["values"] = port_names

        if port_names:
            self.port_box.current(0)

    def connect_serial(self):
        port = self.port_box.get()

        if not port:
            self.log("No serial port selected.")
            return

        try:
            self.serial_connection = serial.Serial(port, 115200, timeout=1)
            time.sleep(2)
            self.connection_label.config(text=f"Connected: {port}", fg="green")
            self.log(f"Connected to {port}")
        except Exception as e:
            self.log(f"Connection failed: {e}")

    def disconnect_serial(self):
        if self.serial_connection:
            self.serial_connection.close()
            self.serial_connection = None

        self.connection_label.config(text="Not Connected", fg="red")
        self.log("Disconnected.")

    def get_intensity(self):
        try:
            value = int(self.intensity_entry.get())
            return max(0, min(255, value))
        except ValueError:
            return 180

    def get_duration(self):
        try:
            value = int(self.duration_entry.get())
            return max(0, value)
        except ValueError:
            return 1000

    def toggle_motor(self, motor_id):
        self.motor_states[motor_id] = not self.motor_states[motor_id]

        if self.motor_states[motor_id]:
            intensity = self.get_intensity()
            command = f"M{motor_id}:{intensity}"
            self.set_motor_visual(motor_id, True)
        else:
            command = f"M{motor_id}:0"
            self.set_motor_visual(motor_id, False)

        self.send_motor_command(command)

    def set_motor_visual(self, motor_id, state):
        self.motor_states[motor_id] = state

        if state:
            self.canvas.itemconfig(self.motor_circles[motor_id], fill=MOTOR_ON)
        else:
            self.canvas.itemconfig(self.motor_circles[motor_id], fill=MOTOR_OFF)

    def all_on(self):
        intensity = self.get_intensity()

        for motor_id in self.motor_positions:
            self.set_motor_visual(motor_id, True)

        self.send_motor_command(f"ALL:{intensity}")

    def all_off(self):
        for motor_id in self.motor_positions:
            self.set_motor_visual(motor_id, False)

        self.send_motor_command("ALL:0")

    def stop_all(self):
        for motor_id in self.motor_positions:
            self.set_motor_visual(motor_id, False)

        self.send_motor_command("STOP")

    def sweep_pattern(self):
        intensity = self.get_intensity()
        duration = self.get_duration()
        self.send_motor_command(f"PATTERN:SWEEP:{intensity}:{duration}")

    def odd_pattern(self):
        intensity = self.get_intensity()
        duration = self.get_duration()
        self.send_motor_command(f"PATTERN:ODD:{intensity}:{duration}")

    def even_pattern(self):
        intensity = self.get_intensity()
        duration = self.get_duration()
        self.send_motor_command(f"PATTERN:EVEN:{intensity}:{duration}")

    def send_motor_command(self, command):
        self.log(command)

        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.write((command + "\n").encode())
        else:
            self.log("Not connected. Command printed only.")

    def log(self, message):
        self.console.insert("end", message + "\n")
        self.console.see("end")
        print(message)


if __name__ == "__main__":
    root = tk.Tk()
    app = HapticGloveGUI(root)
    root.mainloop()