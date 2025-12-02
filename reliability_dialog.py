"""
Main Reliability Dialog

This is the primary user interface for the reliability calculator plugin.
It provides:
- Sheet browser with auto-detection from KiCad project
- Visual block diagram editor
- Real-time reliability calculations  
- Table injection controls
"""

import os
import json
import wx
import wx.lib.scrolledpanel as scrolled
from pathlib import Path
from typing import Dict, List, Optional, Any

from .block_editor import BlockEditorCanvas, BlockNode, ConnectionType
from .reliability_core import (
    calculate_component_lambda, reliability, lambda_from_reliability,
    r_series, r_parallel, r_k_of_n
)
from .schematic_parser import KiCadSchematicParser, create_mock_parser, Component
from .table_generator import KiCadTableGenerator, ReliabilityReportGenerator, ReliabilityTable


class SheetListPanel(wx.Panel):
    """Panel showing available schematic sheets."""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.sheets: List[str] = []
        self.on_sheet_selected = None
        self.on_sheet_add = None
        
        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Header
        header = wx.StaticText(self, label="Available Sheets")
        header.SetFont(header.GetFont().Bold())
        sizer.Add(header, 0, wx.ALL, 5)
        
        # List
        self.list_ctrl = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SIMPLE
        )
        self.list_ctrl.InsertColumn(0, "Sheet Path", width=250)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_add = wx.Button(self, label="Add to Diagram")
        self.btn_add.Bind(wx.EVT_BUTTON, self.on_add_clicked)
        self.btn_add.Enable(False)
        btn_sizer.Add(self.btn_add, 1, wx.RIGHT, 5)
        
        self.btn_add_all = wx.Button(self, label="Add All")
        self.btn_add_all.Bind(wx.EVT_BUTTON, self.on_add_all_clicked)
        btn_sizer.Add(self.btn_add_all, 1)
        
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(sizer)
    
    def set_sheets(self, sheets: List[str]):
        """Update the list of available sheets."""
        self.sheets = sheets
        self.list_ctrl.DeleteAllItems()
        
        for i, sheet in enumerate(sheets):
            self.list_ctrl.InsertItem(i, sheet)
    
    def on_item_selected(self, event):
        """Handle sheet selection."""
        self.btn_add.Enable(True)
        if self.on_sheet_selected:
            idx = event.GetIndex()
            self.on_sheet_selected(self.sheets[idx])
    
    def on_item_activated(self, event):
        """Handle double-click on sheet."""
        self.on_add_clicked(event)
    
    def on_add_clicked(self, event):
        """Add selected sheet to diagram."""
        idx = self.list_ctrl.GetFirstSelected()
        if idx >= 0 and self.on_sheet_add:
            self.on_sheet_add(self.sheets[idx])
    
    def on_add_all_clicked(self, event):
        """Add all sheets to diagram."""
        if self.on_sheet_add:
            for sheet in self.sheets:
                self.on_sheet_add(sheet)


class ComponentDetailsPanel(scrolled.ScrolledPanel):
    """Panel showing component details for selected sheet/block."""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.components: List[Dict] = []
        
        # Layout
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Header
        self.header = wx.StaticText(self, label="Component Details")
        self.header.SetFont(self.header.GetFont().Bold())
        self.sizer.Add(self.header, 0, wx.ALL, 5)
        
        # Component list
        self.list_ctrl = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.BORDER_SIMPLE
        )
        self.list_ctrl.InsertColumn(0, "Ref", width=60)
        self.list_ctrl.InsertColumn(1, "Class", width=150)
        self.list_ctrl.InsertColumn(2, "λ (1/h)", width=80)
        self.list_ctrl.InsertColumn(3, "R", width=70)
        self.sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        # Summary
        self.summary_text = wx.StaticText(self, label="")
        self.sizer.Add(self.summary_text, 0, wx.ALL, 5)
        
        self.SetSizer(self.sizer)
        self.SetupScrolling()
    
    def set_components(self, sheet_path: str, components: List[Dict],
                       total_lambda: float, sheet_r: float):
        """Update displayed components."""
        self.header.SetLabel(f"Components: {sheet_path}")
        self.components = components
        
        self.list_ctrl.DeleteAllItems()
        
        for i, comp in enumerate(components):
            idx = self.list_ctrl.InsertItem(i, comp.get("reference", "?"))
            self.list_ctrl.SetItem(idx, 1, comp.get("class", "Unknown")[:25])
            self.list_ctrl.SetItem(idx, 2, f"{comp.get('lambda', 0):.2e}")
            self.list_ctrl.SetItem(idx, 3, f"{comp.get('reliability', 1.0):.4f}")
        
        self.summary_text.SetLabel(
            f"Total: λ = {total_lambda:.2e}, R = {sheet_r:.6f}"
        )
        
        self.Layout()


