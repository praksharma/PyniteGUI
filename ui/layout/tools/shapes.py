from tkinter import ttk
from tkinter import Menu


def set_tool(tool_type, tool, tool_button):
    global active_tool
    active_tool = tool
    if tool_type == "Shapes":
        print("DEBUG: shape selected.")
        tool_button.config(text = f"{tool_type}: {tool}")

def add_shapes_menu(frame):
    shapes_button = ttk.Menubutton(frame, text="Shapes")
    shapes_menu = Menu(shapes_button, tearoff=True)

    shapes_menu.add_command(
        label="Line",
        command=lambda: set_tool("Shapes", "Line", shapes_button)
    )

    shapes_menu.add_command(
        label="Rectangle",
        command=lambda: set_tool("Shapes", "Rectangle", shapes_button)
    )

    shapes_button["menu"] = shapes_menu
    shapes_button.grid(row=1, column=0)