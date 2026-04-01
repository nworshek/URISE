import tkinter as tk
from tkinter import messagebox
import serial
import time

ARDUINO_PORT = "COM3"   # change this
BAUD_RATE = 9600

try:
    arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
except Exception as e:
    arduino = None
    print("Serial connection error:", e)

sliders = {}
status_labels = {}

def send_command(command):
    if arduino and arduino.is_open:
        arduino.write((command + "\n").encode())
    else:
        messagebox.showerror("Error", "Arduino is not connected")

def set_motor_speed(motor_number, value):
    value = int(float(value))
    send_command(f"{motor_number}:{value}")

    if value == 0:
        status_labels[motor_number].config(text="OFF", fg="red")
    else:
        status_labels[motor_number].config(text=f"ON ({value})", fg="lime")

def turn_motor_on(motor_number):
    value = sliders[motor_number].get()
    if value == 0:
        value = 255
        sliders[motor_number].set(255)

    send_command(f"{motor_number}:{value}")
    status_labels[motor_number].config(text=f"ON ({value})", fg="lime")

def turn_motor_off(motor_number):
    sliders[motor_number].set(0)
    send_command(f"{motor_number}:0")
    status_labels[motor_number].config(text="OFF", fg="red")

def all_off():
    for i in range(1, 7):
        sliders[i].set(0)
        send_command(f"{i}:0")
        status_labels[i].config(text="OFF", fg="red")

def close_app():
    if arduino and arduino.is_open:
        all_off()
        time.sleep(0.2)
        arduino.close()
    root.destroy()

root = tk.Tk()
root.title("6 Motor Control")
root.configure(bg="#2f2f2f")
root.geometry("1200x430")

title = tk.Label(
    root,
    text="Motor Control Panel",
    bg="#2f2f2f",
    fg="white",
    font=("Arial", 18, "bold")
)
title.pack(pady=10)

main_frame = tk.Frame(root, bg="#2f2f2f")
main_frame.pack(pady=10)

for i in range(1, 7):
    frame = tk.Frame(main_frame, bg="#2f2f2f", padx=12, pady=12)
    frame.grid(row=0, column=i-1, padx=8, pady=8)

    motor_label = tk.Label(
        frame,
        text=f"Motor {i}",
        bg="#2f2f2f",
        fg="white",
        font=("Arial", 14, "bold")
    )
    motor_label.pack(pady=5)

    status = tk.Label(
        frame,
        text="OFF",
        bg="#2f2f2f",
        fg="red",
        font=("Arial", 11)
    )
    status.pack(pady=3)
    status_labels[i] = status

    on_button = tk.Button(
        frame,
        text="ON",
        width=10,
        command=lambda m=i: turn_motor_on(m)
    )
    on_button.pack(pady=3)

    off_button = tk.Button(
        frame,
        text="OFF",
        width=10,
        command=lambda m=i: turn_motor_off(m)
    )
    off_button.pack(pady=3)

    speed_label = tk.Label(
        frame,
        text="Intensity",
        bg="#2f2f2f",
        fg="white",
        font=("Arial", 11)
    )
    speed_label.pack(pady=(10, 3))

    slider = tk.Scale(
        frame,
        from_=255,
        to=0,
        length=180,
        bg="#2f2f2f",
        fg="white",
        highlightthickness=0,
        troughcolor="#555555",
        command=lambda value, m=i: set_motor_speed(m, value)
    )
    slider.set(0)
    slider.pack()
    sliders[i] = slider

bottom_frame = tk.Frame(root, bg="#2f2f2f")
bottom_frame.pack(pady=15)

all_off_button = tk.Button(
    bottom_frame,
    text="ALL OFF",
    width=12,
    command=all_off
)
all_off_button.grid(row=0, column=0, padx=10)

exit_button = tk.Button(
    bottom_frame,
    text="EXIT",
    width=12,
    command=close_app
)
exit_button.grid(row=0, column=1, padx=10)

root.protocol("WM_DELETE_WINDOW", close_app)
root.mainloop()