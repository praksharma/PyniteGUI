from tkinter import ttk
from tkinter import *


def set_tool(tool_type, tool):
    pass
def add_support_menu(root):
    support_button = ttk.Menubutton(root, text="Support")
    support_menu = Menu(support_button, tearoff=True)

    support_menu.add_command(
        label="Fixed",
        command=lambda: set_tool("support", "fixed")
    )

    support_menu.add_command(
        label="Pin",
        command=lambda: set_tool("support", "pin")
    )

    support_menu.add_command(
        label="Roller X",
        command=lambda: set_tool("support", "roller_x")
    )


