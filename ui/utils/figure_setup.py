import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np

def drawing_board_init(grid: float = 0.1,
                       min_lim : float = 0,
                       max_lim : float = 1.0
                       ):
    """
    Draws a square drawing board with dimensions min_lim and max_lim
    grid: grid size. typicall set it to (max_lim - min_lim)/10
    """
    # Empty figure with just grid
    fig = Figure()
    ax = fig.add_subplot(111)
    # ticks to show the grid
    ax.set_xticks(np.arange(min_lim, max_lim + 0.01, grid))
    ax.set_yticks(np.arange(min_lim, max_lim + 0.01, grid))
    ax.grid(True)
    # Fix the x,y lim. else it will keep zooming-in to the view.
    # when the first thing is drawn
    ax.set_xlim(min_lim, max_lim)
    ax.set_ylim(min_lim, max_lim)
    ax.set_aspect('equal')

    return fig, ax