from tkinter import Frame, Button
from .tools.shapes import add_shapes_menu

def create_top_frame(structure_tab):
    # Add a frame
    top_frame = Frame(structure_tab)
    top_frame.pack(side="top")

    return top_frame

def top_frame_shape_button(frame):
    # Add shape menu for selecting different shapes
    add_shapes_menu(frame)

def top_frame_analysis_button(frame, **kwargs):
    # temporary run analysis button unless other tabs are finished
    button_post_analysis = Button(frame, text = "Run analysis", **kwargs)# command = lambda: pynite_post_implementation(model))
    button_post_analysis.grid(row=0, column=4)

def drawing_board_frame(self, top_frame):
    board_controls_frame = Frame(top_frame)
    board_controls_frame.pack(side="top")