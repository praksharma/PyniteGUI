import matplotlib.patches as patches

# init the variable variable
hover_square = None

def on_move_snapping(event,
                     fig,
                     ax,
                     grid: float,
                     
                     ):
    """
    Hints via snapping to show which node is selected.
    Only stores one hover_square and then hides it before the new one is calculated.
    """
    global hover_square
    if event.inaxes is None:
        return

    # Hide the previous snapping rectangle by toggling visibility
    if hover_square is not None:
        try:
            hover_square.set_visible(False)
        except Exception:
            pass
        hover_square = None
    
    # round off to grid before adding in
    x = round(event.xdata / grid) * grid
    y = round(event.ydata / grid) * grid

    # size of the rectangle is grid/5.
    rectangle_offset = grid / 5
    
    # Create new snapping rectangle
    hover_square = patches.Rectangle(
        (x - rectangle_offset/2, y - rectangle_offset/2),
        rectangle_offset,
        rectangle_offset,
        edgecolor='orange',
        facecolor='none'
    )

    ax.add_patch(hover_square)
    fig.canvas.draw_idle()