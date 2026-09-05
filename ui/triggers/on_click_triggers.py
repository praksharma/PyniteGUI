from ..pynite_wiring.nodes import  get_or_create_nodes

# a variable to hold points
points = []
member_number = 1

def on_click_tool_selection(event,fig, ax, grid, model):
    # global numbers
    global member_number

    # print("DEBUG: Node number ", node_number)
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

            ####### Add a node/ members for each point
            # only when all the checks are clear (meaning inside this else)
            # and the lines are legal line

            i_node = get_or_create_nodes(model, x1, y1)
            j_node = get_or_create_nodes(model, x2, y2)

            model.add_member(
                f"M{member_number}",
                i_node=i_node,
                j_node=j_node,
                material_name="Steel_A992",
                section_name="W18x35",
            )

            print("DEBUG: Member created: ", model.members[f"M{member_number}"])
            member_number += 1
            # empty the points list
            points.clear()