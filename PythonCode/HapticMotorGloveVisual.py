import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

# Finds image in same folder as this Python file
BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "glove_clean.png"

MOTOR_OFF = "gray"
MOTOR_ON = "lime green"


class HapticGloveGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Haptic Glove Visual Motor Control")

        print("Looking for image at:", IMAGE_PATH)
        print("Image found:", IMAGE_PATH.exists())

        self.original_image = Image.open(IMAGE_PATH)

        self.display_width = 600
        self.display_height = 850

        self.resized_image = self.original_image.resize(
            (self.display_width, self.display_height)
        )

        self.glove_photo = ImageTk.PhotoImage(self.resized_image)

        self.canvas = tk.Canvas(
            root,
            width=self.display_width,
            height=self.display_height,
            bg="white"
        )
        self.canvas.pack()

        self.canvas.create_image(
            0,
            0,
            anchor="nw",
            image=self.glove_photo
        )

        self.motor_states = {}
        self.motor_circles = {}
        self.motor_labels = {}

        self.create_motors()

    def create_motors(self):
        # Adjust these x, y values until they line up with your image
        motor_positions = {
            1:  (145, 300),   # pinky top
            2:  (160, 360),   # pinky middle
            3:  (175, 430),   # pinky lower

            4:  (225, 200),   # ring top
            5:  (240, 270),   # ring middle
            6:  (250, 350),   # ring lower

            7:  (335, 190),   # middle top
            8:  (335, 260),   # middle middle
            9:  (325, 350),   # middle lower

            10: (450, 240),   # index top
            11: (425, 315),   # index middle
            12: (400, 380),   # index lower

            13: (515, 500),   # thumb
            # 14: (350, 380),   # palm/extra motor, not currenlty used but for additional motors if needed
        }

        for motor_id, (x, y) in motor_positions.items():
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

            self.canvas.tag_bind(
                circle,
                "<Button-1>",
                lambda event, m=motor_id: self.toggle_motor(m)
            )

            self.canvas.tag_bind(
                label,
                "<Button-1>",
                lambda event, m=motor_id: self.toggle_motor(m)
            )

    def toggle_motor(self, motor_id):
        self.motor_states[motor_id] = not self.motor_states[motor_id]

        if self.motor_states[motor_id]:
            self.canvas.itemconfig(self.motor_circles[motor_id], fill=MOTOR_ON)
            command = f"M{motor_id}:ON"
        else:
            self.canvas.itemconfig(self.motor_circles[motor_id], fill=MOTOR_OFF)
            command = f"M{motor_id}:OFF"

        print(command)
        self.send_motor_command(command)

    def send_motor_command(self, command):
        # Later this is where serial communication will go
        # Example:
        # serial_connection.write((command + "\n").encode())
        pass


if __name__ == "__main__":
    root = tk.Tk()
    app = HapticGloveGUI(root)
    root.mainloop()