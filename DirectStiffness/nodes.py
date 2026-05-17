class Node():
    def __init__(self, id, x, y) -> None:
        self.id = id
        self.x = x
        self.y = y
    def __str__(self):
        """A string returned when printing the object."""
        return f"Node ID: {self.id}"
    def __repr__(self):
        "Give more information about the object for development purpose."
        return f"Node(ID={self.id}, x={self.x}, y={self.y})"