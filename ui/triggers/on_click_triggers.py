from ..pynite_wiring.nodes import  get_or_create_nodes

# a variable to hold points
points = []
member_number = 1

def on_click_tool_selection(event, fig, ax, grid, model):
    """
    Handles node creation and member drawing.
    1st Click: Creates Node 1 (visual feedback: red dot)
    2nd Click: Creates Node 2 & Member (visual feedback: line + 2 red dots)
    """
    # global numbers
    global member_number

    if event.inaxes is None:
        return
    
    # Snap to grid
    x = round(event.xdata / grid) * grid
    y = round(event.ydata / grid) * grid
    
    # Add point to buffer
    points.append((x, y))
    
    # Draw a marker for the node immediately so user sees it
    ax.plot([x], [y], 'ro', markersize=8)  # 'ro' = red dot
    fig.canvas.draw_idle()

    # Check if we have 2 points to form a member
    if len(points) == 2:
        (x1, y1), (x2, y2) = points
        
        if (x1, y1) == (x2, y2):
            print("Not a line. You selected the same coordinate twice.")
            points.clear()
        else:
            # Draw the member line
            ax.plot([x1, x2], [y1, y2], 'k-', linewidth=2)
            fig.canvas.draw_idle()

            # Create PyNite nodes and member
            i_node = get_or_create_nodes(model, x1, y1)
            j_node = get_or_create_nodes(model, x2, y2)

            model.add_member(
                f"M{member_number}",
                i_node=i_node,
                j_node=j_node,
                material_name="Steel_A992",
                section_name="W18x35",
            )

            print(f"DEBUG: Member M{member_number} created")
            member_number += 1
            
            # Reset for next member
            points.clear()