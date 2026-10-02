import platform
import tkinter as tk
from tkinter import messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from tkinter import Tk

from .layout.base import Layout
from .utils.figure_setup import drawing_board_init
from .triggers.on_move_triggers import on_move_snapping
from .triggers.on_click_triggers import on_click_tool_selection

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


class DrawingBoard:
    """
    Main drawing board application with load selection support.
    """
    # Unicode markers shown next to entities in the structure tree
    _DIR_ARROWS = {"FX": "→", "FY": "↓", "FZ": "⊙", "RX": "↺", "RY": "↻", "RZ": "⊖"}
    _SUP_ICONS = {"pin": "△", "roller": "○", "fixed": "▦"}
    
    def __init__(self, root, model):
        self.root = root
        self.model = model
        self.grid = 0.1
        self.fig, self.ax = drawing_board_init()
        self.current_load = None  # Currently selected load from panel
        self.current_support = None  # Currently selected support
        self.active_tool = "member"   # Default to member drawing
        self.status_var = tk.StringVar(value="Mode: Add Member (Click 2 points to create beam)")
        self.canvas_widget = None
        self.analysis_results = None
        self.deformed_scale = 1.0
        self.support_nodes = []  # list of (node_name, support_name)
        self.applied_loads = []  # list of ("Load", label) tuples
        self.layout = None  # Reference to layout object
        
        # Create layout
        self._create_layout()
    
    def _create_layout(self):
        """Set up the split pane layout."""
        # Create layout with callbacks for load and support selection
        self.layout = Layout(
            self.root, 
            on_load_selected=lambda load: self._activate_load_tool(load),
            on_support_selected=lambda support: self._on_support_selected(support)
        )
        
        # Get the drawing area frame from layout
        drawing_frame = self.layout.drawing_area
        
        # Add a status bar at the bottom
        status_frame = tk.Frame(drawing_frame, bg="#f0f0f0", height=25)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=2)
        status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(
            status_frame, 
            textvariable=self.status_var, 
            font=("Arial", 9),
            bg="#f0f0f0",
            anchor="w"
        )
        self.status_label.pack(fill=tk.X, side=tk.LEFT, padx=10)
        
        # Control buttons
        control_frame = tk.Frame(status_frame, bg="#f0f0f0")
        control_frame.pack(side=tk.RIGHT, padx=10)
        
        # Clear button
        clear_btn = tk.Button(
            control_frame, 
            text="Clear All", 
            command=self._clear_all,
            bg="#ffcccc",
            width=10
        )
        clear_btn.pack(side=tk.LEFT, padx=2)
        
        # Draw Member button
        member_btn = tk.Button(
            control_frame, 
            text="Draw Member", 
            command=self._activate_member_tool,
            bg="#e0e0e0",
            width=12
        )
        member_btn.pack(side=tk.LEFT, padx=2)
        
        # Apply Support button
        support_btn = tk.Button(
            control_frame, 
            text="Apply Support", 
            command=self._activate_support_tool,
            bg="#cce5ff",
            width=13
        )
        support_btn.pack(side=tk.LEFT, padx=2)
        
        # Place Load button
        load_btn = tk.Button(
            control_frame, 
            text="Place Load", 
            command=self._activate_load_button,
            bg="#ffe0e0",
            width=11
        )
        load_btn.pack(side=tk.LEFT, padx=2)
        
        # Run Analysis button
        analysis_btn = tk.Button(
            control_frame, 
            text="Run Analysis", 
            command=self._run_analysis,
            bg="#d4edda",
            width=13
        )
        analysis_btn.pack(side=tk.LEFT, padx=2)
        
        # View Deformed button
        deformed_btn = tk.Button(
            control_frame, 
            text="View Deformed", 
            command=self._view_deformed_shape,
            bg="#fff3cd",
            width=13
        )
        deformed_btn.pack(side=tk.LEFT, padx=2)
        
        # Create canvas - pack it to fill remaining space
        canvas = FigureCanvasTkAgg(self.fig, master=drawing_frame)
        self.canvas_widget = canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)
        
        # Store for access
        self.drawing_frame = drawing_frame
        
        # Connect canvas events AFTER widget is packed
        self._connect_events()

    def _clear_all(self):
        """Clear all nodes, members, loads, and supports."""
        if messagebox.askyesno("Confirm", "Clear all elements?"):
            self.model = FEModel3D()
            # Re-initialize with default material and section
            material = "Steel_A992"
            E = 29_000  # ksi
            nu = 0.3
            G = E / (2 * (1 + nu)) # ksi
            rho = 0.49 / (12**3)   # kci
            self.model.add_material(name=material, E=E, G=G, nu=nu, rho=rho)
            self.model.add_section("W18x35", A=10.3, Iy=15.3, Iz=510, J=0.506)
            
            # Clear canvas
            self.ax.clear()
            self.ax = self.fig.add_subplot(111)
            self.ax.set_xlim(0, 1.0)
            self.ax.set_ylim(0, 1.0)
            self.ax.grid(True)
            self.ax.set_aspect('equal')
            self.fig.canvas.draw_idle()
            
            self.analysis_results = None
            self.deformed_scale = 1.0
            self.support_nodes = []
            self.applied_loads = []
            self.status_var.set("Cleared. Mode: Add Member")
            self._refresh_structure_tree()
            print("[Clear] All elements cleared")

    def _activate_member_tool(self):
        """Switch to Member drawing mode."""
        self.active_tool = "member"
        self.current_load = None
        self.current_support = None
        self.status_var.set("Mode: Add Member (Click 2 points to create beam)")
        print("[Tool] Switched to Member Mode")

    def _activate_load_tool(self, load):
        """Switch to Point Load mode with a specific load."""
        self.active_tool = "point_load"
        self.current_load = load
        self.current_support = None
        self.status_var.set(f"Mode: Add Load '{load.name}' - Click node to apply")
        print(f"[Tool] Switched to Point Load Mode: {load}")

    def _activate_support_tool(self):
        """Switch to Support application mode."""
        self.active_tool = "apply_support"
        self.current_support = None
        self.current_load = None
        self.status_var.set("Mode: Apply Support - Select support first, then click node")
        print("[Tool] Switched to Support Application Mode")
    
    def _activate_load_button(self):
        """Activate point-load placement from the toolbar button."""
        load = self.current_load
        if load is None:
            # Fall back to the load currently selected in the panel
            lp = getattr(self.layout, 'load_panel_widget', None)
            if lp is not None and lp.current_load is not None:
                load = lp.current_load
            else:
                messagebox.showinfo(
                    "No Load Selected",
                    "Define a load in the 'Loads & Supps' tab and select it first."
                )
                return
        self._activate_load_tool(load)

    def _on_support_selected(self, support):
        """Handle support selection from panel."""
        self.current_support = support
        self.active_tool = "apply_support"
        self.status_var.set(f"Mode: Apply '{support.name}' - Click node to assign support")
        print(f"[Support] Selected: {support}")

    def _connect_events(self):
        """Connect matplotlib canvas events."""
        # Snapping on mouse move
        self.fig.canvas.mpl_connect(
            'motion_notify_event', 
            lambda event: on_move_snapping(event, self.fig, self.ax, self.grid)
        )
        
        # Mouse click
        self.fig.canvas.mpl_connect(
            'button_press_event', 
            self._on_canvas_click
        )
    
    def _on_canvas_click(self, event):
        """Handle canvas click events based on active tool."""
        if event.inaxes is None:
            return
        
        if self.active_tool == "member":
            on_click_tool_selection(event, self.fig, self.ax, self.grid, self.model)
            self._refresh_structure_tree()
            self.fig.canvas.draw_idle()
            
        elif self.active_tool == "point_load":
            self._place_point_load(event)
            self._refresh_structure_tree()
            self.fig.canvas.draw_idle()
            
        elif self.active_tool == "apply_support":
            self._apply_support(event)
            self._refresh_structure_tree()
            self.fig.canvas.draw_idle()
    
    def _refresh_structure_tree(self):
        """Refresh the structure tree in the left panel."""
        if not hasattr(self, 'layout') or self.layout is None:
            return
        # Build extra rows for applied loads and supports
        extra_rows = list(self.applied_loads)
        extra_rows += [("Support", f"{sup_name} @ {node_name}")
                       for (node_name, sup_name, _t) in self.support_nodes]
        self.layout.refresh_structure_tree(
            self.model, extra_rows=extra_rows, markers=self._build_markers()
        )
    
    def _end_name(self, end):
        """PyNite member.i_node/j_node may be a node OBJECT or a name string."""
        return end if isinstance(end, str) else end.name
    
    def _member_xy(self, member):
        """Return ((x1, y1), (x2, y2)) for a member's endpoints, safely."""
        pts = []
        for end in (member.i_node, member.j_node):
            node = self.model.nodes[end] if isinstance(end, str) else end
            pts.append((node.X, node.Y))
        return pts[0], pts[1]
    
    def _build_markers(self):
        """Build {entity_name: unicode_marker} for the structure tree."""
        markers = {}
        for _kind, label in self.applied_loads:
            # label format: "Load1 @ N1 (FY -10.0)" or "Load1 @ M1 (0.50 along, FY -10.0)"
            target = label.split(" @ ")[1].split(" ")[0]
            dirn = label.rsplit(" ", 2)[1]
            markers[target] = markers.get(target, "") + self._DIR_ARROWS.get(dirn, "•")
        for node_name, _sup, sup_type in self.support_nodes:
            markers[node_name] = markers.get(node_name, "") + self._SUP_ICONS.get(sup_type, "△")
        return markers
    
    def _nearest_node(self, x, y, tol):
        """Return name of nearest node within tol distance, else None."""
        best_name, best_dist = None, tol
        for name, node in self.model.nodes.items():
            d = ((node.X - x) ** 2 + (node.Y - y) ** 2) ** 0.5
            if d < best_dist:
                best_name, best_dist = name, d
        return best_name
    
    def _nearest_member(self, x, y, tol):
        """Return (member_name, distance, t) for nearest member within tol.
        
        t is the relative position along the member (0 = i_node, 1 = j_node).
        """
        best = None
        for name, member in self.model.members.items():
            (x1, y1), (x2, y2) = self._member_xy(member)
            dx, dy = x2 - x1, y2 - y1
            L2 = dx * dx + dy * dy
            if L2 == 0:
                continue
            # Project click onto member line, clamp to [0, 1]
            t = ((x - x1) * dx + (y - y1) * dy) / L2
            t = max(0.0, min(1.0, t))
            px, py = x1 + t * dx, y1 + t * dy
            d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            if d < tol and (best is None or d < best[1]):
                best = (name, d, t)
        return best
    
    def _apply_support(self, event):
        """Apply support to an EXISTING node near the click location."""
        if not self.current_support:
            messagebox.showwarning("Warning", "Please select a support from the Supports tab first!")
            return
        
        # Snap to grid
        x = round(event.xdata / self.grid) * self.grid
        y = round(event.ydata / self.grid) * self.grid
        tol = self.grid * 0.6
        
        # Find nearest existing node (never create floating nodes)
        node_name = self._nearest_node(x, y, tol)
        if node_name is None:
            messagebox.showwarning(
                "Warning",
                "Supports must be placed on an existing node.\nClick right on a node (red dot)."
            )
            return
        
        try:
            # Apply support based on type
            if self.current_support.support_type == "pin":
                self.model.def_support(
                    node_name=node_name,
                    support_DX=True, support_DY=True, support_DZ=True,
                    support_RX=False, support_RY=False, support_RZ=False
                )
            elif self.current_support.support_type == "roller":
                self.model.def_support(
                    node_name=node_name,
                    support_DX=False, support_DY=True, support_DZ=True,
                    support_RX=True, support_RY=False, support_RZ=False
                )
            else:  # fixed
                self.model.def_support(
                    node_name=node_name,
                    support_DX=True, support_DY=True, support_DZ=True,
                    support_RX=True, support_RY=True, support_RZ=True
                )
            
            # Track supported nodes
            if (node_name, self.current_support.name, self.current_support.support_type) not in self.support_nodes:
                self.support_nodes.append(
                    (node_name, self.current_support.name, self.current_support.support_type)
                )
            
            # Update support panel count
            if hasattr(self.layout, 'support_panel_widget'):
                self.layout.support_panel_widget.add_node_to_support(node_name)
            
            # Draw support indicator (triangle for pin, circle for roller)
            self._draw_support_indicator(event, x, y, self.current_support.support_type)
            
            print(f"[Support] Applied '{self.current_support.name}' to {node_name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply support: {str(e)}")
    
    def _draw_support_indicator(self, event, x, y, support_type):
        """Draw a compact support symbol just below the node."""
        from matplotlib.patches import Polygon, Circle, Rectangle
        green = 'green'
        if support_type == "pin":
            # Small triangle + base line
            tri = Polygon([(x - 0.03, y - 0.04), (x + 0.03, y - 0.04), (x, y - 0.08)],
                          fill=False, edgecolor=green, linewidth=1.5)
            event.inaxes.add_patch(tri)
            event.inaxes.plot([x - 0.035, x + 0.035], [y - 0.04, y - 0.04],
                              color=green, linewidth=1.5)
        elif support_type == "roller":
            # Small circle + ground line
            circ = Circle((x, y - 0.05), 0.02, fill=False, edgecolor=green, linewidth=1.5)
            event.inaxes.add_patch(circ)
            event.inaxes.plot([x - 0.05, x + 0.05], [y - 0.09, y - 0.09],
                              color=green, linewidth=1.5)
        else:  # fixed
            # Small filled block
            rect = Rectangle((x - 0.04, y - 0.08), 0.08, 0.04,
                             fill=True, facecolor=green, alpha=0.4,
                             edgecolor=green, linewidth=1.5)
            event.inaxes.add_patch(rect)

    def _place_point_load(self, event):
        """Place a point load: on the nearest node, or along the nearest member."""
        if not self.current_load:
            messagebox.showwarning("Warning", "Please select a load from the Loads tab first!")
            return
        
        # Snap to grid
        x = round(event.xdata / self.grid) * self.grid
        y = round(event.ydata / self.grid) * self.grid
        tol = self.grid * 0.6
        
        # --- Case 1: Near an existing node -> nodal load ---
        node_name = self._nearest_node(x, y, tol)
        if node_name is not None:
            try:
                # PyNite API: add_nodal_load(node_name, FX=0, FY=0, ...)
                load_kwargs = {self.current_load.direction: self.current_load.magnitude}
                self.model.add_nodal_load(node_name=node_name, **load_kwargs)
                
                self.applied_loads.append(
                    ("Load", f"{self.current_load.name} @ {node_name} ({self.current_load.direction} {self.current_load.magnitude})")
                )
                self._draw_load_arrow(event, x, y, self.current_load)
                print(f"[Load] Applied '{self.current_load.name}' to node {node_name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply load to {node_name}: {str(e)}")
            return
        
        # --- Case 2: Along a member -> member point load ---
        hit = self._nearest_member(x, y, tol)
        if hit is not None:
            member_name, dist, t = hit
            try:
                (x1, y1), (x2, y2) = self._member_xy(self.model.members[member_name])
                length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                # PyNite API: location is absolute distance from i_node
                self.model.add_member_point_load(
                    member_name,
                    self.current_load.direction,
                    self.current_load.magnitude,
                    t * length
                )
                
                self.applied_loads.append(
                    ("Load", f"{self.current_load.name} @ {member_name} ({t:.2f} along, {self.current_load.direction} {self.current_load.magnitude})")
                )
                self._draw_load_arrow(event, x, y, self.current_load)
                print(f"[Load] Applied '{self.current_load.name}' to member {member_name} at {t:.2f} along")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply load to {member_name}: {str(e)}")
            return
        
        # --- Case 3: Empty space ---
        messagebox.showwarning(
            "Warning",
            "Nothing there.\nClick on a node (red dot) or along a member to place the load."
        )
    
    def _draw_load_arrow(self, event, x, y, load):
        """Draw a visual representation of the load on the canvas,
        pointing in the direction of the load."""
        # Direction vectors for force loads (PyNite global +X right, +Y up)
        vectors = {"FX": (1, 0), "FY": (0, 1), "FZ": (0, 0),
                   "RX": (0, 0), "RY": (0, 0), "RZ": (0, 0)}
        dx, dy = vectors.get(load.direction, (0, 0))
        
        if dx != 0 or dy != 0:
            # Force: draw arrow in load direction
            arrow = FancyArrowPatch(
                (x, y), (x + dx * 0.5, y + dy * 0.5),
                arrowstyle='->,head_width=0.08,head_length=0.06',
                color='red', linewidth=2
            )
            event.inaxes.add_patch(arrow)
            label_pos = (x, y - 0.3) if dy != 0 else (x + 0.35, y)
        else:
            # Moment: draw a hollow circle marker
            event.inaxes.plot([x], [y], 'ro', markersize=12,
                              fillstyle='none', markeredgewidth=2)
            label_pos = (x, y - 0.3)
        
        # Add label
        event.inaxes.text(
            label_pos[0], label_pos[1],
            f"{load.magnitude:g} {load.direction}",
            color='red',
            fontsize=10,
            ha='center',
            fontweight='bold'
        )

    def _run_analysis(self):
        """Run the FEM analysis."""
        if len(self.model.nodes) < 2:
            messagebox.showwarning("Warning", "Need at least 2 nodes to analyze!")
            return
        
        if len(self.support_nodes) < 1:
            messagebox.showwarning("Warning", "Need at least 1 support to analyze!")
            return
        
        try:
            # Run analysis
            self.model.analyze_linear(log=True, check_stability=True, check_statics=True)
            self.analysis_results = True
            self.status_var.set("✓ Analysis Complete")
            print("[Analysis] Analysis completed successfully!")
            
            # Show success message
            messagebox.showinfo("Analysis", f"Analysis complete!\nNodes: {len(self.model.nodes)}\nMembers: {len(self.model.members)}\nSupports: {len(self.support_nodes)}")
            
        except Exception as e:
            self.status_var.set(f"✗ Analysis Failed")
            messagebox.showerror("Error", f"Analysis failed:\n{str(e)}")
            print(f"[Analysis] Error: {e}")
    
    def _view_deformed_shape(self):
        """Display the deformed shape of the structure."""
        if not self.analysis_results:
            messagebox.showwarning("Warning", "Please run analysis first!")
            return
        
        try:
            scale = self.deformed_scale
            names = list(self.model.nodes.keys())
            idx = {n: i for i, n in enumerate(names)}
            
            # Original and deformed coordinates
            # PyNite stores displacements as node.UX / node.UY after analysis
            orig, deformed = [], []
            for n in names:
                node = self.model.nodes[n]
                ux = getattr(node, 'UX', 0) or 0
                uy = getattr(node, 'UY', 0) or 0
                orig.append((node.X, node.Y))
                deformed.append((node.X + ux * scale, node.Y + uy * scale))
            
            deformed_fig, deformed_ax = plt.subplots(figsize=(10, 8))
            
            # Original (gray dashed) and deformed (red) members
            first = True
            for m in self.model.members.values():
                i = idx[self._end_name(m.i_node)]
                j = idx[self._end_name(m.j_node)]
                deformed_ax.plot([orig[i][0], orig[j][0]], [orig[i][1], orig[j][1]],
                                 'gray', linewidth=1, alpha=0.4, linestyle='--')
                deformed_ax.plot([deformed[i][0], deformed[j][0]],
                                 [deformed[i][1], deformed[j][1]],
                                 'r-', linewidth=3,
                                 label='Deformed shape' if first else None)
                first = False
            
            # Draw supports on deformed shape
            for node_name, _sup, _t in self.support_nodes:
                i = idx[node_name]
                deformed_ax.plot(deformed[i][0], deformed[i][1], 'g^', markersize=12)
            
            # Draw nodes
            for c in deformed:
                deformed_ax.plot(c[0], c[1], 'ko', markersize=5)
            
            deformed_ax.set_title('Deformed Shape of Structure', fontsize=14, fontweight='bold')
            deformed_ax.set_xlabel('X Position', fontsize=12)
            deformed_ax.set_ylabel('Y Position', fontsize=12)
            deformed_ax.grid(True, alpha=0.3)
            deformed_ax.set_aspect('equal')
            deformed_ax.legend()
            deformed_fig.tight_layout()
            plt.show()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to display deformed shape:\n{e!r}")
    
    def run_mainloop(self):
        """Start the application main loop."""
        self.root.mainloop()


if __name__ == "__main__":
    root = Tk()
    if platform.system() == "Linux":
        root.attributes("-zoomed", True)
    else:
        root.state("zoomed")

    # Initialise pynite model
    model = init_pynite_model()

    # Create drawing board
    board = DrawingBoard(root, model)
    
    board.run_mainloop()