class SettingsPanel(wx.Panel):
    """Panel for configuration settings."""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.on_settings_change = None
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Mission time
        time_sizer = wx.BoxSizer(wx.HORIZONTAL)
        time_sizer.Add(wx.StaticText(self, label="Mission Time:"), 0, 
                       wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.spin_years = wx.SpinCtrl(self, min=1, max=50, initial=5)
        self.spin_years.Bind(wx.EVT_SPINCTRL, self.on_value_change)
        time_sizer.Add(self.spin_years, 0, wx.RIGHT, 5)
        time_sizer.Add(wx.StaticText(self, label="years"), 0, wx.ALIGN_CENTER_VERTICAL)
        
        sizer.Add(time_sizer, 0, wx.ALL, 5)
        
        # Thermal cycles
        cycles_sizer = wx.BoxSizer(wx.HORIZONTAL)
        cycles_sizer.Add(wx.StaticText(self, label="Thermal Cycles/Year:"), 0,
                        wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.spin_cycles = wx.SpinCtrl(self, min=100, max=50000, initial=5256)
        self.spin_cycles.Bind(wx.EVT_SPINCTRL, self.on_value_change)
        cycles_sizer.Add(self.spin_cycles, 0)
        
        sizer.Add(cycles_sizer, 0, wx.ALL, 5)
        
        # Delta T
        dt_sizer = wx.BoxSizer(wx.HORIZONTAL)
        dt_sizer.Add(wx.StaticText(self, label="Temperature Swing (ΔT):"), 0,
                     wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.spin_dt = wx.SpinCtrlDouble(self, min=0.1, max=50.0, initial=3.0, inc=0.5)
        self.spin_dt.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_value_change)
        dt_sizer.Add(self.spin_dt, 0, wx.RIGHT, 5)
        dt_sizer.Add(wx.StaticText(self, label="°C"), 0, wx.ALIGN_CENTER_VERTICAL)
        
        sizer.Add(dt_sizer, 0, wx.ALL, 5)
        
        self.SetSizer(sizer)
    
    def get_mission_hours(self) -> float:
        """Get mission time in hours."""
        return self.spin_years.GetValue() * 365 * 24
    
    def get_n_cycles(self) -> int:
        """Get thermal cycles per year."""
        return self.spin_cycles.GetValue()
    
    def get_delta_t(self) -> float:
        """Get temperature swing."""
        return self.spin_dt.GetValue()
    
    def on_value_change(self, event):
        """Handle value changes."""
        if self.on_settings_change:
            self.on_settings_change()


class ReliabilityMainDialog(wx.Dialog):
    """
    Main dialog for the reliability calculator.
    
    Layout:
    +--------------------------------------------------+
    |  [Project: path]  [Load] [Save Config] [Export]  |
    +--------------------------------------------------+
    | Sheet List  |  Block Diagram Editor              |
    |             |                                     |
    |             |                                     |
    |-------------|                                     |
    | Settings    |                                     |
    |             |                                     |
    +--------------------------------------------------+
    | Component Details                    | Results   |
    |                                      |           |
    +--------------------------------------------------+
    """
    
    def __init__(self, parent):
        super().__init__(
            parent,
            title="Reliability Calculator",
            size=(1400, 900),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX
        )
        
        # State
        self.project_path: Optional[str] = None
        self.parser: Optional[KiCadSchematicParser] = None
        self.config_path: Optional[str] = None
        
        # Sheet -> calculated data
        self.sheet_data: Dict[str, Dict] = {}
        
        self._create_ui()
        self._bind_events()
        
        # Load mock data for testing
        self._load_mock_data()
    
    def _create_ui(self):
        """Create the user interface."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Toolbar
        toolbar = self._create_toolbar()
        main_sizer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 5)
        
        # Main content splitter
        self.main_splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        
        # Left panel (sheets + settings)
        left_panel = wx.Panel(self.main_splitter)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.sheet_panel = SheetListPanel(left_panel)
        left_sizer.Add(self.sheet_panel, 2, wx.EXPAND)
        
        self.settings_panel = SettingsPanel(left_panel)
        left_sizer.Add(self.settings_panel, 0, wx.EXPAND | wx.TOP, 10)
        
        left_panel.SetSizer(left_sizer)
        
        # Right panel (editor + details)
        right_splitter = wx.SplitterWindow(self.main_splitter, style=wx.SP_LIVE_UPDATE)
        
        # Block editor
        editor_panel = wx.Panel(right_splitter)
        editor_sizer = wx.BoxSizer(wx.VERTICAL)
        
        editor_header = wx.StaticText(editor_panel, label="System Block Diagram")
        editor_header.SetFont(editor_header.GetFont().Bold())
        editor_sizer.Add(editor_header, 0, wx.ALL, 5)
        
        # Instructions
        instructions = wx.StaticText(
            editor_panel,
            label="Drag blocks to arrange. Select multiple (drag rectangle) → right-click to group. "
                  "Double-click groups to change type."
        )
        instructions.SetForegroundColour(wx.Colour(100, 100, 100))
        editor_sizer.Add(instructions, 0, wx.LEFT | wx.BOTTOM, 5)
        
        self.block_editor = BlockEditorCanvas(editor_panel)
        editor_sizer.Add(self.block_editor, 1, wx.EXPAND | wx.ALL, 5)
        
        editor_panel.SetSizer(editor_sizer)
        
        # Bottom panel (details + results)
        bottom_splitter = wx.SplitterWindow(right_splitter, style=wx.SP_LIVE_UPDATE)
        
        self.details_panel = ComponentDetailsPanel(bottom_splitter)
        
        # Results panel
        results_panel = wx.Panel(bottom_splitter)
        results_sizer = wx.BoxSizer(wx.VERTICAL)
        
        results_header = wx.StaticText(results_panel, label="System Results")
        results_header.SetFont(results_header.GetFont().Bold())
        results_sizer.Add(results_header, 0, wx.ALL, 5)
        
        self.results_text = wx.TextCtrl(
            results_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
        )
        self.results_text.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, 
                                          wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        results_sizer.Add(self.results_text, 1, wx.EXPAND | wx.ALL, 5)
        
        # Calculate button
        self.btn_calculate = wx.Button(results_panel, label="Calculate System Reliability")
        self.btn_calculate.Bind(wx.EVT_BUTTON, self.on_calculate)
        results_sizer.Add(self.btn_calculate, 0, wx.EXPAND | wx.ALL, 5)
        
        results_panel.SetSizer(results_sizer)
        
        # Set up splitters
        bottom_splitter.SplitVertically(self.details_panel, results_panel, 500)
        right_splitter.SplitHorizontally(editor_panel, bottom_splitter, 400)
        self.main_splitter.SplitVertically(left_panel, right_splitter, 280)
        
        main_sizer.Add(self.main_splitter, 1, wx.EXPAND | wx.ALL, 5)
        
        # Status bar
        self.status = wx.StaticText(self, label="Ready")
        main_sizer.Add(self.status, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(main_sizer)
    
    def _create_toolbar(self) -> wx.Panel:
        """Create the toolbar panel."""
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Project path
        sizer.Add(wx.StaticText(panel, label="Project:"), 0, 
                  wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.txt_project = wx.TextCtrl(panel, value="(No project loaded)", 
                                        style=wx.TE_READONLY)
        sizer.Add(self.txt_project, 1, wx.RIGHT, 10)
        
        # Buttons
        self.btn_load = wx.Button(panel, label="Load Project...")
        self.btn_load.Bind(wx.EVT_BUTTON, self.on_load_project)
        sizer.Add(self.btn_load, 0, wx.RIGHT, 5)
        
        self.btn_save_config = wx.Button(panel, label="Save Config")
        self.btn_save_config.Bind(wx.EVT_BUTTON, self.on_save_config)
        sizer.Add(self.btn_save_config, 0, wx.RIGHT, 5)
        
        self.btn_load_config = wx.Button(panel, label="Load Config")
        self.btn_load_config.Bind(wx.EVT_BUTTON, self.on_load_config)
        sizer.Add(self.btn_load_config, 0, wx.RIGHT, 5)
        
        sizer.Add(wx.StaticLine(panel, style=wx.LI_VERTICAL), 0, 
                  wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        self.btn_inject = wx.Button(panel, label="Inject Tables")
        self.btn_inject.Bind(wx.EVT_BUTTON, self.on_inject_tables)
        sizer.Add(self.btn_inject, 0, wx.RIGHT, 5)
        
        self.btn_export = wx.Button(panel, label="Export Report...")
        self.btn_export.Bind(wx.EVT_BUTTON, self.on_export_report)
        sizer.Add(self.btn_export, 0)
        
        panel.SetSizer(sizer)
        return panel
    
    def _bind_events(self):
        """Bind event handlers."""
        self.sheet_panel.on_sheet_add = self.on_add_sheet_to_diagram
        self.sheet_panel.on_sheet_selected = self.on_sheet_selected
        self.block_editor.on_selection_change = self.on_block_selection_change
        self.block_editor.on_structure_change = self.on_structure_change
        self.settings_panel.on_settings_change = self.on_settings_change
    
    def _load_mock_data(self):
        """Load mock data for testing."""
        # Use the sheet names from the original code
        mock_sheets = [
            "/Project Architecture/",
            "/Project Architecture/Power/",
            "/Project Architecture/Power/Protection Satellite 24V/",
            "/Project Architecture/Power/Battery Charger/",
            "/Project Architecture/Power/LDO_3v3_sat/",
            "/Project Architecture/Power/Ideal Diode Satellite/",
            "/Project Architecture/Power/Protection Battery/",
            "/Project Architecture/Power/System On Logic/",
            "/Project Architecture/Power/System On Logic/On Arbitration/",
            "/Project Architecture/Power/System On Logic/Off Arbitration/",
            "/Project Architecture/Power/System On Logic/On Memory/",
            "/Project Architecture/Power/LDO_3v3_bat/",
            "/Project Architecture/Power/Ideal Diode Battery/",
            "/Project Architecture/Power/Deploy/",
            "/Project Architecture/Power/Deploy/Boost/",
            "/Project Architecture/Power/Deploy/Boost/TRIGGER_LOGIC_B1/",
            "/Project Architecture/Power/Deploy/Boost/TRIGGER_LOGIC_B2/",
            "/Project Architecture/Power/Deploy/Buck/",
            "/Project Architecture/Power/Deploy/Buck/TRIGGER_LOGIC_B3/",
            "/Project Architecture/Power/Unlatch Arbitration/",
            "/Project Architecture/Power/Passivate Arbitration/",
            "/Project Architecture/Power/Passivate Memory/",
            "/Project Architecture/Control/MCU_A/",
            "/Project Architecture/Trigger IDD/",
        ]
        
        self.parser = create_mock_parser(mock_sheets)
        self.sheet_panel.set_sheets(mock_sheets)
        self.txt_project.SetValue("Mock Project (for testing)")
        
        # Pre-calculate sheet data
        self._calculate_all_sheets()
    
    def _calculate_all_sheets(self):
        """Calculate reliability for all sheets."""
        if not self.parser:
            return
        
        mission_hours = self.settings_panel.get_mission_hours()
        n_cycles = self.settings_panel.get_n_cycles()
        delta_t = self.settings_panel.get_delta_t()
        
        for sheet_path in self.parser.get_sheet_paths():
            components = self.parser.get_sheet_components(sheet_path)
            
            comp_data = []
            total_lambda = 0.0
            
            for comp in components:
                # Build params dict from component fields
                params = {
                    "reference": comp.reference,
                    "n_cycles": n_cycles,
                    "delta_t": delta_t,
                    "t_ambient": comp.get_float_field("Temperature_Ambient", 25.0),
                    "t_junction": comp.get_float_field("Temperature_Junction", 85.0),
                    "operating_power": comp.get_float_field("Operating_Power", 0.01),
                    "rated_power": comp.get_float_field("Rated_Power", 0.125),
                    "transistor_type": comp.get_field("Transistor_Type", "MOS"),
                    "diode_type": comp.get_field("Diode_Type", "signal"),
                    "ic_type": comp.get_field("IC_Type", "MOS Standard, Digital circuits, 20000 transistors"),
                    "package": comp.get_field("Package", "SOT-23, 3 pins"),
                    "inductor_type": comp.get_field("Inductor_Type", "Power Inductor"),
                    "power_loss": comp.get_float_field("Power_Loss", 0.1),
                    "surface_area": comp.get_float_field("Surface_Area", 100.0),
                    "construction_year": comp.get_int_field("Construction_Year", 2020),
                }
                
                comp_class = comp.get_field("Reliability_Class", comp.get_field("Class", ""))
                lam = calculate_component_lambda(comp_class, params)
                r = reliability(lam, mission_hours)
                
                total_lambda += lam
                
                comp_data.append({
                    "reference": comp.reference,
                    "class": comp_class,
                    "lambda": lam,
                    "reliability": r,
                })
            
            sheet_r = reliability(total_lambda, mission_hours)
            
            self.sheet_data[sheet_path] = {
                "components": comp_data,
                "total_lambda": total_lambda,
                "reliability": sheet_r,
            }
    
    def _calculate_system_reliability(self) -> Tuple[float, float]:
        """
        Calculate system reliability based on block diagram structure.
        
        Returns:
            (system_reliability, system_lambda)
        """
        mission_hours = self.settings_panel.get_mission_hours()
        
        def calc_block(block_id: str) -> float:
            """Recursively calculate reliability for a block."""
            block = self.block_editor.blocks.get(block_id)
            if not block:
                return 1.0
            
            if block.is_group:
                # Calculate children reliabilities
                child_rs = [calc_block(cid) for cid in block.children]
                
                if block.connection_type == ConnectionType.SERIES:
                    r = r_series(child_rs)
                elif block.connection_type == ConnectionType.PARALLEL:
                    r = r_parallel(child_rs)
                else:  # K_OF_N
                    r = r_k_of_n(child_rs, block.k_value)
                
                block.reliability = r
                block.lambda_val = lambda_from_reliability(r, mission_hours)
                return r
            else:
                # Leaf block - get from sheet data
                data = self.sheet_data.get(block.name, {})
                r = data.get("reliability", 1.0)
                lam = data.get("total_lambda", 0.0)
                
                block.reliability = r
                block.lambda_val = lam
                return r
        
        # Start from root
        root_id = self.block_editor.root_group
        if not root_id:
            return 1.0, 0.0
        
        # Calculate all blocks in diagram
        for block_id, block in self.block_editor.blocks.items():
            if not block.is_group:
                data = self.sheet_data.get(block.name, {})
                block.reliability = data.get("reliability", 1.0)
                block.lambda_val = data.get("total_lambda", 0.0)
        
        system_r = calc_block(root_id)
        system_lambda = lambda_from_reliability(system_r, mission_hours)
        
        self.block_editor.Refresh()
        
        return system_r, system_lambda
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    
    def on_load_project(self, event):
        """Load a KiCad project."""
        dlg = wx.DirDialog(
            self,
            "Select KiCad Project Directory",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST
        )
        
        if dlg.ShowModal() == wx.ID_OK:
            self.project_path = dlg.GetPath()
            self.txt_project.SetValue(self.project_path)
            
            # Parse schematic
            self.parser = KiCadSchematicParser(self.project_path)
            if self.parser.parse():
                sheets = self.parser.get_sheet_paths()
                self.sheet_panel.set_sheets(sheets)
                self._calculate_all_sheets()
                self.status.SetLabel(f"Loaded {len(sheets)} sheets")
            else:
                wx.MessageBox(
                    "Could not parse schematic files in the selected directory.",
                    "Parse Error",
                    wx.OK | wx.ICON_ERROR
                )
        
        dlg.Destroy()
    
    def on_save_config(self, event):
        """Save current configuration."""
        if not self.project_path:
            config_dir = os.getcwd()
        else:
            config_dir = self.project_path
        
        dlg = wx.FileDialog(
            self,
            "Save Configuration",
            defaultDir=config_dir,
            defaultFile="reliability_config.json",
            wildcard="JSON files (*.json)|*.json",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        
        if dlg.ShowModal() == wx.ID_OK:
            config = {
                "project_path": self.project_path,
                "structure": self.block_editor.get_structure(),
                "settings": {
                    "mission_years": self.settings_panel.spin_years.GetValue(),
                    "n_cycles": self.settings_panel.spin_cycles.GetValue(),
                    "delta_t": self.settings_panel.spin_dt.GetValue(),
                }
            }
            
            with open(dlg.GetPath(), 'w') as f:
                json.dump(config, f, indent=2)
            
            self.status.SetLabel(f"Configuration saved to {dlg.GetPath()}")
        
        dlg.Destroy()
    
    def on_load_config(self, event):
        """Load a saved configuration."""
        dlg = wx.FileDialog(
            self,
            "Load Configuration",
            wildcard="JSON files (*.json)|*.json",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        )
        
        if dlg.ShowModal() == wx.ID_OK:
            try:
                with open(dlg.GetPath(), 'r') as f:
                    config = json.load(f)
                
                # Restore settings
                settings = config.get("settings", {})
                self.settings_panel.spin_years.SetValue(settings.get("mission_years", 5))
                self.settings_panel.spin_cycles.SetValue(settings.get("n_cycles", 5256))
                self.settings_panel.spin_dt.SetValue(settings.get("delta_t", 3.0))
                
                # Restore structure
                self.block_editor.load_structure(config.get("structure", {}))
                
                self._calculate_all_sheets()
                self.on_calculate(None)
                
                self.status.SetLabel(f"Configuration loaded from {dlg.GetPath()}")
                
            except Exception as e:
                wx.MessageBox(
                    f"Error loading configuration: {str(e)}",
                    "Load Error",
                    wx.OK | wx.ICON_ERROR
                )
        
        dlg.Destroy()
    
    def on_add_sheet_to_diagram(self, sheet_path: str):
        """Add a sheet to the block diagram."""
        # Check if already added
        for block in self.block_editor.blocks.values():
            if block.name == sheet_path:
                return
        
        # Create short name
        name = sheet_path.rstrip('/').split('/')[-1] or "Root"
        
        # Add block
        block = self.block_editor.add_block(
            f"sheet_{len(self.block_editor.blocks)}",
            sheet_path,
            name
        )
        
        # Update with reliability data
        data = self.sheet_data.get(sheet_path, {})
        block.reliability = data.get("reliability", 1.0)
        block.lambda_val = data.get("total_lambda", 0.0)
        
        # Add to root group
        root = self.block_editor.blocks.get(self.block_editor.root_group)
        if root and block.id not in root.children:
            root.children.append(block.id)
        
        self.block_editor.Refresh()
    
    def on_sheet_selected(self, sheet_path: str):
        """Handle sheet selection in the list."""
        data = self.sheet_data.get(sheet_path, {})
        self.details_panel.set_components(
            sheet_path,
            data.get("components", []),
            data.get("total_lambda", 0.0),
            data.get("reliability", 1.0)
        )
    
    def on_block_selection_change(self, block_id: Optional[str]):
        """Handle block selection in the editor."""
        if block_id:
            block = self.block_editor.blocks.get(block_id)
            if block and not block.is_group:
                data = self.sheet_data.get(block.name, {})
                self.details_panel.set_components(
                    block.name,
                    data.get("components", []),
                    data.get("total_lambda", 0.0),
                    data.get("reliability", 1.0)
                )
    
    def on_structure_change(self):
        """Handle changes to the block diagram structure."""
        # Recalculate
        self.on_calculate(None)
    
    def on_settings_change(self):
        """Handle changes to settings."""
        self._calculate_all_sheets()
        self.on_calculate(None)
    
    def on_calculate(self, event):
        """Calculate and display system reliability."""
        system_r, system_lambda = self._calculate_system_reliability()
        mission_hours = self.settings_panel.get_mission_hours()
        mission_years = mission_hours / (365 * 24)
        
        results = [
            "=" * 40,
            "SYSTEM RELIABILITY RESULTS",
            "=" * 40,
            "",
            f"Mission Duration: {mission_years:.1f} years ({mission_hours:.0f} hours)",
            "",
            f"System Reliability:     R = {system_r:.6f}",
            f"System Failure Rate:    λ = {system_lambda:.2e} /hour",
            f"Mean Time to Failure:   MTTF = {1/system_lambda:.2e} hours" if system_lambda > 0 else "",
            "",
            "=" * 40,
            "BLOCK SUMMARY",
            "=" * 40,
        ]
        
        # Add block details
        for block_id, block in sorted(self.block_editor.blocks.items()):
            if block.id.startswith("__"):
                continue  # Skip internal blocks
            
            if block.is_group:
                conn_type = block.connection_type.value.upper()
                if block.connection_type == ConnectionType.K_OF_N:
                    conn_type = f"{block.k_value}-of-{len(block.children)}"
                results.append(f"\n[GROUP: {conn_type}]")
                results.append(f"  R = {block.reliability:.6f}")
            else:
                results.append(f"\n{block.display_name}")
                results.append(f"  λ = {block.lambda_val:.2e}, R = {block.reliability:.6f}")
        
        self.results_text.SetValue('\n'.join(results))
        self.status.SetLabel(f"System R = {system_r:.6f}")
    
    def on_inject_tables(self, event):
        """Inject reliability tables into schematic files."""
        if not self.parser:
            wx.MessageBox(
                "No project loaded. Please load a KiCad project first.",
                "No Project",
                wx.OK | wx.ICON_WARNING
            )
            return
        
        generator = KiCadTableGenerator()
        mission_hours = self.settings_panel.get_mission_hours()
        
        success_count = 0
        error_count = 0
        
        for sheet_path, data in self.sheet_data.items():
            sheet = self.parser.sheets.get(sheet_path)
            if not sheet:
                continue
            
            table = generator.create_table(
                sheet_path,
                data.get("components", []),
                data.get("total_lambda", 0.0),
                data.get("reliability", 1.0)
            )
            
            if generator.inject_into_schematic(sheet.filename, table):
                success_count += 1
            else:
                error_count += 1
        
        wx.MessageBox(
            f"Tables injected into {success_count} schematics.\n"
            f"Errors: {error_count}\n\n"
            "Note: You may need to reload the schematic in KiCad to see changes.",
            "Injection Complete",
            wx.OK | wx.ICON_INFORMATION
        )
    
    def on_export_report(self, event):
        """Export reliability report."""
        dlg = wx.FileDialog(
            self,
            "Export Report",
            wildcard="HTML files (*.html)|*.html|Markdown files (*.md)|*.md|CSV files (*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            filter_idx = dlg.GetFilterIndex()
            
            generator = KiCadTableGenerator()
            report_gen = ReliabilityReportGenerator()
            
            # Create tables
            tables = {}
            for sheet_path, data in self.sheet_data.items():
                table = generator.create_table(
                    sheet_path,
                    data.get("components", []),
                    data.get("total_lambda", 0.0),
                    data.get("reliability", 1.0)
                )
                tables[sheet_path] = table
            
            system_r, system_lambda = self._calculate_system_reliability()
            
            # Generate report
            if filter_idx == 0:  # HTML
                content = report_gen.generate_html(tables, system_r, system_lambda)
            elif filter_idx == 1:  # Markdown
                content = report_gen.generate_markdown(tables, system_r, system_lambda)
            else:  # CSV
                content = report_gen.generate_csv(tables)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.status.SetLabel(f"Report exported to {path}")
        
        dlg.Destroy()


# =============================================================================
# Standalone launcher
# =============================================================================

def main():
    """Run as standalone application."""
    app = wx.App()
    dlg = ReliabilityMainDialog(None)
    dlg.ShowModal()
    dlg.Destroy()
    app.MainLoop()


if __name__ == "__main__":
    main()
