import tkinter as tk

root = tk.Tk()
root.title("Motor Control")
root.configure(bg="#2f2f2f")

NUM_MOTORS = 6


def turn_motor_on(motor_name):
    print(f"{motor_name} ON")


def turn_motor_off(motor_name):
    print(f"{motor_name} OFF")


def intensity_up(motor_name):
    print(f"{motor_name} Intensity Increase +1")


def intensity_down(motor_name):
    print(f"{motor_name} Intensity Decrease -1")


def turn_all_on():
    for i in range(NUM_MOTORS):
        motor_name = f"Motor{i+1}"
        turn_motor_on(motor_name)


def turn_all_off():
    for i in range(NUM_MOTORS):
        motor_name = f"Motor{i+1}"
        turn_motor_off(motor_name)


def intensity_all_up():
    for i in range(NUM_MOTORS):
        motor_name = f"Motor{i+1}"
        intensity_up(motor_name)


def intensity_all_down():
    for i in range(NUM_MOTORS):
        motor_name = f"Motor{i+1}"
        intensity_down(motor_name)


# Top control frame for all motors
all_frame = tk.Frame(root, bg="#2f2f2f", padx=15, pady=15)
all_frame.grid(row=0, column=0, columnspan=NUM_MOTORS, pady=10)

all_label = tk.Label(
    all_frame,
    text="ALL MOTORS",
    bg="#2f2f2f",
    fg="white",
    font=("Arial", 16, "bold")
)
all_label.pack(pady=5)

all_on_button = tk.Button(
    all_frame,
    text="ALL ON",
    width=12,
    command=turn_all_on
)
all_on_button.pack(pady=3)

all_off_button = tk.Button(
    all_frame,
    text="ALL OFF",
    width=12,
    command=turn_all_off
)
all_off_button.pack(pady=3)

all_intensity_label = tk.Label(
    all_frame,
    text="ALL INTENSITY",
    bg="#2f2f2f",
    fg="white",
    font=("Arial", 12)
)
all_intensity_label.pack(pady=(10, 3))

all_plus_button = tk.Button(
    all_frame,
    text="+",
    width=12,
    command=intensity_all_up
)
all_plus_button.pack(pady=3)

all_minus_button = tk.Button(
    all_frame,
    text="-",
    width=12,
    command=intensity_all_down
)
all_minus_button.pack(pady=3)


# Individual motor controls
for i in range(NUM_MOTORS):
    motor_name = f"Motor{i+1}"

    frame = tk.Frame(root, bg="#2f2f2f", padx=15, pady=15)
    frame.grid(row=1, column=i, padx=10, pady=10)

    motor_label = tk.Label(
        frame,
        text=motor_name,
        bg="#2f2f2f",
        fg="white",
        font=("Arial", 14)
    )
    motor_label.pack(pady=5)

    on_button = tk.Button(
        frame,
        text="ON",
        width=8,
        command=lambda name=motor_name: turn_motor_on(name)
    )
    on_button.pack(pady=3)

    off_button = tk.Button(
        frame,
        text="OFF",
        width=8,
        command=lambda name=motor_name: turn_motor_off(name)
    )
    off_button.pack(pady=3)

    intensity_label = tk.Label(
        frame,
        text="INTENSITY",
        bg="#2f2f2f",
        fg="white",
        font=("Arial", 12)
    )
    intensity_label.pack(pady=(10, 3))

    plus_button = tk.Button(
        frame,
        text="+",
        width=8,
        command=lambda name=motor_name: intensity_up(name)
    )
    plus_button.pack(pady=3)

    minus_button = tk.Button(
        frame,
        text="-",
        width=8,
        command=lambda name=motor_name: intensity_down(name)
    )
    minus_button.pack(pady=3)

root.mainloop()