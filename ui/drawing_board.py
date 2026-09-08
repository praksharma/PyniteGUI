import platform
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import *

from .layout.base import Layout
from .utils.figure_setup import drawing_board_init
from .triggers.on_move_triggers import on_move_snapping
from .triggers.on_click_triggers import on_click_tool_selection
from .layout.tools.shapes import add_shapes_menu

from Pynite import FEModel3D

def init_pynite_model():
    """
    A temporary function to load things with default values until they are implemented in the UI.
    """
    model = FEModel3D()
    # User-defined material
    material = "Steel_A992"
    E = 29_000  # ksi
    nu = 0.3
    G = E / (2 * (1 + nu)) # ksi
    rho = 0.49 / (12**3)   # kci

    # Add material to model
    model.add_material(name=material, E=E, G=G, nu=nu, rho=rho)

    # Arbitrarily chosen wide-flange section
    model.add_section("W18x35", A=10.3, Iy=15.3, Iz=510, J=0.506)
    return model

def pynite_post_implementation(model):
    """
    Function to run a full FEM analysis with predefined value post what we have already implemented
    """
    ### create nodes and members using the UI
    # then jump to load, supports and analysis
    # Pin support
    model.def_support(
        node_name="N1",
        support_DX=True,
        support_DY=True,
        support_DZ=True,
        support_RX=False,
        support_RY=False,
        support_RZ=False
    )

    # Roller support
    model.def_support(
        node_name="N2",
        support_DX=False,
        support_DY=True,
        support_DZ=True,
        support_RX=True,  # For stability
        support_RY=False,
        support_RZ=False
    )

    # Distributed dead load
    w_D = -0.120 / 12  # 0.12 klf to k/in

    # Distributed live load
    w_L =  -0.100 / 12  # 0.1 klf to k/in

    # Add dead load
    model.add_member_dist_load(
        member_name="M1",
        direction="Fy",
        w1=w_D,
        w2=w_D,
        x1=0,
        x2=35*12,  # 35 feet to inches
        case="D"
    )

    # Add live load
    model.add_member_dist_load(
        member_name="M1",
        direction="Fy",
        w1=w_L,
        w2=w_L,
        x1=0,
        x2=35*12,  # 35 feet to inches
        case="L"
    )

    # self_weight = factor * member.material.rho * member.section.A

    # Add self weight
    model.add_member_self_weight(global_direction="FY", factor=-1, case='SW')

    # Add load combinations
    model.add_load_combo(
        name="D+L",
        factors={"SW": 1.0, "D": 1.0, "L": 1.0},
        combo_tags="Service"
    )

    model.add_load_combo(
        name="1.2D+1.6L",
        factors={"SW": 1.2, "D": 1.2, "L": 1.6},
        combo_tags="Strength"
    )

    model.add_load_combo(
        name="Dead",
        factors={"SW": 1.0, "D": 1.0},
        combo_tags="Dead"
    )

    model.add_load_combo(
        name="Live",
        factors={"L": 1},
        combo_tags="Live"
    )

    model.add_load_combo(
        name="Self Wt",
        factors={"SW": 1},
        combo_tags="Self Weight"
    )

    model.analyze_linear(log=True, check_stability=True, check_statics=True)

if __name__ == "__main__":
    root = Tk()
    if platform.system() == "Linux":
        root.attributes("-zoomed", True)
    else:
        root.state("zoomed")

    # create the base class for layout
    layout = Layout(root)

    # Initialise pynite model
    model = init_pynite_model()

    # load drawing board
    # move settign like grid, max_lim and min_lim to a class
    grid = 0.1
    fig, ax = drawing_board_init()

    layout.top_frame_analysis_button(layout.structure_tab_top_frame, command = lambda: pynite_post_implementation(model))


    # figure triggers
    fig.canvas.mpl_connect('motion_notify_event', lambda event: 
                        on_move_snapping(event, fig, ax, grid))
    fig.canvas.mpl_connect('button_press_event', lambda event:
                        on_click_tool_selection(event, fig, ax, grid, model))

    canvas = FigureCanvasTkAgg(fig, master=layout.structure_tab)
    canvas.get_tk_widget().pack(fill="both", expand=True)
    root.mainloop()