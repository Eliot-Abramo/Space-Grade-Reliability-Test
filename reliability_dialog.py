"""
Main Reliability Calculator Dialog

The primary UI for the reliability calculator with integrated component editor.
Based on IEC TR 62380 reliability prediction methodology.
"""

import os
import json
import wx
import wx.lib.scrolledpanel as scrolled
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .block_editor import BlockEditor, Block
from .reliability_math import (
    get_component_types, calculate_component_lambda, 
    reliability_from_lambda, lambda_from_reliability,
    r_series, r_parallel, r_k_of_n, calculate_lambda,
    get_field_definitions
)
from .component_editor import (
    ComponentEditorDialog, BatchComponentEditorDialog, ComponentData,
    classify_component, QuickReferenceDialog, generate_kicad_fields,
    parse_kicad_fields
)
from .schematic_parser import SchematicParser, create_test_data


# ConnectionType is now just string constants: "series", "parallel", "k_of_n"


class SheetPanel(wx.Panel):
    """Panel listing available sheets."""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.sheets = []
        self.on_add = None
        self.on_edit = None
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        header = wx.StaticText(self, label="📋 Schematic Sheets")
        header.SetFont(header.GetFont().Bold())
        sizer.Add(header, 0, wx.ALL, 5)
        
        self.list = wx.ListBox(self, style=wx.LB_EXTENDED)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_dclick)
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 5)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add = wx.Button(self, label="Add Selected")
        self.btn_add.Bind(wx.EVT_BUTTON, self._on_add)
        btn_sizer.Add(self.btn_add, 1, wx.RIGHT, 3)
        self.btn_all = wx.Button(self, label="Add All")
        self.btn_all.Bind(wx.EVT_BUTTON, self._on_add_all)
        btn_sizer.Add(self.btn_all, 1)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.btn_edit = wx.Button(self, label="✏️ Edit Components...")
        self.btn_edit.Bind(wx.EVT_BUTTON, self._on_edit)
        self.btn_edit.SetToolTip("Edit reliability fields for components in selected sheet")
        sizer.Add(self.btn_edit, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        
        self.SetSizer(sizer)
    
    def set_sheets(self, sheets: List[str]):
        self.sheets = sheets
        self.list.Set(sheets)
    
    def _on_add(self, event):
        selections = self.list.GetSelections()
        if self.on_add:
            for i in selections:
                self.on_add(self.sheets[i])
    
    def _on_add_all(self, event):
        if self.on_add:
            for s in self.sheets:
                self.on_add(s)
    
    def _on_dclick(self, event):
        self._on_add(event)
    
    def _on_edit(self, event):
        if self.on_edit:
            selections = self.list.GetSelections()
            if selections:
                self.on_edit([self.sheets[i] for i in selections])
            else:
                wx.MessageBox("Please select a sheet first.", "No Selection", wx.OK | wx.ICON_INFORMATION)


class ComponentPanel(scrolled.ScrolledPanel):
    """Panel showing component details with edit capability."""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.current_sheet = None
        self.on_component_edit = None
        
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.header = wx.StaticText(self, label="📦 Components")
        self.header.SetFont(self.header.GetFont().Bold())
        header_sizer.Add(self.header, 1, wx.ALIGN_CENTER_VERTICAL)
        
        self.btn_edit = wx.Button(self, label="Edit", size=(50, -1))
        self.btn_edit.Bind(wx.EVT_BUTTON, self._on_edit)
        self.btn_edit.SetToolTip("Edit selected component's reliability fields")
        header_sizer.Add(self.btn_edit, 0)
        
        self.sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SIMPLE)
        self.list.InsertColumn(0, "Ref", width=50)
        self.list.InsertColumn(1, "Value", width=70)
        self.list.InsertColumn(2, "Type", width=100)
        self.list.InsertColumn(3, "λ (FIT)", width=70)
        self.list.InsertColumn(4, "R", width=60)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_dclick)
        self.sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 5)
        
        self.summary = wx.StaticText(self, label="")
        self.summary.SetFont(self.summary.GetFont().Bold())
        self.sizer.Add(self.summary, 0, wx.ALL, 5)
        
        self.SetSizer(self.sizer)
        self.SetupScrolling()
    
    def set_data(self, sheet: str, components: List[Dict], total_lam: float, r: float):
        self.current_sheet = sheet
        self.header.SetLabel(f"📦 {sheet.split('/')[-2] or sheet}")
        
        self.list.DeleteAllItems()
        for i, c in enumerate(components):
            idx = self.list.InsertItem(i, c.get("ref", "?"))
            self.list.SetItem(idx, 1, c.get("value", "")[:10])
            self.list.SetItem(idx, 2, c.get("class", "")[:15])
            lam = c.get('lambda', 0)
            fit = lam * 1e9
            self.list.SetItem(idx, 3, f"{fit:.2f}")
            self.list.SetItem(idx, 4, f"{c.get('r', 1):.4f}")
        
        fit_total = total_lam * 1e9
        self.summary.SetLabel(f"Total: λ = {fit_total:.2f} FIT, R = {r:.6f}")
        self.Layout()
    
    def _on_edit(self, event):
        idx = self.list.GetFirstSelected()
        if idx >= 0 and self.on_component_edit:
            ref = self.list.GetItemText(idx, 0)
            self.on_component_edit(self.current_sheet, ref)
        else:
            wx.MessageBox("Please select a component first.", "No Selection", wx.OK | wx.ICON_INFORMATION)
    
    def _on_dclick(self, event):
        if self.on_component_edit:
            ref = self.list.GetItemText(event.GetIndex(), 0)
            self.on_component_edit(self.current_sheet, ref)


