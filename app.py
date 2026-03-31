import tkinter as tk
from tkinter import ttk

def say_hello():
    print("Hello from Tkinter!")

# Create the main window
root = tk.Tk()
root.title("Tkinter Test")
root.geometry("300x200")

# Add a label
label = ttk.Label(root, text="Welcome to Tkinter in VS Code!")
label.pack(pady=20)

# Add a button
button = ttk.Button(root, text="Click Me", command=say_hello)
button.pack(pady=20)

# Start the event loop
root.mainloop()
