"""
Belt Feedback Game Demo
-----------------------
A simple Tkinter game for testing a 4-motor haptic feedback belt.

Works with your existing Arduino command format:
    TEST:START:M1:180:150
    TEST:START:M1,M2,M3,M4:255:300
    TEST:STOP
    STATUS

Controls:
    Arrow keys / WASD = move player
    Space = stop motors
    R = reset game

Motor mapping used in this demo:
    M1 = front-left feedback
    M2 = front-right feedback
    M3 = back-left feedback
    M4 = back-right feedback

You can change the mapping in the MOTOR_GROUPS dictionary.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import random
import time


class BeltFeedbackGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Belt Feedback Game Demo")
        self.root.configure(bg="#202020")

        # ---------------- Serial / belt settings ----------------
        self.serial_conn = None
        self.baud_rate = 115200
        self.last_feedback_time = 0.0
        self.feedback_cooldown_s = 0.12

        # Motor mapping for a 4-motor belt
        self.MOTOR_GROUPS = {
            "front": [1, 2],
            "back": [3, 4],
            "left": [1, 3],
            "right": [2, 4],
            "front_left": [1],
            "front_right": [2],
            "back_left": [3],
            "back_right": [4],
            "all": [1, 2, 3, 4],
        }

        # ---------------- Game settings ----------------
        self.canvas_width = 700
        self.canvas_height = 450
        self.player_size = 28
        self.player_speed = 10
        self.obstacle_count = 7
        self.obstacle_size = 42
        self.warning_distance = 85

        self.score = 0
        self.game_running = True
        self.player = None
        self.goal = None
        self.obstacles = []
        self.keys_down = set()

        self.build_ui()
        self.refresh_ports()
        self.reset_game()

        self.root.bind("<KeyPress>", self.on_key_press)
        self.root.bind("<KeyRelease>", self.on_key_release)
        self.game_loop()

    # ---------------- UI ----------------

    def build_ui(self):
        title = tk.Label(
            self.root,
            text="Belt Feedback Game Demo",
            bg="#202020",
            fg="white",
            font=("Arial", 18, "bold"),
        )
        title.pack(pady=(12, 4))

        subtitle = tk.Label(
            self.root,
            text="Move the blue square to the green goal. Obstacles trigger directional belt feedback.",
            bg="#202020",
            fg="#cccccc",
            font=("Arial", 10),
        )
        subtitle.pack(pady=(0, 10))

        top_frame = tk.Frame(self.root, bg="#202020")
        top_frame.pack(fill="x", padx=12, pady=(0, 8))

        connection_frame = tk.LabelFrame(
            top_frame,
            text="Belt Connection",
            bg="#202020",
            fg="white",
            padx=10,
            pady=8,
        )
        connection_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))

        tk.Label(connection_frame, text="Serial Port", bg="#202020", fg="white").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(connection_frame, state="readonly", width=18)
        self.port_combo.grid(row=0, column=1, padx=6)

        tk.Button(connection_frame, text="Refresh", command=self.refresh_ports, width=10).grid(row=0, column=2, padx=4)
        tk.Button(connection_frame, text="Connect", command=self.connect_serial, width=10).grid(row=0, column=3, padx=4)
        tk.Button(connection_frame, text="Disconnect", command=self.disconnect_serial, width=10).grid(row=0, column=4, padx=4)

        self.connection_label = tk.Label(
            connection_frame,
            text="Disconnected",
            bg="#202020",
            fg="red",
            font=("Arial", 10, "bold"),
        )
        self.connection_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        settings_frame = tk.LabelFrame(
            top_frame,
            text="Feedback Settings",
            bg="#202020",
            fg="white",
            padx=10,
            pady=8,
        )
        settings_frame.pack(side="left", fill="x", expand=True, padx=(8, 0))

        tk.Label(settings_frame, text="Intensity", bg="#202020", fg="white").grid(row=0, column=0, sticky="w")
        self.intensity_var = tk.StringVar(value="180")
        tk.Entry(settings_frame, textvariable=self.intensity_var, width=8).grid(row=0, column=1, padx=6)

        tk.Label(settings_frame, text="Pulse ms", bg="#202020", fg="white").grid(row=0, column=2, sticky="w")
        self.pulse_ms_var = tk.StringVar(value="150")
        tk.Entry(settings_frame, textvariable=self.pulse_ms_var, width=8).grid(row=0, column=3, padx=6)

        tk.Label(settings_frame, text="Warning Distance", bg="#202020", fg="white").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.warning_distance_var = tk.StringVar(value=str(self.warning_distance))
        tk.Entry(settings_frame, textvariable=self.warning_distance_var, width=8).grid(row=1, column=1, padx=6, pady=(6, 0))

        tk.Button(settings_frame, text="Stop Motors", command=self.stop_motors, width=12).grid(row=1, column=2, padx=4, pady=(6, 0))
        tk.Button(settings_frame, text="Reset Game", command=self.reset_game, width=12).grid(row=1, column=3, padx=4, pady=(6, 0))

        manual_frame = tk.LabelFrame(
            self.root,
            text="Manual Belt Test",
            bg="#202020",
            fg="white",
            padx=10,
            pady=8,
        )
        manual_frame.pack(fill="x", padx=12, pady=(0, 8))

        buttons = [
            ("Front", "front"),
            ("Back", "back"),
            ("Left", "left"),
            ("Right", "right"),
            ("Front Left", "front_left"),
            ("Front Right", "front_right"),
            ("Back Left", "back_left"),
            ("Back Right", "back_right"),
            ("All", "all"),
        ]

        for idx, (label, group) in enumerate(buttons):
            tk.Button(
                manual_frame,
                text=label,
                width=11,
                command=lambda g=group: self.trigger_feedback(g, force=True),
            ).grid(row=0, column=idx, padx=3, pady=3)

        info_frame = tk.Frame(self.root, bg="#202020")
        info_frame.pack(fill="x", padx=12, pady=(0, 6))

        self.score_label = tk.Label(
            info_frame,
            text="Score: 0",
            bg="#202020",
            fg="#00d7ff",
            font=("Arial", 12, "bold"),
        )
        self.score_label.pack(side="left")

        self.status_label = tk.Label(
            info_frame,
            text="Use Arrow Keys or WASD to move. Avoid red blocks. Reach green goal.",
            bg="#202020",
            fg="white",
            font=("Arial", 10),
        )
        self.status_label.pack(side="right")

        self.canvas = tk.Canvas(
            self.root,
            width=self.canvas_width,
            height=self.canvas_height,
            bg="#111111",
            highlightthickness=2,
            highlightbackground="#444444",
        )
        self.canvas.pack(padx=12, pady=(0, 12))

    # ---------------- Serial helpers ----------------

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
            self.serial_conn = serial.Serial(port, self.baud_rate, timeout=0.2)
            time.sleep(2)
            self.connection_label.config(text=f"Connected: {port}", fg="lime")
            self.send_command("PING")
            self.send_command("STATUS")
        except Exception as e:
            self.serial_conn = None
            self.connection_label.config(text="Disconnected", fg="red")
            messagebox.showerror("Connection Error", str(e))

    def disconnect_serial(self):
        self.stop_motors()
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.serial_conn = None
        self.connection_label.config(text="Disconnected", fg="red")

    def send_command(self, cmd):
        if not self.serial_conn or not self.serial_conn.is_open:
            return False
        try:
            self.serial_conn.write((cmd + "\n").encode())
            return True
        except Exception:
            return False

    def stop_motors(self):
        self.send_command("TEST:STOP")

    def get_intensity(self):
        try:
            value = int(self.intensity_var.get().strip())
        except ValueError:
            value = 180
        return max(0, min(255, value))

    def get_pulse_ms(self):
        try:
            value = int(self.pulse_ms_var.get().strip())
        except ValueError:
            value = 150
        return max(20, min(2000, value))

    def trigger_feedback(self, group_name, force=False):
        now = time.time()
        if not force and now - self.last_feedback_time < self.feedback_cooldown_s:
            return

        motors = self.MOTOR_GROUPS.get(group_name, [])
        if not motors:
            return

        motor_string = ",".join(f"M{m}" for m in motors)
        intensity = self.get_intensity()
        pulse_ms = self.get_pulse_ms()

        self.send_command(f"TEST:START:{motor_string}:{intensity}:{pulse_ms}")
        self.last_feedback_time = now

    # ---------------- Game setup ----------------

    def reset_game(self):
        self.canvas.delete("all")
        self.obstacles = []
        self.keys_down.clear()
        self.game_running = True

        self.score_label.config(text=f"Score: {self.score}")
        self.status_label.config(text="Use Arrow Keys or WASD to move. Avoid red blocks. Reach green goal.")

        start_x = 40
        start_y = self.canvas_height // 2
        self.player = self.canvas.create_rectangle(
            start_x,
            start_y,
            start_x + self.player_size,
            start_y + self.player_size,
            fill="#00aaff",
            outline="white",
            width=2,
        )

        goal_x = self.canvas_width - 70
        goal_y = self.canvas_height // 2 - 25
        self.goal = self.canvas.create_rectangle(
            goal_x,
            goal_y,
            goal_x + 50,
            goal_y + 50,
            fill="#00cc66",
            outline="white",
            width=2,
        )

        self.canvas.create_text(
            goal_x + 25,
            goal_y + 25,
            text="GOAL",
            fill="white",
            font=("Arial", 9, "bold"),
        )

        self.create_obstacles()

    def create_obstacles(self):
        for _ in range(self.obstacle_count):
            placed = False
            tries = 0
            while not placed and tries < 100:
                tries += 1
                x = random.randint(130, self.canvas_width - 170)
                y = random.randint(30, self.canvas_height - 80)
                box = (x, y, x + self.obstacle_size, y + self.obstacle_size)

                if not self.overlaps_start_or_goal(box):
                    obstacle = self.canvas.create_rectangle(
                        *box,
                        fill="#cc3333",
                        outline="#ff9999",
                        width=2,
                    )
                    self.obstacles.append(obstacle)
                    placed = True

    def overlaps_start_or_goal(self, box):
        x1, y1, x2, y2 = box
        start_zone = (0, 0, 110, self.canvas_height)
        goal_zone = (self.canvas_width - 130, 0, self.canvas_width, self.canvas_height)
        return self.boxes_overlap(box, start_zone) or self.boxes_overlap(box, goal_zone)

    # ---------------- Game input ----------------

    def on_key_press(self, event):
        key = event.keysym.lower()
        self.keys_down.add(key)

        if key == "space":
            self.stop_motors()
        elif key == "r":
            self.reset_game()

    def on_key_release(self, event):
        key = event.keysym.lower()
        if key in self.keys_down:
            self.keys_down.remove(key)

    # ---------------- Game loop ----------------

    def game_loop(self):
        if self.game_running:
            self.update_player_position()
            self.check_goal()
            self.check_obstacle_feedback()

        self.root.after(35, self.game_loop)

    def update_player_position(self):
        dx = 0
        dy = 0

        if "left" in self.keys_down or "a" in self.keys_down:
            dx -= self.player_speed
        if "right" in self.keys_down or "d" in self.keys_down:
            dx += self.player_speed
        if "up" in self.keys_down or "w" in self.keys_down:
            dy -= self.player_speed
        if "down" in self.keys_down or "s" in self.keys_down:
            dy += self.player_speed

        if dx == 0 and dy == 0:
            return

        px1, py1, px2, py2 = self.canvas.coords(self.player)
        new_box = (px1 + dx, py1 + dy, px2 + dx, py2 + dy)

        if new_box[0] < 0 or new_box[2] > self.canvas_width:
            dx = 0
            self.trigger_feedback("left" if new_box[0] < 0 else "right")
        if new_box[1] < 0 or new_box[3] > self.canvas_height:
            dy = 0
            self.trigger_feedback("front" if new_box[1] < 0 else "back")

        self.canvas.move(self.player, dx, dy)

    def check_goal(self):
        player_box = self.canvas.coords(self.player)
        goal_box = self.canvas.coords(self.goal)

        if self.boxes_overlap(player_box, goal_box):
            self.score += 1
            self.score_label.config(text=f"Score: {self.score}")
            self.status_label.config(text="Goal reached. Full-belt success pulse sent.")
            self.trigger_feedback("all", force=True)
            self.root.after(450, self.reset_game)

    def check_obstacle_feedback(self):
        player_box = self.canvas.coords(self.player)
        player_center = self.center_of_box(player_box)

        closest_obstacle = None
        closest_distance = 999999

        for obstacle in self.obstacles:
            obstacle_box = self.canvas.coords(obstacle)

            if self.boxes_overlap(player_box, obstacle_box):
                self.status_label.config(text="Collision. Strong full-belt pulse sent.")
                self.trigger_feedback("all", force=True)
                self.push_player_away(player_box, obstacle_box)
                return

            obstacle_center = self.center_of_box(obstacle_box)
            distance = self.distance(player_center, obstacle_center)
            if distance < closest_distance:
                closest_distance = distance
                closest_obstacle = obstacle_box

        try:
            self.warning_distance = int(self.warning_distance_var.get().strip())
        except ValueError:
            self.warning_distance = 85

        if closest_obstacle and closest_distance <= self.warning_distance:
            direction = self.direction_from_player_to_obstacle(player_box, closest_obstacle)
            self.status_label.config(text=f"Obstacle nearby: {direction.replace('_', ' ')} feedback")
            self.trigger_feedback(direction)

    def push_player_away(self, player_box, obstacle_box):
        px = (player_box[0] + player_box[2]) / 2
        py = (player_box[1] + player_box[3]) / 2
        ox = (obstacle_box[0] + obstacle_box[2]) / 2
        oy = (obstacle_box[1] + obstacle_box[3]) / 2

        dx = 20 if px > ox else -20
        dy = 20 if py > oy else -20

        self.canvas.move(self.player, dx, dy)

    # ---------------- Geometry helpers ----------------

    def boxes_overlap(self, a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1

    def center_of_box(self, box):
        x1, y1, x2, y2 = box
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    def distance(self, p1, p2):
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

    def direction_from_player_to_obstacle(self, player_box, obstacle_box):
        px, py = self.center_of_box(player_box)
        ox, oy = self.center_of_box(obstacle_box)

        dx = ox - px
        dy = oy - py

        if abs(dx) > abs(dy):
            return "right" if dx > 0 else "left"
        else:
            return "back" if dy > 0 else "front"

    def on_close(self):
        self.stop_motors()
        self.disconnect_serial()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = BeltFeedbackGame(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
