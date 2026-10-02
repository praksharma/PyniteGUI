import tkinter as tk
from tkinter import ttk
import sys

# Add parent directory to path for relative imports if necessary
sys.path.append('..')

from .structure_tab import create_top_frame, top_frame_shape_button


class Layout:
    def __init__(self, root, on_load_selected=None, on_support_selected=None) -> None:
        """
        Initializes the STAAD.Pro-style Split Layout:
        Left Pane: Tool Panels (Notebook for categories)
        Right Pane: Drawing Area (Fixed)
        
        Args:
            root: Root window
            on_load_selected: Callback function for when a load is selected
            on_support_selected: Callback function for when a support is selected
        """
        root.title("PyniteGUI - Structural Analysis")
        self.on_load_selected = on_load_selected
        self.on_support_selected = on_support_selected
        
        # Main Container
        self.root = root
        main_container = tk.PanedWindow(root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- LEFT PANE (Tool Panels) ---
        left_pane = tk.Frame(main_container, width=250, bg="#f0f0f0")
        main_container.add(left_pane, width=250)

        # Notebook for Panels (Loads, Materials, etc.)
        self.panel_notebook = ttk.Notebook(left_pane)
        self.panel_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 1. Structure Panel (Tree/List of nodes/members)
        self.structure_panel = ttk.Frame(self.panel_notebook)
        self.panel_notebook.add(self.structure_panel, text="Structure")
        self.create_structure_tree(self.structure_panel)

        # 2. Loads Panel (Definition & List)
        self.loads_panel = ttk.Frame(self.panel_notebook)
        self.panel_notebook.add(self.loads_panel, text="Loads & Supps")
        # We'll import the specific widget here to avoid circular imports
        self.create_loads_panel(self.loads_panel)

        # 3. Supports Panel
        self.supports_panel = ttk.Frame(self.panel_notebook)
        self.panel_notebook.add(self.supports_panel, text="Supports")
        self.create_supports_panel(self.supports_panel)

        # 4. Materials Panel (Placeholder)
        self.materials_panel = ttk.Frame(self.panel_notebook)
        self.panel_notebook.add(self.materials_panel, text="Materials")

        # --- RIGHT PANE (Drawing Area) ---
        right_pane = tk.Frame(main_container)
        main_container.add(right_pane)
        
        self.drawing_area = right_pane

    def create_structure_tree(self, parent):
        """Create the structure tree view (Nodes/Members list)"""
        tk.Label(parent, text="Structure Tree (Nodes/Members)", font=("Arial", 10, "bold")).pack(pady=5)
        
        # Create Treeview for nodes and members
        tree_frame = tk.Frame(parent, bg="white", relief=tk.SUNKEN)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create Treeview
        self.structure_tree = ttk.Treeview(
            tree_frame, 
            columns=("type", "id"), 
            show="headings",
            yscrollcommand=scrollbar.set
        )
        self.structure_tree.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.structure_tree.yview)
        
        # Define headings
        self.structure_tree.heading("type", text="Type")
        self.structure_tree.heading("id", text="ID/Name")
        
        # Set column widths
        self.structure_tree.column("type", width=80, anchor=tk.CENTER)
        self.structure_tree.column("id", width=150)
        
        # Initialize with empty state
        self.structure_tree.insert("", "end", values=("-", "-"))

    def create_loads_panel(self, parent):
        """Imports the Load Definition widget into the panel"""
        from ..widgets.load_panel import create_load_panel
        # Store the widget instance so DrawingBoard can update it
        self.load_panel_widget = create_load_panel(parent, on_load_selected=self.on_load_selected)

    def create_supports_panel(self, parent):
        """Imports the Support Definition widget into the panel"""
        from ..widgets.support_panel import SupportPanel
        # Store the widget instance so DrawingBoard can update it
        self.support_panel_widget = SupportPanel(parent, on_support_selected=self.on_support_selected)

    def refresh_structure_tree(self, model, extra_rows=None, markers=None):
        """Refresh the structure tree with current nodes, members, loads, supports.
        
        extra_rows: list of (type, label) tuples, e.g. [("Load", "Load1 @ N1")]
        markers: dict mapping entity name -> unicode marker string (e.g. "N1": "↓ △")
        """
        if not hasattr(self, 'structure_tree'):
            return
        markers = markers or {}
        
        # Clear existing items
        for item in self.structure_tree.get_children():
            self.structure_tree.delete(item)
        
        # Add nodes (with unicode markers if loads/supports are applied)
        for node_name in model.nodes:
            m = markers.get(node_name, "")
            self.structure_tree.insert("", "end", values=("Node", f"{node_name} {m}".rstrip()))
        
        # Add members (with unicode markers if loads are applied)
        for member_name in model.members:
            m = markers.get(member_name, "")
            self.structure_tree.insert("", "end", values=("Member", f"{member_name} {m}".rstrip()))
        
        # Add loads and supports if provided
        if extra_rows:
            for kind, label in extra_rows:
                self.structure_tree.insert("", "end", values=(kind, label))
        
        # Force tkinter to update
        if hasattr(self, 'root'):
            self.root.update_idletasks()