import tkinter as tk
from tkinter import messagebox
import serial
import time

# Change this to your Arduino Nano port
ARDUINO_PORT = "COM3"     # Example: COM3 on Windows
BAUD_RATE = 9600

# Serial connection
try:
    arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # wait for Arduino reset
except Exception as e:
    arduino = None
    print("Serial connection error:", e)


def send_command(command, motor_name, state):
    if arduino and arduino.is_open:
        arduino.write(command.encode())
        status_label.config(text=f"{motor_name}: {state}")
    else:
        messagebox.showerror("Connection error", "Arduino is not connected")


def all_off():
    if arduino and arduino.is_open:
        off_commands = ['0', 'q', 'w', 'e', 'r', 't']
        for cmd in off_commands:
            arduino.write(cmd.encode())
            time.sleep(0.05)
        status_label.config(text="All motors: OFF")


def close_app():
    if arduino and arduino.is_open:
        all_off()
        arduino.close()
    root.destroy()


# Main window
root = tk.Tk()
root.title("Arduino Nano - Motor Control")
root.geometry("650x420")
root.resizable(False, False)

title_label = tk.Label(root, text="Motor Control Panel", font=("Arial", 18, "bold"))
title_label.pack(pady=10)

status_label = tk.Label(root, text="System ready", font=("Arial", 12), fg="blue")
status_label.pack(pady=5)

main_frame = tk.Frame(root)
main_frame.pack(pady=15)

motors = [
    ("Motor 1", '1', '0'),
    ("Motor 2", '2', 'q'),
    ("Motor 3", '3', 'w'),
    ("Motor 4", '4', 'e'),
    ("Motor 5", '5', 'r'),
    ("Motor 6", '6', 't'),
]

for i, (motor_name, on_cmd, off_cmd) in enumerate(motors):
    row = i // 2
    col = (i % 2) * 3

    label = tk.Label(main_frame, text=motor_name, font=("Arial", 12, "bold"))
    label.grid(row=row * 2, column=col, columnspan=2, pady=(10, 5), padx=20)

    on_button = tk.Button(
        main_frame,
        text="ON",
        width=12,
        bg="green",
        fg="white",
        font=("Arial", 11),
        command=lambda c=on_cmd, m=motor_name: send_command(c, m, "ON")
    )
    on_button.grid(row=row * 2 + 1, column=col, padx=5, pady=5)

    off_button = tk.Button(
        main_frame,
        text="OFF",
        width=12,
        bg="red",
        fg="white",
        font=("Arial", 11),
        command=lambda c=off_cmd, m=motor_name: send_command(c, m, "OFF")
    )
    off_button.grid(row=row * 2 + 1, column=col + 1, padx=5, pady=5)

bottom_frame = tk.Frame(root)
bottom_frame.pack(pady=20)

all_off_button = tk.Button(
    bottom_frame,
    text="TURN ALL OFF",
    width=15,
    font=("Arial", 11, "bold"),
    command=all_off
)
all_off_button.grid(row=0, column=0, padx=10)

exit_button = tk.Button(
    bottom_frame,
    text="EXIT",
    width=15,
    font=("Arial", 11, "bold"),
    command=close_app
)
exit_button.grid(row=0, column=1, padx=10)

root.protocol("WM_DELETE_WINDOW", close_app)
root.mainloop()