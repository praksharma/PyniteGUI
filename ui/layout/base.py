from tkinter import ttk
from .structure_tab import create_top_frame, top_frame_shape_button, top_frame_analysis_button

class Layout():
    def __init__(self, root) -> None:
        """Initiliase the tabe

        Root: top level widget on screen
        """
        root.title("Direct Stiffness")
        # add tabs
        self.notebook = ttk.Notebook(root)

        #### ADD TABS #######
        self.structure_tab = ttk.Frame(self.notebook)
        self.materials_tab = ttk.Frame(self.notebook)
        self.sections_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.structure_tab, text="Structure")
        self.notebook.add(self.materials_tab, text="Materials")
        self.notebook.add(self.sections_tab, text="Section")
        self.notebook.pack(fill="both", expand= True)

        # init tab 1
        self.structure_tab_top_frame = create_top_frame(self.structure_tab)
        top_frame_shape_button(self.structure_tab_top_frame)
        self.top_frame_analysis_button = top_frame_analysis_button