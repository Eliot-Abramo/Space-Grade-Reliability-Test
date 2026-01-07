"""
Visual Block Diagram Editor

Drag-and-drop canvas for defining reliability topology.
"""

import wx
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .reliability_math import ConnectionType

@dataclass
class Block:
    """A block in the reliability diagram."""
    id: str
    name: str  # Full sheet path
    label: str  # Display name
    x: int = 0
    y: int = 0
    width: int = 150
    height: int = 55
    reliability: float = 1.0
    lambda_val: float = 0.0
    is_group: bool = False
    children: List[str] = field(default_factory=list)
    connection_type: str = "series"
    k_value: int = 2
    
    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height
    
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


class BlockEditor(wx.Panel):
    """Visual editor for reliability block diagrams."""
    
    GRID = 20
    BLOCK_W = 150
    BLOCK_H = 55
    PAD = 15
    
    # Colors
    BG = wx.Colour(248, 248, 248)
    GRID_COLOR = wx.Colour(230, 230, 230)
    BLOCK_COLOR = wx.Colour(200, 220, 255)
    BLOCK_SEL = wx.Colour(150, 180, 255)
    SERIES_COLOR = wx.Colour(220, 255, 220)
    PARALLEL_COLOR = wx.Colour(255, 220, 220)
    KN_COLOR = wx.Colour(255, 255, 200)
    
    def __init__(self, parent):
        super().__init__(parent, style=wx.BORDER_SIMPLE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((700, 350))
        
        self.blocks: Dict[str, Block] = {}
        self.root_id: Optional[str] = None
        self.selected: Optional[str] = None
        self.hover: Optional[str] = None
        
        self.dragging = False
        self.drag_offset = (0, 0)
        self.selecting = False
        self.sel_start = (0, 0)
        self.sel_rect: Optional[Tuple[int, int, int, int]] = None
        
        self.mission_hours = 5 * 365 * 24
        
        # Callbacks
        self.on_selection_change = None
        self.on_structure_change = None
        
        # Events
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_dclick)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_right_click)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.Bind(wx.EVT_SIZE, lambda e: self.Refresh())
        
        self.SetFocus()
    
    def add_block(self, block_id: str, name: str, label: str = None) -> Block:
        """Add a sheet block."""
        if label is None:
            label = name.rstrip('/').split('/')[-1] or name
        
        x, y = self._find_position()
        
        block = Block(id=block_id, name=name, label=label, x=x, y=y,
                      width=self.BLOCK_W, height=self.BLOCK_H)
        self.blocks[block_id] = block
        
        # Create root group if needed
        if self.root_id is None:
            root = Block(id="__root__", name="System", label="System",
                        is_group=True, connection_type="series")
            self.blocks["__root__"] = root
            self.root_id = "__root__"
        
        # Add to root
        root = self.blocks.get(self.root_id)
        if root and block_id not in root.children:
            root.children.append(block_id)
        
        self._update_group_bounds()
        self.Refresh()
        return block
    
    def remove_block(self, block_id: str):
        """Remove a block."""
        if block_id not in self.blocks:
            return
        
        # Remove from parents
        for b in self.blocks.values():
            if b.is_group and block_id in b.children:
                b.children.remove(block_id)
        
        del self.blocks[block_id]
        if self.selected == block_id:
            self.selected = None
        
        self._update_group_bounds()
        self.Refresh()
        self._notify_change()
    
    def create_group(self, block_ids: List[str], conn_type: str, k: int = 2) -> Optional[str]:
        """Group blocks together."""
        if len(block_ids) < 2:
            return None
        
        gid = f"__grp_{sum(1 for b in self.blocks.values() if b.is_group)}__"
        
        # Bounds
        min_x = min(self.blocks[bid].x for bid in block_ids)
        min_y = min(self.blocks[bid].y for bid in block_ids)
        max_x = max(self.blocks[bid].x + self.blocks[bid].width for bid in block_ids)
        max_y = max(self.blocks[bid].y + self.blocks[bid].height for bid in block_ids)
        
        label = {
            "series": "SERIES",
            "parallel": "PARALLEL",
            "k_of_n": f"{k}-of-{len(block_ids)}"
        }[conn_type]
        
        group = Block(
            id=gid, name=label, label=label,
            x=min_x - self.PAD, y=min_y - self.PAD,
            width=max_x - min_x + 2*self.PAD,
            height=max_y - min_y + 2*self.PAD,
            is_group=True, children=list(block_ids),
            connection_type=conn_type, k_value=k
        )
        self.blocks[gid] = group
        
        # Move blocks from root to this group
        root = self.blocks.get(self.root_id)
        if root:
            for bid in block_ids:
                if bid in root.children:
                    root.children.remove(bid)
            root.children.append(gid)
        
        self.Refresh()
        self._notify_change()
        return gid
    
    def ungroup(self, group_id: str):
        """Dissolve a group."""
        if group_id not in self.blocks or not self.blocks[group_id].is_group:
            return
        
        group = self.blocks[group_id]
        children = group.children.copy()
        
        # Find parent
        parent = None
        for b in self.blocks.values():
            if b.is_group and group_id in b.children:
                parent = b
                break
        
        if parent:
            parent.children.remove(group_id)
            parent.children.extend(children)
        
        del self.blocks[group_id]
        self._update_group_bounds()
        self.Refresh()
        self._notify_change()
    
    def _find_position(self) -> Tuple[int, int]:
        """Find free position for new block."""
        x, y = self.PAD + self.GRID, self.PAD + self.GRID
        
        while True:
            collision = False
            for b in self.blocks.values():
                if not b.is_group:
                    if abs(b.x - x) < self.BLOCK_W + 20 and abs(b.y - y) < self.BLOCK_H + 20:
                        collision = True
                        break
            
            if not collision:
                return (x, y)
            
            x += self.BLOCK_W + 30
            if x > 500:
                x = self.PAD + self.GRID
                y += self.BLOCK_H + 30
    
    def _snap(self, x: int, y: int) -> Tuple[int, int]:
        return (round(x / self.GRID) * self.GRID, round(y / self.GRID) * self.GRID)
    
    def _block_at(self, x: int, y: int) -> Optional[str]:
        """Get block at position (prefer non-groups)."""
        for bid, b in self.blocks.items():
            if not b.is_group and b.contains(x, y):
                return bid
        for bid, b in self.blocks.items():
            if b.is_group and b.contains(x, y):
                return bid
        return None
    
    def _update_group_bounds(self):
        """Update group boundaries."""
        for g in self.blocks.values():
            if g.is_group and g.children:
                min_x = min_y = float('inf')
                max_x = max_y = float('-inf')
                
                for cid in g.children:
                    c = self.blocks.get(cid)
                    if c:
                        min_x = min(min_x, c.x)
                        min_y = min(min_y, c.y)
                        max_x = max(max_x, c.x + c.width)
                        max_y = max(max_y, c.y + c.height)
                
                if min_x != float('inf'):
                    g.x = int(min_x - self.PAD)
                    g.y = int(min_y - self.PAD)
                    g.width = int(max_x - min_x + 2*self.PAD)
                    g.height = int(max_y - min_y + 2*self.PAD)
    
    def _notify_change(self):
        if self.on_structure_change:
            self.on_structure_change()
    
    def _notify_selection(self):
        if self.on_selection_change:
            self.on_selection_change(self.selected)
    
    # === Event handlers ===
    
    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        w, h = self.GetSize()
        
        # Background
        gc.SetBrush(wx.Brush(self.BG))
        gc.DrawRectangle(0, 0, w, h)
        
        # Grid
        gc.SetPen(wx.Pen(self.GRID_COLOR, 1))
        for x in range(0, w, self.GRID):
            gc.StrokeLine(x, 0, x, h)
        for y in range(0, h, self.GRID):
            gc.StrokeLine(0, y, w, y)
        
        # Groups (back)
        for b in sorted(self.blocks.values(), key=lambda x: not x.is_group):
            if b.is_group:
                self._draw_group(gc, b)
        
        # Blocks (front)
        for b in self.blocks.values():
            if not b.is_group:
                self._draw_block(gc, b)
        
        # Selection rectangle
        if self.selecting and self.sel_rect:
            x, y, w, h = self.sel_rect
            gc.SetBrush(wx.Brush(wx.Colour(100, 150, 255, 50)))
            gc.SetPen(wx.Pen(wx.Colour(100, 150, 255), 2, wx.PENSTYLE_DOT))
            gc.DrawRectangle(x, y, w, h)
    
    def _draw_block(self, gc, b: Block):
        if b.id == self.selected:
            gc.SetBrush(wx.Brush(self.BLOCK_SEL))
            gc.SetPen(wx.Pen(wx.Colour(50, 100, 200), 3))
        elif b.id == self.hover:
            gc.SetBrush(wx.Brush(self.BLOCK_COLOR))
            gc.SetPen(wx.Pen(wx.Colour(100, 150, 200), 2))
        else:
            gc.SetBrush(wx.Brush(self.BLOCK_COLOR))
            gc.SetPen(wx.Pen(wx.Colour(100, 100, 100), 1))
        
        gc.DrawRoundedRectangle(b.x, b.y, b.width, b.height, 6)
        
        # Label
        font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        gc.SetFont(font, wx.Colour(30, 30, 30))
        
        label = b.label[:18] + "..." if len(b.label) > 18 else b.label
        tw = gc.GetTextExtent(label)[0]
        gc.DrawText(label, b.x + (b.width - tw)/2, b.y + 8)
        
        # Reliability
        font = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        gc.SetFont(font, wx.Colour(60, 60, 60))
        
        r_text = f"R = {b.reliability:.4f}"
        tw = gc.GetTextExtent(r_text)[0]
        gc.DrawText(r_text, b.x + (b.width - tw)/2, b.y + 24)
        
        l_text = f"λ = {b.lambda_val:.2e}"
        tw = gc.GetTextExtent(l_text)[0]
        gc.DrawText(l_text, b.x + (b.width - tw)/2, b.y + 38)
    
    def _draw_group(self, gc, g: Block):
        color = {
            "series": self.SERIES_COLOR,
            "parallel": self.PARALLEL_COLOR,
            "k_of_n": self.KN_COLOR,
        }.get(g.connection_type, self.SERIES_COLOR)
        
        gc.SetBrush(wx.Brush(wx.Colour(color.Red(), color.Green(), color.Blue(), 80)))
        
        if g.id == self.selected:
            gc.SetPen(wx.Pen(wx.Colour(50, 100, 200), 3, wx.PENSTYLE_DOT))
        else:
            gc.SetPen(wx.Pen(wx.Colour(150, 150, 150), 2, wx.PENSTYLE_DOT))
        
        gc.DrawRoundedRectangle(g.x, g.y, g.width, g.height, 10)
        
        # Label
        font = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        gc.SetFont(font, wx.Colour(80, 80, 80))
        
        label = g.label
        gc.DrawText(label, g.x + 6, g.y + 3)
        
        r_text = f"R={g.reliability:.4f}"
        tw = gc.GetTextExtent(r_text)[0]
        gc.DrawText(r_text, g.x + g.width - tw - 6, g.y + 3)
    
    def _on_left_down(self, event):
        x, y = event.GetPosition()
        self.SetFocus()
        
        bid = self._block_at(x, y)
        
        if bid:
            self.selected = bid
            self.dragging = True
            b = self.blocks[bid]
            self.drag_offset = (x - b.x, y - b.y)
        else:
            self.selecting = True
            self.sel_start = (x, y)
            self.sel_rect = (x, y, 0, 0)
            self.selected = None
        
        self._notify_selection()
        self.Refresh()
    
    def _on_left_up(self, event):
        if self.dragging:
            self.dragging = False
            self._update_group_bounds()
            self._notify_change()
        
        if self.selecting:
            self.selecting = False
            if self.sel_rect:
                x, y, w, h = self.sel_rect
                if w > 20 and h > 20:
                    selected = []
                    for bid, b in self.blocks.items():
                        if not b.is_group:
                            cx, cy = b.center()
                            if x <= cx <= x+w and y <= cy <= y+h:
                                selected.append(bid)
                    
                    if len(selected) >= 2:
                        self._show_group_menu(selected)
            
            self.sel_rect = None
        
        self.Refresh()
    
    def _on_dclick(self, event):
        x, y = event.GetPosition()
        bid = self._block_at(x, y)
        
        if bid and self.blocks[bid].is_group:
            self._edit_group(bid)
    
    def _on_right_click(self, event):
        x, y = event.GetPosition()
        bid = self._block_at(x, y)
        
        if bid:
            self.selected = bid
            self._notify_selection()
            self.Refresh()
            
            menu = wx.Menu()
            b = self.blocks[bid]
            
            if b.is_group:
                item = menu.Append(wx.ID_ANY, "Edit Group Type...")
                self.Bind(wx.EVT_MENU, lambda e: self._edit_group(bid), item)
                menu.AppendSeparator()
                item = menu.Append(wx.ID_ANY, "Ungroup")
                self.Bind(wx.EVT_MENU, lambda e: self.ungroup(bid), item)
            else:
                item = menu.Append(wx.ID_ANY, "Remove from Diagram")
                self.Bind(wx.EVT_MENU, lambda e: self.remove_block(bid), item)
            
            self.PopupMenu(menu, event.GetPosition())
            menu.Destroy()
    
    def _on_motion(self, event):
        x, y = event.GetPosition()
        
        if self.dragging and self.selected:
            b = self.blocks[self.selected]
            b.x, b.y = self._snap(x - self.drag_offset[0], y - self.drag_offset[1])
            b.x = max(0, b.x)
            b.y = max(0, b.y)
            self._update_group_bounds()
            self.Refresh()
        
        elif self.selecting:
            sx, sy = self.sel_start
            w, h = x - sx, y - sy
            if w < 0:
                sx, w = x, -w
            if h < 0:
                sy, h = y, -h
            self.sel_rect = (sx, sy, w, h)
            self.Refresh()
        
        else:
            old_hover = self.hover
            self.hover = self._block_at(x, y)
            if old_hover != self.hover:
                self.Refresh()
    
    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_DELETE and self.selected:
            b = self.blocks.get(self.selected)
            if b and b.is_group:
                self.ungroup(self.selected)
            elif b:
                self.remove_block(self.selected)
        event.Skip()
    
    def _show_group_menu(self, block_ids: List[str]):
        """Show menu to create group."""
        menu = wx.Menu()
        
        id_s = wx.NewId()
        id_p = wx.NewId()
        id_k = wx.NewId()
        
        menu.Append(id_s, "Group as SERIES (all must work)")
        menu.Append(id_p, "Group as PARALLEL (any can work)")
        menu.Append(id_k, f"Group as K-of-{len(block_ids)} (redundancy)...")
        
        self.Bind(wx.EVT_MENU, lambda e: self.create_group(block_ids, "series"), id=id_s)
        self.Bind(wx.EVT_MENU, lambda e: self.create_group(block_ids, "parallel"), id=id_p)
        
        def on_kn(e):
            dlg = wx.NumberEntryDialog(self, f"How many must work?", "K:", 
                                       "K-of-N Redundancy", 2, 1, len(block_ids))
            if dlg.ShowModal() == wx.ID_OK:
                self.create_group(block_ids, "k_of_n", dlg.GetValue())
            dlg.Destroy()
        
        self.Bind(wx.EVT_MENU, on_kn, id=id_k)
        
        self.PopupMenu(menu)
        menu.Destroy()
    
    def _edit_group(self, group_id: str):
        """Edit group properties."""
        g = self.blocks.get(group_id)
        if not g or not g.is_group:
            return
        
        choices = ["SERIES (all must work)", "PARALLEL (any can work)", 
                   f"K-of-{len(g.children)} (redundancy)"]
        
        dlg = wx.SingleChoiceDialog(self, "Select connection type:", "Group Type", choices)
        
        idx = {"series": 0, "parallel": 1, "k_of_n": 2}
        dlg.SetSelection(idx.get(g.connection_type, 0))
        
        if dlg.ShowModal() == wx.ID_OK:
            sel = dlg.GetSelection()
            if sel == 0:
                g.connection_type = "series"
                g.label = "SERIES"
            elif sel == 1:
                g.connection_type = "parallel"
                g.label = "PARALLEL"
            else:
                kdlg = wx.NumberEntryDialog(self, "How many must work?", "K:",
                                            "K-of-N", g.k_value, 1, len(g.children))
                if kdlg.ShowModal() == wx.ID_OK:
                    g.k_value = kdlg.GetValue()
                kdlg.Destroy()
                g.connection_type = "k_of_n"
                g.label = f"{g.k_value}-of-{len(g.children)}"
            
            self.Refresh()
            self._notify_change()
        
        dlg.Destroy()
    
    # === Data access ===
    
    def get_structure(self) -> Dict:
        """Get serializable structure."""
        return {
            "blocks": {
                bid: {
                    "name": b.name, "label": b.label,
                    "x": b.x, "y": b.y,
                    "is_group": b.is_group, "children": b.children,
                    "connection_type": b.connection_type,
                    "k_value": b.k_value,
                }
                for bid, b in self.blocks.items()
            },
            "root": self.root_id,
            "mission_hours": self.mission_hours,
        }
    
    def load_structure(self, data: Dict):
        """Load structure from dict."""
        self.blocks.clear()
        
        for bid, bd in data.get("blocks", {}).items():
            b = Block(
                id=bid, name=bd["name"], label=bd["label"],
                x=bd["x"], y=bd["y"],
                is_group=bd["is_group"], children=bd.get("children", []),
                connection_type=bd.get("connection_type", "series"),
                k_value=bd.get("k_value", 2)
            )
            self.blocks[bid] = b
        
        self.root_id = data.get("root")
        self.mission_hours = data.get("mission_hours", 5*365*24)
        self.Refresh()
    
    def update_block(self, block_id: str, r: float, lam: float):
        """Update block reliability values."""
        if block_id in self.blocks:
            self.blocks[block_id].reliability = r
            self.blocks[block_id].lambda_val = lam
    
    def clear(self):
        """Clear all blocks."""
        self.blocks.clear()
        self.root_id = None
        self.selected = None
        self.Refresh()