class SettingsPanel(wx.Panel):
    """Settings panel."""
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.on_change = None
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        header = wx.StaticText(self, label="⚙️ Mission Profile")
        header.SetFont(header.GetFont().Bold())
        sizer.Add(header, 0, wx.ALL, 5)
        
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Mission:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.years = wx.SpinCtrl(self, min=1, max=30, initial=5, size=(60, -1))
        self.years.Bind(wx.EVT_SPINCTRL, self._on_change)
        row.Add(self.years, 0, wx.RIGHT, 3)
        row.Add(wx.StaticText(self, label="years"), 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(row, 0, wx.ALL, 5)
        
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Cycles/yr:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.cycles = wx.SpinCtrl(self, min=100, max=20000, initial=5256, size=(70, -1))
        self.cycles.Bind(wx.EVT_SPINCTRL, self._on_change)
        self.cycles.SetToolTip("Annual thermal cycles (5256 = LEO satellite)")
        row.Add(self.cycles, 0)
        sizer.Add(row, 0, wx.ALL, 5)
        
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="ΔT:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.dt = wx.SpinCtrlDouble(self, min=0.5, max=30, initial=3, inc=0.5, size=(60, -1))
        self.dt.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_change)
        self.dt.SetToolTip("Temperature swing per cycle (°C)")
        row.Add(self.dt, 0, wx.RIGHT, 3)
        row.Add(wx.StaticText(self, label="°C"), 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(row, 0, wx.ALL, 5)
        
        help_btn = wx.Button(self, label="📖 IEC 62380 Reference")
        help_btn.Bind(wx.EVT_BUTTON, self._on_help)
        sizer.Add(help_btn, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(sizer)
    
    def get_hours(self) -> float:
        return self.years.GetValue() * 365 * 24
    
    def get_cycles(self) -> int:
        return self.cycles.GetValue()
    
    def get_dt(self) -> float:
        return self.dt.GetValue()
    
    def _on_change(self, event):
        if self.on_change:
            self.on_change()
    
    def _on_help(self, event):
        dlg = QuickReferenceDialog(self)
        dlg.ShowModal()
        dlg.Destroy()


class ReliabilityMainDialog(wx.Dialog):
    """Main reliability calculator dialog."""
    
    def __init__(self, parent, project_path: str = None):
        super().__init__(
            parent,
            title="⚡ Reliability Calculator (IEC TR 62380)",
            size=(1350, 900),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX
        )
        
        self.project_path = project_path
        self.parser: Optional[SchematicParser] = None
        self.sheet_data: Dict[str, Dict] = {}
        self.component_edits: Dict[str, Dict[str, Dict]] = {}
        
        self._create_ui()
        self._bind_events()
        
        if project_path:
            self._load_project(project_path)
        else:
            self._load_test_data()
    
    def _create_ui(self):
        main = wx.BoxSizer(wx.VERTICAL)
        
        toolbar = self._create_toolbar()
        main.Add(toolbar, 0, wx.EXPAND | wx.ALL, 5)
        
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        
        left = wx.Panel(splitter)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        self.sheet_panel = SheetPanel(left)
        left_sizer.Add(self.sheet_panel, 2, wx.EXPAND)
        self.settings_panel = SettingsPanel(left)
        left_sizer.Add(self.settings_panel, 0, wx.EXPAND | wx.TOP, 5)
        left.SetSizer(left_sizer)
        
        right = wx.SplitterWindow(splitter, style=wx.SP_LIVE_UPDATE)
        
        editor_panel = wx.Panel(right)
        editor_sizer = wx.BoxSizer(wx.VERTICAL)
        editor_header = wx.StaticText(editor_panel, label="🔗 System Block Diagram")
        editor_header.SetFont(editor_header.GetFont().Bold())
        editor_sizer.Add(editor_header, 0, wx.ALL, 5)
        hint = wx.StaticText(editor_panel, 
            label="Drag rectangle to select → Right-click to Group as Series/Parallel/K-of-N")
        hint.SetForegroundColour(wx.Colour(100, 100, 100))
        editor_sizer.Add(hint, 0, wx.LEFT | wx.BOTTOM, 5)
        self.editor = BlockEditor(editor_panel)
        editor_sizer.Add(self.editor, 1, wx.EXPAND | wx.ALL, 5)
        editor_panel.SetSizer(editor_sizer)
        
        bottom = wx.SplitterWindow(right, style=wx.SP_LIVE_UPDATE)
        self.comp_panel = ComponentPanel(bottom)
        
        results_panel = wx.Panel(bottom)
        results_sizer = wx.BoxSizer(wx.VERTICAL)
        results_header = wx.StaticText(results_panel, label="📊 System Results")
        results_header.SetFont(results_header.GetFont().Bold())
        results_sizer.Add(results_header, 0, wx.ALL, 5)
        self.results = wx.TextCtrl(results_panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.results.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        results_sizer.Add(self.results, 1, wx.EXPAND | wx.ALL, 5)
        btn_calc = wx.Button(results_panel, label="🔄 Calculate System Reliability")
        btn_calc.SetFont(btn_calc.GetFont().Bold())
        btn_calc.Bind(wx.EVT_BUTTON, self._on_calculate)
        results_sizer.Add(btn_calc, 0, wx.EXPAND | wx.ALL, 5)
        results_panel.SetSizer(results_sizer)
        
        bottom.SplitVertically(self.comp_panel, results_panel, 450)
        right.SplitHorizontally(editor_panel, bottom, 380)
        splitter.SplitVertically(left, right, 280)
        
        main.Add(splitter, 1, wx.EXPAND | wx.ALL, 5)
        
        self.status = wx.StaticText(self, label="Ready - Double-click components to edit reliability fields")
        main.Add(self.status, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(main)
    
    def _create_toolbar(self) -> wx.Panel:
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        sizer.Add(wx.StaticText(panel, label="Project:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.txt_project = wx.TextCtrl(panel, value="(none)", style=wx.TE_READONLY)
        sizer.Add(self.txt_project, 1, wx.RIGHT, 10)
        
        btn_load = wx.Button(panel, label="📂 Open...")
        btn_load.Bind(wx.EVT_BUTTON, self._on_open)
        sizer.Add(btn_load, 0, wx.RIGHT, 5)
        
        btn_save = wx.Button(panel, label="💾 Save Config")
        btn_save.Bind(wx.EVT_BUTTON, self._on_save)
        sizer.Add(btn_save, 0, wx.RIGHT, 5)
        
        btn_load_cfg = wx.Button(panel, label="📁 Load Config")
        btn_load_cfg.Bind(wx.EVT_BUTTON, self._on_load_config)
        sizer.Add(btn_load_cfg, 0, wx.RIGHT, 15)
        
        btn_batch = wx.Button(panel, label="✏️ Batch Edit All")
        btn_batch.Bind(wx.EVT_BUTTON, self._on_batch_edit)
        btn_batch.SetToolTip("Edit reliability fields for all components")
        sizer.Add(btn_batch, 0, wx.RIGHT, 5)
        
        btn_export = wx.Button(panel, label="📄 Export Report")
        btn_export.Bind(wx.EVT_BUTTON, self._on_export)
        sizer.Add(btn_export, 0)
        
        panel.SetSizer(sizer)
        return panel
    
    def _bind_events(self):
        self.editor.on_block_activate = self._on_block_activate
        self.sheet_panel.on_add = self._add_sheet
        self.sheet_panel.on_edit = self._edit_sheet_components
        self.editor.on_selection_change = self._on_block_select
        self.editor.on_structure_change = self._on_calculate
        self.settings_panel.on_change = self._recalculate_all
        self.comp_panel.on_component_edit = self._edit_single_component
    
    def _load_project(self, path: str):
        self.project_path = path
        self.txt_project.SetValue(path)
        
        self.parser = SchematicParser(path)
        if self.parser.parse():
            sheets = self.parser.get_sheet_paths()
            self.sheet_panel.set_sheets(sheets)
            self._calculate_sheets()
            self.status.SetLabel(f"Loaded {len(sheets)} sheets from {path}")
        else:
            wx.MessageBox(f"Could not parse schematics in:\n{path}", 
                         "Parse Error", wx.OK | wx.ICON_WARNING)
    
    def _load_test_data(self):
        sheets = [
            "/Project Architecture/",
            "/Project Architecture/Power/",
            "/Project Architecture/Power/Protection Satellite 24V/",
            "/Project Architecture/Power/Battery Charger/",
            "/Project Architecture/Power/LDO_3v3_sat/",
            "/Project Architecture/Power/System On Logic/",
            "/Project Architecture/Control/MCU_A/",
            "/Project Architecture/Trigger IDD/",
        ]
        
        self.parser = create_test_data(sheets)
        self.sheet_panel.set_sheets(sheets)
        self.txt_project.SetValue("Test Data")
        self._calculate_sheets()
        self.status.SetLabel("Loaded test data")
    
    def _calculate_sheets(self):
        if not self.parser:
            return
        
        hours = self.settings_panel.get_hours()
        cycles = self.settings_panel.get_cycles()
        dt = self.settings_panel.get_dt()
        
        for path in self.parser.get_sheet_paths():
            components = self.parser.get_sheet_components(path)
            
            comp_data = []
            total_lam = 0.0
            
            for c in components:
                edited = self.component_edits.get(path, {}).get(c.reference, {})
                
                if edited:
                    comp_type = edited.get("_component_type", "Resistor")
                    params = edited.copy()
                    params["n_cycles"] = cycles
                    params["delta_t"] = dt
                    result = calculate_component_lambda(comp_type, params)
                    lam = result.get("lambda_total", 0)
                    cls_name = comp_type
                else:
                    cls = c.get_field("Reliability_Class", c.get_field("Class", ""))
                    if not cls:
                        cls = classify_component(c.reference, c.value, {})
                    
                    params = {
                        "n_cycles": cycles,
                        "delta_t": dt,
                        "t_ambient": c.get_float("T_Ambient", 25),
                        "t_junction": c.get_float("T_Junction", 85),
                        "operating_power": c.get_float("Operating_Power", 0.01),
                        "rated_power": c.get_float("Rated_Power", 0.125),
                    }
                    
                    lam = calculate_lambda(cls or "Resistor", params)
                    cls_name = cls or "Unknown"
                
                r = reliability_from_lambda(lam, hours)
                total_lam += lam
                
                comp_data.append({
                    "ref": c.reference,
                    "value": c.value,
                    "class": cls_name,
                    "lambda": lam,
                    "r": r,
                })
            
            sheet_r = reliability_from_lambda(total_lam, hours)
            
            self.sheet_data[path] = {
                "components": comp_data,
                "lambda": total_lam,
                "r": sheet_r,
            }
    
    def _recalculate_all(self):
        self._calculate_sheets()
        
        for bid, b in self.editor.blocks.items():
            if not b.is_group:
                data = self.sheet_data.get(b.name, {})
                b.reliability = data.get("r", 1.0)
                b.lambda_val = data.get("lambda", 0.0)
        
        self._on_calculate(None)
    
    def _calculate_system(self) -> Tuple[float, float]:
        hours = self.settings_panel.get_hours()
        
        def calc(block_id: str) -> float:
            b = self.editor.blocks.get(block_id)
            if not b:
                return 1.0
            
            if b.is_group:
                child_rs = [calc(cid) for cid in b.children]
                
                if b.connection_type == "series":
                    r = r_series(child_rs)
                elif b.connection_type == "parallel":
                    r = r_parallel(child_rs)
                else:
                    r = r_k_of_n(child_rs, b.k_value)
                
                b.reliability = r
                b.lambda_val = lambda_from_reliability(r, hours)
                return r
            else:
                data = self.sheet_data.get(b.name, {})
                b.reliability = data.get("r", 1.0)
                b.lambda_val = data.get("lambda", 0.0)
                return b.reliability
        
        if not self.editor.root_id:
            return 1.0, 0.0
        
        sys_r = calc(self.editor.root_id)
        sys_lam = lambda_from_reliability(sys_r, hours)
        
        self.editor.Refresh()
        return sys_r, sys_lam
    
    def _add_sheet(self, path: str):
        for b in self.editor.blocks.values():
            if b.name == path:
                return
        
        label = path.rstrip('/').split('/')[-1] or "Root"
        block = self.editor.add_block(f"sheet_{len(self.editor.blocks)}", path, label)
        
        data = self.sheet_data.get(path, {})
        block.reliability = data.get("r", 1.0)
        block.lambda_val = data.get("lambda", 0.0)
        
        self.editor.Refresh()
    
    def _on_block_select(self, block_id: Optional[str]):
        if block_id:
            b = self.editor.blocks.get(block_id)
            if b and not b.is_group:
                data = self.sheet_data.get(b.name, {})
                self.comp_panel.set_data(
                    b.name,
                    data.get("components", []),
                    data.get("lambda", 0),
                    data.get("r", 1)
                )

    def _on_block_activate(self, block_id: str, sheet_path: str):
            """Handle double-click on a sheet block - open component editor."""
            components = self.parser.get_sheet_components(sheet_path) if self.parser else []
            
            if not components:
                wx.MessageBox(f"No components found in {sheet_path}", "Info", wx.ICON_INFORMATION)
                return
            
            # Convert to ComponentData for the batch editor
            comp_data_list = []
            for comp in components:
                comp_type = classify_component(comp.reference, comp.value, comp.fields)
                comp_data_list.append(ComponentData(
                    reference=comp.reference,
                    value=comp.value,
                    component_type=comp_type,
                    fields=dict(comp.fields)
                ))
            
            dlg = BatchComponentEditorDialog(self, comp_data_list, sheet_path)
            if dlg.ShowModal() == wx.ID_OK:
                # Update fields back to parser components
                for cd in dlg.components:
                    for comp in components:
                        if comp.reference == cd.reference:
                            comp.fields.update(cd.fields)
                            break
                
                # Recalculate
                self._recalculate_sheet(sheet_path)
                self.status.SetLabel(f"Updated {len(components)} components in {sheet_path}")
            
            dlg.Destroy()
            
    def _on_calculate(self, event):
        sys_r, sys_lam = self._calculate_system()
        hours = self.settings_panel.get_hours()
        years = hours / (365 * 24)
        sys_fit = sys_lam * 1e9
        
        lines = [
            "═" * 45,
            "       SYSTEM RELIABILITY ANALYSIS",
            "═" * 45,
            "",
            f"  Mission Duration: {years:.1f} years ({hours:.0f} h)",
            "",
            f"  ► System Reliability:  R = {sys_r:.6f}",
            f"  ► Failure Rate:        λ = {sys_fit:.2f} FIT",
            f"                           = {sys_lam:.2e} /h",
        ]
        
        if sys_lam > 0:
            mttf = 1 / sys_lam
            lines.append(f"  ► MTTF:                {mttf:.2e} hours")
            lines.append(f"                         ({mttf/(365*24):.1f} years)")
        
        lines.extend([
            "",
            "═" * 45,
            "       BLOCK DETAILS",
            "═" * 45,
        ])
        
        for bid, b in sorted(self.editor.blocks.items()):
            if bid.startswith("__"):
                continue
            
            if b.is_group:
                lines.append(f"\n  [{b.label}] ({len(b.children)} blocks)")
                lines.append(f"    R = {b.reliability:.6f}")
            else:
                fit = b.lambda_val * 1e9
                lines.append(f"\n  {b.label}")
                lines.append(f"    λ = {fit:.2f} FIT, R = {b.reliability:.6f}")
        
        self.results.SetValue('\n'.join(lines))
        self.status.SetLabel(f"System R = {sys_r:.6f} ({years:.0f}y mission)")
    
    def _edit_single_component(self, sheet_path: str, ref: str):
        if not self.parser:
            return
        
        components = self.parser.get_sheet_components(sheet_path)
        comp = None
        for c in components:
            if c.reference == ref:
                comp = c
                break
        
        if not comp:
            return
        
        edited = self.component_edits.get(sheet_path, {}).get(ref, {})
        
        if edited:
            comp_type = edited.get("_component_type", "Resistor")
            fields = edited
        else:
            comp_type = classify_component(comp.reference, comp.value, {})
            fields = {}
        
        comp_data = ComponentData(
            reference=ref,
            value=comp.value,
            component_type=comp_type,
            fields=fields
        )
        
        dlg = ComponentEditorDialog(self, comp_data, self.settings_panel.get_hours())
        if dlg.ShowModal() == wx.ID_OK:
            result = dlg.get_result()
            if result:
                if sheet_path not in self.component_edits:
                    self.component_edits[sheet_path] = {}
                self.component_edits[sheet_path][ref] = result
                
                self._recalculate_all()
                
                data = self.sheet_data.get(sheet_path, {})
                self.comp_panel.set_data(
                    sheet_path,
                    data.get("components", []),
                    data.get("lambda", 0),
                    data.get("r", 1)
                )
        dlg.Destroy()
    
    def _edit_sheet_components(self, sheets: List[str]):
        if not self.parser:
            return
        
        all_components = []
        for sheet in sheets:
            components = self.parser.get_sheet_components(sheet)
            for c in components:
                edited = self.component_edits.get(sheet, {}).get(c.reference, {})
                
                if edited:
                    comp_type = edited.get("_component_type", "Resistor")
                    fields = edited
                else:
                    comp_type = classify_component(c.reference, c.value, {})
                    fields = {}
                
                all_components.append(ComponentData(
                    reference=c.reference,
                    value=c.value,
                    component_type=comp_type,
                    fields=fields
                ))
        
        if not all_components:
            wx.MessageBox("No components found.", "No Components", wx.OK | wx.ICON_INFORMATION)
            return
        
        dlg = BatchComponentEditorDialog(self, all_components, self.settings_panel.get_hours())
        if dlg.ShowModal() == wx.ID_OK:
            results = dlg.get_results()
            
            for sheet in sheets:
                components = self.parser.get_sheet_components(sheet)
                for c in components:
                    if c.reference in results:
                        if sheet not in self.component_edits:
                            self.component_edits[sheet] = {}
                        self.component_edits[sheet][c.reference] = results[c.reference]
            
            self._recalculate_all()
        dlg.Destroy()
    
    def _on_batch_edit(self, event):
        if not self.parser:
            wx.MessageBox("No project loaded.", "No Project", wx.OK | wx.ICON_INFORMATION)
            return
        sheets = self.parser.get_sheet_paths()
        self._edit_sheet_components(sheets)
    
    def _on_open(self, event):
        dlg = wx.DirDialog(self, "Select KiCad Project", 
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.editor.clear()
            self.sheet_data.clear()
            self.component_edits.clear()
            self._load_project(dlg.GetPath())
        dlg.Destroy()
    
    def _on_save(self, event):
        default_dir = self.project_path or os.getcwd()
        dlg = wx.FileDialog(self, "Save Configuration", defaultDir=default_dir,
                           defaultFile="reliability_config.json",
                           wildcard="JSON (*.json)|*.json",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            config = {
                "project": self.project_path,
                "structure": self.editor.get_structure(),
                "settings": {
                    "years": self.settings_panel.years.GetValue(),
                    "cycles": self.settings_panel.cycles.GetValue(),
                    "dt": self.settings_panel.dt.GetValue(),
                },
                "component_edits": self.component_edits,
            }
            with open(dlg.GetPath(), 'w') as f:
                json.dump(config, f, indent=2)
            self.status.SetLabel(f"Saved to {dlg.GetPath()}")
        dlg.Destroy()
    
    def _on_load_config(self, event):
        dlg = wx.FileDialog(self, "Load Configuration",
                           wildcard="JSON (*.json)|*.json",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                with open(dlg.GetPath(), 'r') as f:
                    config = json.load(f)
                
                settings = config.get("settings", {})
                self.settings_panel.years.SetValue(settings.get("years", 5))
                self.settings_panel.cycles.SetValue(settings.get("cycles", 5256))
                self.settings_panel.dt.SetValue(settings.get("dt", 3.0))
                self.component_edits = config.get("component_edits", {})
                self.editor.load_structure(config.get("structure", {}))
                self._recalculate_all()
                self.status.SetLabel(f"Loaded from {dlg.GetPath()}")
            except Exception as e:
                wx.MessageBox(f"Error: {e}", "Load Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()
    
    def _on_export(self, event):
        dlg = wx.FileDialog(self, "Export Report",
                           wildcard="HTML (*.html)|*.html|Markdown (*.md)|*.md|CSV (*.csv)|*.csv",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            idx = dlg.GetFilterIndex()
            
            sys_r, sys_lam = self._calculate_system()
            hours = self.settings_panel.get_hours()
            
            if idx == 0:
                content = self._generate_html(sys_r, sys_lam, hours)
            elif idx == 1:
                content = self._generate_md(sys_r, sys_lam, hours)
            else:
                content = self._generate_csv()
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.status.SetLabel(f"Exported to {path}")
        dlg.Destroy()
    
    def _generate_html(self, sys_r: float, sys_lam: float, hours: float) -> str:
        years = hours / (365*24)
        sys_fit = sys_lam * 1e9
        html = f'''<!DOCTYPE html>
<html><head><title>Reliability Report - IEC TR 62380</title>
<style>
body {{ font-family: Arial; margin: 20px; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; margin: 15px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; }}
th {{ background: #f5f5f5; }}
.summary {{ background: #e8f4e8; padding: 15px; border-radius: 5px; margin: 15px 0; }}
</style></head><body>
<h1>⚡ Reliability Analysis Report</h1>
<p><i>Based on IEC TR 62380</i></p>
<div class="summary">
<h2>System Summary</h2>
<p><b>Mission:</b> {years:.1f} years</p>
<p><b>Reliability:</b> R = {sys_r:.6f}</p>
<p><b>Failure Rate:</b> λ = {sys_fit:.2f} FIT</p>
</div>
<h2>Sheet Analysis</h2>
'''
        for path, data in sorted(self.sheet_data.items()):
            fit = data["lambda"] * 1e9
            html += f'''<h3>{path}</h3>
<p>R = {data["r"]:.6f}, λ = {fit:.2f} FIT</p>
<table><tr><th>Ref</th><th>Value</th><th>Type</th><th>λ (FIT)</th><th>R</th></tr>
'''
            for c in data["components"]:
                c_fit = c["lambda"] * 1e9
                html += f'<tr><td>{c["ref"]}</td><td>{c["value"]}</td><td>{c["class"]}</td>'
                html += f'<td>{c_fit:.2f}</td><td>{c["r"]:.4f}</td></tr>\n'
            html += '</table>\n'
        html += '</body></html>'
        return html
    
    def _generate_md(self, sys_r: float, sys_lam: float, hours: float) -> str:
        years = hours / (365*24)
        sys_fit = sys_lam * 1e9
        md = f'''# Reliability Analysis Report

*Based on IEC TR 62380*

## System Summary

- **Mission:** {years:.1f} years
- **Reliability:** R = {sys_r:.6f}
- **Failure Rate:** λ = {sys_fit:.2f} FIT

## Sheet Analysis

'''
        for path, data in sorted(self.sheet_data.items()):
            fit = data["lambda"] * 1e9
            md += f'''### {path}

R = {data["r"]:.6f}, λ = {fit:.2f} FIT

| Ref | Value | Type | λ (FIT) | R |
|-----|-------|------|---------|---|
'''
            for c in data["components"]:
                c_fit = c["lambda"] * 1e9
                md += f'| {c["ref"]} | {c["value"]} | {c["class"]} | {c_fit:.2f} | {c["r"]:.4f} |\n'
            md += '\n'
        return md
    
    def _generate_csv(self) -> str:
        lines = ["Sheet,Reference,Value,Type,Lambda_FIT,Reliability"]
        for path, data in sorted(self.sheet_data.items()):
            for c in data["components"]:
                c_fit = c["lambda"] * 1e9
                lines.append(f'"{path}","{c["ref"]}","{c["value"]}","{c["class"]}",{c_fit:.2f},{c["r"]:.6f}')
        return '\n'.join(lines)


if __name__ == "__main__":
    app = wx.App()
    dlg = ReliabilityMainDialog(None)
    dlg.ShowModal()
    dlg.Destroy()
