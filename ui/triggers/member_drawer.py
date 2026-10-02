"""
Member Drawer - Handles the creation of structural members (lines).

Workflow:
1. Click canvas -> sets point A
2. Click canvas again -> draws line A-B, creates nodes/member in model
3. Resets for next member
"""

class MemberDrawer:
    def __init__(self):
        self.points = []
        
    def click(self, event, grid, model, fig, ax):
        """Handle a canvas click for drawing a member."""
        if event.inaxes is None:
            return
            
        # Import here to avoid circular imports
        from ..pynite_wiring.nodes import get_or_create_nodes
            
        # Snap to grid
        x = round(event.xdata / grid) * grid
        y = round(event.ydata / grid) * grid
        
        self.points.append((x, y))
        
        if len(self.points) == 2:
            (x1, y1), (x2, y2) = self.points
            
            if (x1, y1) == (x2, y2):
                print("[Draw] Duplicate point detected. Skipping.")
                self.points = []
                return
            
            # Draw line on canvas
            ax.plot([x1, x2], [y1, y2], 'k-', linewidth=2)
            fig.canvas.draw_idle()
            
            # Add to PyNite model
            try:
                node1_id = get_or_create_nodes(model, x1, y1)
                node2_id = get_or_create_nodes(model, x2, y2)
                
                node1_name = f"NODE_{node1_id}"
                node2_name = f"NODE_{node2_id}"
                
                # Default properties for the drawn member
                model.add_member(
                    f"M{len(model.members) + 1}",
                    node1_name, 
                    node2_name,
                    material_name="Steel_A992",
                    section_name="W18x35"
                )
                
                print(f"[Draw] Member created: {node1_name} -> {node2_name}")
                
            except Exception as e:
                print(f"[Draw] Error creating member: {e}")
            
            # Reset for next member
            self.points = []