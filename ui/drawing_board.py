import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
import matplotlib.patches as patches
from matplotlib.backend_bases import MouseButton
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import *

root = Tk()
root.state("zoomed")    
root.title("Direct Stiffness")



points = []
grid = 0.1
fig = Figure()
ax = fig.add_subplot(111)
ax.set_xticks(np.arange(0, 1.01, grid))
ax.set_yticks(np.arange(0, 1.01, grid))
ax.grid(True)
ax.set_xlim(0, 1.0)
ax.set_ylim(0, 1.0)
ax.set_aspect('equal')

def add_element(points):
    # fem backend
    pass

def on_click(event):
    if event.inaxes is None:
        return
    # round off to grid before adding in
    x = round(event.xdata / grid) * grid
    y = round(event.ydata / grid) * grid
    points.append((x, y))
    
    # need two point to create a line
    # flush everything else
    if len(points) == 2:
        (x1, y1), (x2, y2) = points
        if (x1, y1) == (x2, y2):
            print("Not a line. You selected the same coordinate twice.")

        else:
            ax.plot([x1, x2], [y1, y2], 'k-')
            fig.canvas.draw_idle()

        points.clear()

hover_square = None
def on_move(event):
    global hover_square
    if event.inaxes is None:
        return

    # remove all previous snapping rectangles
    if hover_square is not None:
        hover_square.remove()
    # round off to grid before adding in
    x = round(event.xdata / grid) * grid
    y = round(event.ydata / grid) * grid

    rectangle_offset = grid / 5
    hover_square = patches.Rectangle(
        (x - rectangle_offset/2, y - rectangle_offset/2),
        rectangle_offset,
        rectangle_offset,
        edgecolor='orange',
        facecolor='none'
    )

    ax.add_patch(hover_square)
    fig.canvas.draw_idle()

        
fig.canvas.mpl_connect('motion_notify_event', on_move)
fig.canvas.mpl_connect('button_press_event', on_click)

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill="both", expand=True)
root.mainloop()