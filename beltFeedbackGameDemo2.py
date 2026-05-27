import tkinter as tk
import random
import time
import serial

# ---------------- SETTINGS ----------------

WINDOW_W = 900
WINDOW_H = 700

PLAYER_SIZE = 40
OBJECT_SIZE = 30
OBJECT_SPEED = 6
PLAYER_SPEED = 8
SPAWN_INTERVAL_MS = 700

SERIAL_PORT = "COM5"      # Change this to your ESP32/Arduino port
BAUD = 115200

MOTOR_INTENSITY = 180
MOTOR_DURATION = 300


# ---------------- BELT SERIAL CONTROL ----------------

class BeltController:
    def __init__(self):
        self.serial_conn = None

        try:
            self.serial_conn = serial.Serial(SERIAL_PORT, BAUD, timeout=0.1)
            time.sleep(2)
            print(f"Connected to {SERIAL_PORT}")
        except Exception as e:
            print("Serial connection failed:", e)

    def send_motor(self, motor_number):
        if not self.serial_conn:
            return

        command = f"TEST:START:M{motor_number}:{MOTOR_INTENSITY}:{MOTOR_DURATION}\n"

        try:
            self.serial_conn.write(command.encode())
            print(command.strip())
        except Exception as e:
            print("Serial write failed:", e)


# ---------------- GAME ----------------

class BeltGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Directional Haptic Belt Demo")

        self.canvas = tk.Canvas(root, width=WINDOW_W, height=WINDOW_H, bg="black")
        self.canvas.pack()

        self.belt = BeltController()

        self.player_x = WINDOW_W // 2
        self.player_y = WINDOW_H // 2

        self.keys_pressed = set()

        self.player = self.canvas.create_oval(
            self.player_x - PLAYER_SIZE,
            self.player_y - PLAYER_SIZE,
            self.player_x + PLAYER_SIZE,
            self.player_y + PLAYER_SIZE,
            fill="cyan"
        )

        self.objects = []
        self.score = 0
        self.last_spawn = time.time()

        self.score_text = self.canvas.create_text(
            100,
            30,
            fill="white",
            font=("Arial", 18, "bold"),
            text="Hits: 0"
        )

        self.controls_text = self.canvas.create_text(
            WINDOW_W // 2,
            30,
            fill="white",
            font=("Arial", 14, "bold"),
            text="Move: WASD or Arrow Keys"
        )

        self.mapping_text = self.canvas.create_text(
            WINDOW_W // 2,
            WINDOW_H - 30,
            fill="white",
            font=("Arial", 12),
            text="Mapping: Left=M1 | Top/Front=M2 | Right=M3 | Bottom/Back=M4"
        )

        self.root.bind("<KeyPress>", self.key_press)
        self.root.bind("<KeyRelease>", self.key_release)

        self.game_loop()

    # ---------------- PLAYER CONTROLS ----------------

    def key_press(self, event):
        self.keys_pressed.add(event.keysym.lower())

    def key_release(self, event):
        self.keys_pressed.discard(event.keysym.lower())

    def move_player(self):
        dx = 0
        dy = 0

        if "left" in self.keys_pressed or "a" in self.keys_pressed:
            dx -= PLAYER_SPEED
        if "right" in self.keys_pressed or "d" in self.keys_pressed:
            dx += PLAYER_SPEED
        if "up" in self.keys_pressed or "w" in self.keys_pressed:
            dy -= PLAYER_SPEED
        if "down" in self.keys_pressed or "s" in self.keys_pressed:
            dy += PLAYER_SPEED

        self.player_x += dx
        self.player_y += dy

        self.player_x = max(PLAYER_SIZE, min(WINDOW_W - PLAYER_SIZE, self.player_x))
        self.player_y = max(PLAYER_SIZE, min(WINDOW_H - PLAYER_SIZE, self.player_y))

        self.canvas.coords(
            self.player,
            self.player_x - PLAYER_SIZE,
            self.player_y - PLAYER_SIZE,
            self.player_x + PLAYER_SIZE,
            self.player_y + PLAYER_SIZE
        )

    # ---------------- SPAWN OBJECTS ----------------

    def spawn_object(self):
        side = random.choice(["left", "right", "top", "bottom"])

        if side == "left":
            x = -OBJECT_SIZE
            y = random.randint(0, WINDOW_H - OBJECT_SIZE)
            dx = OBJECT_SPEED
            dy = 0

        elif side == "right":
            x = WINDOW_W + OBJECT_SIZE
            y = random.randint(0, WINDOW_H - OBJECT_SIZE)
            dx = -OBJECT_SPEED
            dy = 0

        elif side == "top":
            x = random.randint(0, WINDOW_W - OBJECT_SIZE)
            y = -OBJECT_SIZE
            dx = 0
            dy = OBJECT_SPEED

        else:
            x = random.randint(0, WINDOW_W - OBJECT_SIZE)
            y = WINDOW_H + OBJECT_SIZE
            dx = 0
            dy = -OBJECT_SPEED

        obj = self.canvas.create_rectangle(
            x,
            y,
            x + OBJECT_SIZE,
            y + OBJECT_SIZE,
            fill="red"
        )

        self.objects.append({
            "id": obj,
            "x": x,
            "y": y,
            "dx": dx,
            "dy": dy,
            "side": side
        })

    # ---------------- COLLISION ----------------

    def check_collision(self, obj):
        px1 = self.player_x - PLAYER_SIZE
        py1 = self.player_y - PLAYER_SIZE
        px2 = self.player_x + PLAYER_SIZE
        py2 = self.player_y + PLAYER_SIZE

        ox1 = obj["x"]
        oy1 = obj["y"]
        ox2 = ox1 + OBJECT_SIZE
        oy2 = oy1 + OBJECT_SIZE

        return not (
            ox2 < px1 or
            ox1 > px2 or
            oy2 < py1 or
            oy1 > py2
        )

    # ---------------- MOTOR MAPPING ----------------

    def trigger_feedback(self, side):
        if side == "left":
            motor = 1
        elif side == "top":
            motor = 2
        elif side == "right":
            motor = 3
        else:
            motor = 4

        print(f"Hit from {side} -> Motor {motor}")
        self.belt.send_motor(motor)

    # ---------------- GAME LOOP ----------------

    def game_loop(self):
        self.move_player()

        now = time.time()

        if (now - self.last_spawn) * 1000 > SPAWN_INTERVAL_MS:
            self.spawn_object()
            self.last_spawn = now

        remove_list = []

        for obj in self.objects:
            obj["x"] += obj["dx"]
            obj["y"] += obj["dy"]

            self.canvas.coords(
                obj["id"],
                obj["x"],
                obj["y"],
                obj["x"] + OBJECT_SIZE,
                obj["y"] + OBJECT_SIZE
            )

            if self.check_collision(obj):
                self.trigger_feedback(obj["side"])
                remove_list.append(obj)
                self.score += 1

            elif (
                obj["x"] < -100 or
                obj["x"] > WINDOW_W + 100 or
                obj["y"] < -100 or
                obj["y"] > WINDOW_H + 100
            ):
                remove_list.append(obj)

        for obj in remove_list:
            try:
                self.canvas.delete(obj["id"])
                self.objects.remove(obj)
            except Exception:
                pass

        self.canvas.itemconfig(self.score_text, text=f"Hits: {self.score}")
        self.root.after(16, self.game_loop)


# ---------------- MAIN ----------------

if __name__ == "__main__":
    root = tk.Tk()
    app = BeltGame(root)
    root.mainloop()