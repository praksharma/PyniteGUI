"""
Support Panel Widget - STAAD.Pro-style support definition panel.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, Optional


class SupportDefinition:
    def __init__(self, name: str, support_type: str):
        self.name = name
        self.support_type = support_type  # "pin", "roller", "fixed"
        self.applied_to = []  # list of node names

    def __str__(self):
        return f"{self.name} ({self.support_type}) on {len(self.applied_to)} node(s)"


class SupportPanel:
    def __init__(self, parent: tk.Widget, on_support_selected: Optional[Callable] = None):
        self.parent = parent
        self.on_support_selected = on_support_selected
        self.supports: Dict[str, SupportDefinition] = {}
        self.current_support = None
        self._create_widgets()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        input_frame = ttk.LabelFrame(main_frame, text="Define Support")
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(input_frame, text="Name:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.name_var = tk.StringVar(value="Support1")
        ttk.Entry(input_frame, textvariable=self.name_var).grid(row=0, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(input_frame, text="Type:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.type_var = tk.StringVar(value="pin")
        ttk.Combobox(input_frame, textvariable=self.type_var, values=["pin", "roller", "fixed"], state="readonly").grid(row=1, column=1, padx=5, pady=2, sticky="ew")

        ttk.Button(input_frame, text="Define", command=self._add_support).grid(row=2, column=0, columnspan=2, padx=5, pady=5)

        list_frame = ttk.LabelFrame(main_frame, text="Applied Supports")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.support_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.support_listbox.yview)
        self.support_listbox.configure(yscrollcommand=scrollbar.set)
        self.support_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.support_listbox.bind('<<ListboxSelect>>', self._on_support_selected)

        ttk.Button(list_frame, text="Delete Selected", command=self._delete_selected).pack(fill=tk.X, padx=5, pady=5)
        self._refresh_list()

    def _add_support(self):
        name = self.name_var.get().strip()
        if not name:
            return
        if name in self.supports:
            if messagebox.askyesno("Duplicate", f"Replace existing '{name}'?"):
                self.supports[name] = SupportDefinition(name, self.type_var.get())
                self._refresh_list()
            return
        self.supports[name] = SupportDefinition(name, self.type_var.get())
        self._refresh_list()
        self.support_listbox.selection_clear(0, tk.END)
        idx = self.support_listbox.size() - 1
        self.support_listbox.selection_set(idx)

    def _refresh_list(self):
        self.support_listbox.delete(0, tk.END)
        for name in sorted(self.supports.keys()):
            self.support_listbox.insert(tk.END, str(self.supports[name]))

    def _on_support_selected(self, event=None):
        sel = self.support_listbox.curselection()
        if not sel:
            self.current_support = None
            return
        idx = sel[0]
        self.current_support = list(self.supports.values())[idx]
        if self.on_support_selected:
            self.on_support_selected(self.current_support)

    def _delete_selected(self):
        sel = self.support_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        name = list(self.supports.keys())[idx]
        if messagebox.askyesno("Confirm", f"Delete '{name}'?"):
            del self.supports[name]
            self._refresh_list()

    def add_node_to_support(self, node_name: str):
        """Add a node to the currently selected support's applied list."""
        if self.current_support:
            if node_name not in self.current_support.applied_to:
                self.current_support.applied_to.append(node_name)
                self._refresh_list()

    def get_current_support(self) -> Optional[SupportDefinition]:
        return self.current_support