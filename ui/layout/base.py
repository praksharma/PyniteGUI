from tkinter import ttk

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