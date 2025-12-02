"""
Visual Block Diagram Editor

This module provides a drag-and-drop canvas for defining how schematic sheets
are connected in reliability terms (series, parallel, k-of-n redundancy).
"""

import wx
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Any
from enum import Enum


class ConnectionType(Enum):
    """Types of reliability connections between blocks."""
    SERIES = "series"
    PARALLEL = "parallel"
    K_OF_N = "k_of_n"


@dataclass
class BlockNode:
    """Represents a sheet/block in the reliability diagram."""
    id: str
    name: str
    display_name: str
    x: int = 0
    y: int = 0
    width: int = 160
    height: int = 60
    reliability: float = 1.0
    lambda_val: float = 0.0
    is_group: bool = False
    children: List[str] = field(default_factory=list)
    connection_type: ConnectionType = ConnectionType.SERIES
    k_value: int = 2  # For k-of-n connections
    color: wx.Colour = field(default_factory=lambda: wx.Colour(200, 220, 255))
    
    def contains_point(self, px: int, py: int) -> bool:
        """Check if point is inside this block."""
        return (self.x <= px <= self.x + self.width and
                self.y <= py <= self.y + self.height)
    
    def get_center(self) -> Tuple[int, int]:
        """Get center point of block."""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    def get_input_point(self) -> Tuple[int, int]:
        """Get left connection point."""
        return (self.x, self.y + self.height // 2)
    
    def get_output_point(self) -> Tuple[int, int]:
        """Get right connection point."""
        return (self.x + self.width, self.y + self.height // 2)


class BlockEditorCanvas(wx.Panel):
    """
    Visual canvas for editing reliability block diagrams.
    
    Users can:
    - Drag blocks from a palette
    - Arrange blocks to indicate series/parallel connections
    - Create groups for redundancy configurations
    - See real-time reliability calculations
    """
    
    # Layout constants
    GRID_SIZE = 20
    BLOCK_WIDTH = 160
    BLOCK_HEIGHT = 60
    GROUP_PADDING = 20
    
    # Colors
    COLOR_BACKGROUND = wx.Colour(250, 250, 250)
    COLOR_GRID = wx.Colour(230, 230, 230)
    COLOR_BLOCK = wx.Colour(200, 220, 255)
    COLOR_BLOCK_SELECTED = wx.Colour(150, 180, 255)
    COLOR_GROUP_SERIES = wx.Colour(220, 255, 220)
    COLOR_GROUP_PARALLEL = wx.Colour(255, 220, 220)
    COLOR_GROUP_KN = wx.Colour(255, 255, 200)
    COLOR_CONNECTION = wx.Colour(100, 100, 100)
    COLOR_TEXT = wx.Colour(30, 30, 30)
    
    def __init__(self, parent):
        super().__init__(parent, style=wx.BORDER_SIMPLE)
        
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((800, 400))
        
        # State
        self.blocks: Dict[str, BlockNode] = {}
        self.root_group: Optional[str] = None
        self.selected_block: Optional[str] = None
        self.dragging: bool = False
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.hover_block: Optional[str] = None
        
        # For creating new groups
        self.selection_rect: Optional[Tuple[int, int, int, int]] = None
        self.selecting: bool = False
        self.selection_start: Tuple[int, int] = (0, 0)
        
        # Mission time for calculations
        self.mission_hours: float = 5 * 365 * 24  # 5 years default
        
        # Callbacks
        self.on_selection_change = None
        self.on_structure_change = None
        
        # Bind events
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_left_up)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_double_click)
        self.Bind(wx.EVT_RIGHT_DOWN, self.on_right_click)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        
        self.SetFocus()
    
    def add_block(self, block_id: str, name: str, display_name: str = None,
                  x: int = None, y: int = None) -> BlockNode:
        """Add a new block to the canvas."""
        if display_name is None:
            # Extract short name from path
            display_name = name.rstrip('/').split('/')[-1] or name
        
        # Auto-position if not specified
        if x is None or y is None:
            x, y = self._find_free_position()
        
        block = BlockNode(
            id=block_id,
            name=name,
            display_name=display_name,
            x=x,
            y=y,
            width=self.BLOCK_WIDTH,
            height=self.BLOCK_HEIGHT,
        )
        self.blocks[block_id] = block
        
        # If no root, this becomes the root series group
        if self.root_group is None:
            root = BlockNode(
                id="__root__",
                name="System",
                display_name="System",
                x=0, y=0,
                is_group=True,
                connection_type=ConnectionType.SERIES,
                color=self.COLOR_GROUP_SERIES,
            )
            self.blocks["__root__"] = root
            self.root_group = "__root__"
        
        self.Refresh()
        return block
    
    def remove_block(self, block_id: str):
        """Remove a block from the canvas."""
        if block_id in self.blocks:
            # Remove from any parent groups
            for block in self.blocks.values():
                if block.is_group and block_id in block.children:
                    block.children.remove(block_id)
            
            del self.blocks[block_id]
            
            if self.selected_block == block_id:
                self.selected_block = None
            
            self.Refresh()
            self._notify_structure_change()
    
    def create_group(self, block_ids: List[str], connection_type: ConnectionType,
                     k_value: int = 2) -> Optional[str]:
        """Create a group from selected blocks."""
        if len(block_ids) < 2:
            return None
        
        # Generate unique group ID
        group_id = f"__group_{len([b for b in self.blocks.values() if b.is_group])}__"
        
        # Calculate bounding box
        min_x = min(self.blocks[bid].x for bid in block_ids)
        min_y = min(self.blocks[bid].y for bid in block_ids)
        max_x = max(self.blocks[bid].x + self.blocks[bid].width for bid in block_ids)
        max_y = max(self.blocks[bid].y + self.blocks[bid].height for bid in block_ids)
        
        # Set color based on connection type
        if connection_type == ConnectionType.SERIES:
            color = self.COLOR_GROUP_SERIES
            name = "Series"
        elif connection_type == ConnectionType.PARALLEL:
            color = self.COLOR_GROUP_PARALLEL
            name = "Parallel"
        else:
            color = self.COLOR_GROUP_KN
            name = f"{k_value}-of-{len(block_ids)}"
        
        group = BlockNode(
            id=group_id,
            name=name,
            display_name=name,
            x=min_x - self.GROUP_PADDING,
            y=min_y - self.GROUP_PADDING,
            width=max_x - min_x + 2 * self.GROUP_PADDING,
            height=max_y - min_y + 2 * self.GROUP_PADDING,
            is_group=True,
            children=list(block_ids),
            connection_type=connection_type,
            k_value=k_value,
            color=color,
        )
        
        self.blocks[group_id] = group
        
        # Remove blocks from root if they were there
        root = self.blocks.get(self.root_group)
        if root:
            for bid in block_ids:
                if bid in root.children:
                    root.children.remove(bid)
            root.children.append(group_id)
        
        self.Refresh()
        self._notify_structure_change()
        return group_id
    
    def ungroup(self, group_id: str):
        """Dissolve a group, returning children to parent."""
        if group_id not in self.blocks or not self.blocks[group_id].is_group:
            return
        
        group = self.blocks[group_id]
        children = group.children.copy()
        
        # Find parent group
        parent_id = None
        for block in self.blocks.values():
            if block.is_group and group_id in block.children:
                parent_id = block.id
                break
        
        if parent_id:
            parent = self.blocks[parent_id]
            parent.children.remove(group_id)
            parent.children.extend(children)
        
        del self.blocks[group_id]
        
        self.Refresh()
        self._notify_structure_change()
    
    def _find_free_position(self) -> Tuple[int, int]:
        """Find a free position for a new block."""
        # Simple grid-based placement
        x = self.GROUP_PADDING + self.GRID_SIZE
        y = self.GROUP_PADDING + self.GRID_SIZE
        
        while True:
            collision = False
            for block in self.blocks.values():
                if (abs(block.x - x) < self.BLOCK_WIDTH + 20 and
                    abs(block.y - y) < self.BLOCK_HEIGHT + 20):
                    collision = True
                    break
            
            if not collision:
                return (x, y)
            
            x += self.BLOCK_WIDTH + 40
            if x > 600:
                x = self.GROUP_PADDING + self.GRID_SIZE
                y += self.BLOCK_HEIGHT + 40
    
    def _snap_to_grid(self, x: int, y: int) -> Tuple[int, int]:
        """Snap coordinates to grid."""
        return (
            round(x / self.GRID_SIZE) * self.GRID_SIZE,
            round(y / self.GRID_SIZE) * self.GRID_SIZE
        )
    
    def _get_block_at(self, x: int, y: int) -> Optional[str]:
        """Get block ID at position, preferring non-groups."""
        # First check non-group blocks (higher z-order)
        for block_id, block in self.blocks.items():
            if not block.is_group and block.contains_point(x, y):
                return block_id
        
        # Then check groups
        for block_id, block in self.blocks.items():
            if block.is_group and block.contains_point(x, y):
                return block_id
        
        return None
    
    def _notify_selection_change(self):
        """Notify listeners of selection change."""
        if self.on_selection_change:
            self.on_selection_change(self.selected_block)
    
    def _notify_structure_change(self):
        """Notify listeners of structure change."""
        if self.on_structure_change:
            self.on_structure_change()
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    
    def on_paint(self, event):
        """Paint the canvas."""
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        
        width, height = self.GetSize()
        
        # Background
        gc.SetBrush(wx.Brush(self.COLOR_BACKGROUND))
        gc.DrawRectangle(0, 0, width, height)
        
        # Grid
        gc.SetPen(wx.Pen(self.COLOR_GRID, 1))
        for x in range(0, width, self.GRID_SIZE):
            gc.StrokeLine(x, 0, x, height)
        for y in range(0, height, self.GRID_SIZE):
            gc.StrokeLine(0, y, width, y)
        
        # Draw groups first (background)
        for block in sorted(self.blocks.values(), key=lambda b: (not b.is_group, b.y)):
            if block.is_group:
                self._draw_group(gc, block)
        
        # Draw regular blocks
        for block in self.blocks.values():
            if not block.is_group:
                self._draw_block(gc, block)
        
        # Draw selection rectangle if selecting
        if self.selecting and self.selection_rect:
            x, y, w, h = self.selection_rect
            gc.SetBrush(wx.Brush(wx.Colour(100, 150, 255, 50)))
            gc.SetPen(wx.Pen(wx.Colour(100, 150, 255), 2, wx.PENSTYLE_DOT))
            gc.DrawRectangle(x, y, w, h)
    
    def _draw_block(self, gc: wx.GraphicsContext, block: BlockNode):
        """Draw a single block."""
        # Block rectangle
        if block.id == self.selected_block:
            gc.SetBrush(wx.Brush(self.COLOR_BLOCK_SELECTED))
            gc.SetPen(wx.Pen(wx.Colour(50, 100, 200), 3))
        elif block.id == self.hover_block:
            gc.SetBrush(wx.Brush(self.COLOR_BLOCK))
            gc.SetPen(wx.Pen(wx.Colour(100, 150, 200), 2))
        else:
            gc.SetBrush(wx.Brush(block.color))
            gc.SetPen(wx.Pen(wx.Colour(100, 100, 100), 1))
        
        gc.DrawRoundedRectangle(block.x, block.y, block.width, block.height, 8)
        
        # Block name
        font = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        gc.SetFont(font, self.COLOR_TEXT)
        
        # Truncate name if too long
        name = block.display_name
        if len(name) > 18:
            name = name[:15] + "..."
        
        text_width, text_height = gc.GetTextExtent(name)[:2]
        text_x = block.x + (block.width - text_width) / 2
        text_y = block.y + 10
        gc.DrawText(name, text_x, text_y)
        
        # Reliability value
        font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        gc.SetFont(font, wx.Colour(60, 60, 60))
        
        r_text = f"R = {block.reliability:.4f}"
        text_width, text_height = gc.GetTextExtent(r_text)[:2]
        gc.DrawText(r_text, block.x + (block.width - text_width) / 2, block.y + 32)
        
        # Lambda value
        lambda_text = f"λ = {block.lambda_val:.2e}"
        text_width, text_height = gc.GetTextExtent(lambda_text)[:2]
        gc.DrawText(lambda_text, block.x + (block.width - text_width) / 2, block.y + 46)
    
    def _draw_group(self, gc: wx.GraphicsContext, group: BlockNode):
        """Draw a group container."""
        # Background
        gc.SetBrush(wx.Brush(wx.Colour(group.color.Red(), group.color.Green(),
                                        group.color.Blue(), 100)))
        
        if group.id == self.selected_block:
            gc.SetPen(wx.Pen(wx.Colour(50, 100, 200), 3, wx.PENSTYLE_DOT))
        else:
            gc.SetPen(wx.Pen(wx.Colour(150, 150, 150), 2, wx.PENSTYLE_DOT))
        
        gc.DrawRoundedRectangle(group.x, group.y, group.width, group.height, 12)
        
        # Label
        font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        gc.SetFont(font, wx.Colour(80, 80, 80))
        
        if group.connection_type == ConnectionType.SERIES:
            label = "SERIES"
        elif group.connection_type == ConnectionType.PARALLEL:
            label = "PARALLEL"
        else:
            label = f"{group.k_value}-of-{len(group.children)}"
        
        gc.DrawText(label, group.x + 8, group.y + 4)
        
        # Group reliability
        r_text = f"R = {group.reliability:.4f}"
        text_width = gc.GetTextExtent(r_text)[0]
        gc.DrawText(r_text, group.x + group.width - text_width - 8, group.y + 4)
    
    def on_left_down(self, event):
        """Handle left mouse button down."""
        x, y = event.GetPosition()
        self.SetFocus()
        
        block_id = self._get_block_at(x, y)
        
        if block_id:
            self.selected_block = block_id
            self.dragging = True
            block = self.blocks[block_id]
            self.drag_offset = (x - block.x, y - block.y)
        else:
            # Start selection rectangle
            self.selecting = True
            self.selection_start = (x, y)
            self.selection_rect = (x, y, 0, 0)
            self.selected_block = None
        
        self._notify_selection_change()
        self.Refresh()
    
    def on_left_up(self, event):
        """Handle left mouse button up."""
        if self.dragging:
            self.dragging = False
            self._notify_structure_change()
        
        if self.selecting:
            self.selecting = False
            # Check if selection is large enough and contains blocks
            if self.selection_rect:
                x, y, w, h = self.selection_rect
                if w > 20 and h > 20:
                    # Find blocks in selection
                    selected = []
                    for bid, block in self.blocks.items():
                        if not block.is_group:
                            cx, cy = block.get_center()
                            if x <= cx <= x + w and y <= cy <= y + h:
                                selected.append(bid)
                    
                    if len(selected) >= 2:
                        # Show context menu for group creation
                        self._show_group_menu(selected)
            
            self.selection_rect = None
        
        self.Refresh()
    
    def on_double_click(self, event):
        """Handle double click - edit group properties."""
        x, y = event.GetPosition()
        block_id = self._get_block_at(x, y)
        
        if block_id and self.blocks[block_id].is_group:
            self._show_group_properties(block_id)
    
    def on_right_click(self, event):
        """Handle right click - context menu."""
        x, y = event.GetPosition()
        block_id = self._get_block_at(x, y)
        
        if block_id:
            self.selected_block = block_id
            self._notify_selection_change()
            self.Refresh()
            
            menu = wx.Menu()
            
            block = self.blocks[block_id]
            if block.is_group:
                menu.Append(wx.ID_ANY, "Edit Group Properties...")
                menu.AppendSeparator()
                menu.Append(wx.ID_ANY, "Ungroup")
            else:
                menu.Append(wx.ID_ANY, "Edit Parameters...")
                menu.AppendSeparator()
                menu.Append(wx.ID_ANY, "Remove Block")
            
            self.PopupMenu(menu, event.GetPosition())
            menu.Destroy()
    
    def on_motion(self, event):
        """Handle mouse motion."""
        x, y = event.GetPosition()
        
        if self.dragging and self.selected_block:
            block = self.blocks[self.selected_block]
            new_x, new_y = self._snap_to_grid(
                x - self.drag_offset[0],
                y - self.drag_offset[1]
            )
            block.x = max(0, new_x)
            block.y = max(0, new_y)
            
            # Update parent group bounds if in a group
            self._update_group_bounds()
            
            self.Refresh()
        
        elif self.selecting:
            sx, sy = self.selection_start
            w = x - sx
            h = y - sy
            
            # Normalize for negative dimensions
            if w < 0:
                sx, w = x, -w
            if h < 0:
                sy, h = y, -h
            
            self.selection_rect = (sx, sy, w, h)
            self.Refresh()
        
        else:
            # Hover effect
            old_hover = self.hover_block
            self.hover_block = self._get_block_at(x, y)
            if old_hover != self.hover_block:
                self.Refresh()
    
    def on_size(self, event):
        """Handle resize."""
        self.Refresh()
        event.Skip()
    
    def on_key_down(self, event):
        """Handle keyboard input."""
        keycode = event.GetKeyCode()
        
        if keycode == wx.WXK_DELETE and self.selected_block:
            block = self.blocks.get(self.selected_block)
            if block and block.is_group:
                self.ungroup(self.selected_block)
            elif block:
                self.remove_block(self.selected_block)
        
        event.Skip()
    
    def _update_group_bounds(self):
        """Update group boundaries to contain all children."""
        for group in self.blocks.values():
            if group.is_group and group.children:
                # Calculate bounds from children
                min_x = float('inf')
                min_y = float('inf')
                max_x = float('-inf')
                max_y = float('-inf')
                
                for child_id in group.children:
                    child = self.blocks.get(child_id)
                    if child:
                        min_x = min(min_x, child.x)
                        min_y = min(min_y, child.y)
                        max_x = max(max_x, child.x + child.width)
                        max_y = max(max_y, child.y + child.height)
                
                if min_x != float('inf'):
                    group.x = min_x - self.GROUP_PADDING
                    group.y = min_y - self.GROUP_PADDING
                    group.width = max_x - min_x + 2 * self.GROUP_PADDING
                    group.height = max_y - min_y + 2 * self.GROUP_PADDING
    
    def _show_group_menu(self, block_ids: List[str]):
        """Show menu for creating a group."""
        menu = wx.Menu()
        
        id_series = wx.NewId()
        id_parallel = wx.NewId()
        id_kn = wx.NewId()
        
        menu.Append(id_series, "Group as Series")
        menu.Append(id_parallel, "Group as Parallel")
        menu.Append(id_kn, f"Group as K-of-{len(block_ids)}...")
        
        def on_series(evt):
            self.create_group(block_ids, ConnectionType.SERIES)
        
        def on_parallel(evt):
            self.create_group(block_ids, ConnectionType.PARALLEL)
        
        def on_kn(evt):
            dlg = wx.NumberEntryDialog(
                self, f"How many must work out of {len(block_ids)}?",
                "K value:", "K-of-N Redundancy",
                2, 1, len(block_ids)
            )
            if dlg.ShowModal() == wx.ID_OK:
                self.create_group(block_ids, ConnectionType.K_OF_N, dlg.GetValue())
            dlg.Destroy()
        
        self.Bind(wx.EVT_MENU, on_series, id=id_series)
        self.Bind(wx.EVT_MENU, on_parallel, id=id_parallel)
        self.Bind(wx.EVT_MENU, on_kn, id=id_kn)
        
        self.PopupMenu(menu)
        menu.Destroy()
    
    def _show_group_properties(self, group_id: str):
        """Show dialog to edit group properties."""
        group = self.blocks.get(group_id)
        if not group or not group.is_group:
            return
        
        dlg = wx.SingleChoiceDialog(
            self,
            "Select connection type:",
            "Group Properties",
            ["Series", "Parallel", f"K-of-{len(group.children)}"]
        )
        
        # Set current selection
        if group.connection_type == ConnectionType.SERIES:
            dlg.SetSelection(0)
        elif group.connection_type == ConnectionType.PARALLEL:
            dlg.SetSelection(1)
        else:
            dlg.SetSelection(2)
        
        if dlg.ShowModal() == wx.ID_OK:
            sel = dlg.GetSelection()
            if sel == 0:
                group.connection_type = ConnectionType.SERIES
                group.color = self.COLOR_GROUP_SERIES
                group.display_name = "Series"
            elif sel == 1:
                group.connection_type = ConnectionType.PARALLEL
                group.color = self.COLOR_GROUP_PARALLEL
                group.display_name = "Parallel"
            else:
                # Ask for K value
                k_dlg = wx.NumberEntryDialog(
                    self, f"How many must work out of {len(group.children)}?",
                    "K value:", "K-of-N Redundancy",
                    group.k_value, 1, len(group.children)
                )
                if k_dlg.ShowModal() == wx.ID_OK:
                    group.k_value = k_dlg.GetValue()
                k_dlg.Destroy()
                
                group.connection_type = ConnectionType.K_OF_N
                group.color = self.COLOR_GROUP_KN
                group.display_name = f"{group.k_value}-of-{len(group.children)}"
            
            self.Refresh()
            self._notify_structure_change()
        
        dlg.Destroy()
    
    # =========================================================================
    # Data Access
    # =========================================================================
    
    def get_structure(self) -> Dict:
        """Get the current structure as a serializable dictionary."""
        return {
            "blocks": {
                bid: {
                    "name": b.name,
                    "display_name": b.display_name,
                    "x": b.x,
                    "y": b.y,
                    "is_group": b.is_group,
                    "children": b.children,
                    "connection_type": b.connection_type.value,
                    "k_value": b.k_value,
                }
                for bid, b in self.blocks.items()
            },
            "root": self.root_group,
            "mission_hours": self.mission_hours,
        }
    
    def load_structure(self, data: Dict):
        """Load structure from a dictionary."""
        self.blocks.clear()
        
        for bid, bdata in data.get("blocks", {}).items():
            block = BlockNode(
                id=bid,
                name=bdata["name"],
                display_name=bdata["display_name"],
                x=bdata["x"],
                y=bdata["y"],
                is_group=bdata["is_group"],
                children=bdata.get("children", []),
                connection_type=ConnectionType(bdata.get("connection_type", "series")),
                k_value=bdata.get("k_value", 2),
            )
            
            # Set color based on type
            if block.is_group:
                if block.connection_type == ConnectionType.SERIES:
                    block.color = self.COLOR_GROUP_SERIES
                elif block.connection_type == ConnectionType.PARALLEL:
                    block.color = self.COLOR_GROUP_PARALLEL
                else:
                    block.color = self.COLOR_GROUP_KN
            
            self.blocks[bid] = block
        
        self.root_group = data.get("root")
        self.mission_hours = data.get("mission_hours", 5 * 365 * 24)
        
        self.Refresh()
    
    def update_reliability(self, block_id: str, reliability: float, lambda_val: float):
        """Update reliability values for a block."""
        if block_id in self.blocks:
            self.blocks[block_id].reliability = reliability
            self.blocks[block_id].lambda_val = lambda_val
            self.Refresh()
    
    def clear(self):
        """Clear all blocks."""
        self.blocks.clear()
        self.root_group = None
        self.selected_block = None
        self.Refresh()
