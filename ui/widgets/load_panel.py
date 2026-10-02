"""
Load Panel Widget - STAAD.Pro-style load definition panel.

This widget allows users to:
1. Define load cases/definitions (name, magnitude, direction)
2. List all defined loads
3. Select a load to apply it to the drawing area
4. Delete loads from the list
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, List, Optional


class LoadDefinition:
    """Represents a load definition that can be reused."""
    def __init__(self, name: str, magnitude: float, direction: str):
        self.name = name
        self.magnitude = magnitude
        self.direction = direction
    
    def __str__(self):
        return f"{self.name}: {self.magnitude} {self.direction}"


class LoadPanel:
    """
    Panel for defining and managing loads.
    
    This widget provides:
    - Input fields for magnitude and direction
    - A listbox to display defined loads
    - Buttons to add/delete loads
    - Callback when a load is selected
    """
    
    def __init__(self, parent: tk.Widget, on_load_selected: Optional[Callable] = None):
        """
        Initialize the load panel.
        
        Args:
            parent: Parent widget to attach this panel to
            on_load_selected: Callback function when a load is selected
                             Called with: on_load_selected(load_definition)
        """
        self.parent = parent
        self.on_load_selected = on_load_selected
        self.defined_loads: Dict[str, LoadDefinition] = {}  # name -> LoadDefinition
        self.current_load: Optional[LoadDefinition] = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create all widgets for the load panel."""
        # Main container
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Input frame for new load
        input_frame = ttk.LabelFrame(main_frame, text="Define New Load")
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Load name
        ttk.Label(input_frame, text="Name:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.name_var = tk.StringVar(value="Load1")
        self.name_entry = ttk.Entry(input_frame, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        
        # Magnitude
        ttk.Label(input_frame, text="Magnitude:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.magnitude_var = tk.StringVar(value="10.0")
        self.magnitude_entry = ttk.Entry(input_frame, textvariable=self.magnitude_var)
        self.magnitude_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        
        # Direction
        ttk.Label(input_frame, text="Direction:").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.direction_var = tk.StringVar(value="FY")
        self.direction_combo = ttk.Combobox(
            input_frame, 
            textvariable=self.direction_var,
            values=["FX", "FY", "FZ", "RX", "RY", "RZ"],
            state="readonly"
        )
        self.direction_combo.grid(row=2, column=1, padx=5, pady=2, sticky="ew")
        
        # Add button
        self.add_button = ttk.Button(
            input_frame, 
            text="Add Load",
            command=self._add_load
        )
        self.add_button.grid(row=3, column=0, columnspan=2, padx=5, pady=5)
        
        # List frame
        list_frame = ttk.LabelFrame(main_frame, text="Defined Loads")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Listbox to show all loads
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.load_listbox = tk.Listbox(list_container, selectmode=tk.SINGLE)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.load_listbox.yview)
        self.load_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.load_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind selection event
        self.load_listbox.bind('<<ListboxSelect>>', self._on_load_selected)
        
        # Buttons frame
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.delete_button = ttk.Button(
            btn_frame,
            text="Delete Selected",
            command=self._delete_selected_load
        )
        self.delete_button.pack(side=tk.RIGHT, padx=5)
        
        # Initialize empty
        self._refresh_list()
    
    def _add_load(self):
        """Add a new load definition."""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Load name cannot be empty")
            return
        
        try:
            magnitude = float(self.magnitude_var.get())
        except ValueError:
            messagebox.showerror("Error", "Magnitude must be a number")
            return
        
        direction = self.direction_var.get()
        
        # Check if load name already exists
        if name in self.defined_loads:
            if messagebox.askyesno("Duplicate Load", f"Load '{name}' already exists. Replace it?"):
                self._update_load(name, magnitude, direction)
            return
        
        # Add new load
        self._update_load(name, magnitude, direction)
        self._refresh_list()
        
        # Auto-select the new load
        self.load_listbox.selection_clear(0, tk.END)
        idx = self.load_listbox.size() - 1
        self.load_listbox.selection_set(idx)
        self.load_listbox.see(idx)
    
    def _update_load(self, name: str, magnitude: float, direction: str):
        """Update or add a load definition."""
        self.defined_loads[name] = LoadDefinition(name, magnitude, direction)
    
    def _refresh_list(self):
        """Refresh the listbox with current loads."""
        self.load_listbox.delete(0, tk.END)
        for name in sorted(self.defined_loads.keys()):
            self.load_listbox.insert(tk.END, str(self.defined_loads[name]))
    
    def _on_load_selected(self, event=None):
        """Handle load selection in listbox."""
        selection = self.load_listbox.curselection()
        if not selection:
            self.current_load = None
            return
        
        idx = selection[0]
        load_name = list(self.defined_loads.keys())[idx]
        self.current_load = self.defined_loads[load_name]
        
        # Notify callback
        if self.on_load_selected:
            self.on_load_selected(self.current_load)
    
    def _delete_selected_load(self):
        """Delete selected load."""
        selection = self.load_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        load_name = list(self.defined_loads.keys())[idx]
        
        if messagebox.askyesno("Confirm Delete", f"Delete load '{load_name}'?"):
            del self.defined_loads[load_name]
            self._refresh_list()
    
    def get_current_load(self) -> Optional[LoadDefinition]:
        """Get the currently selected load."""
        return self.current_load
    
    def get_all_loads(self) -> List[LoadDefinition]:
        """Get all defined loads."""
        return list(self.defined_loads.values())
    
    def clear_all(self):
        """Clear all defined loads."""
        if messagebox.askyesno("Clear All", "Clear all defined loads?"):
            self.defined_loads.clear()
            self._refresh_list()
            self.current_load = None


def create_load_panel(parent: tk.Widget, on_load_selected: Optional[Callable] = None) -> LoadPanel:
    """
    Factory function to create a load panel.
    
    Args:
        parent: Parent widget
        on_load_selected: Callback when a load is selected
    
    Returns:
        LoadPanel instance
    """
    panel = LoadPanel(parent, on_load_selected)
    return panel