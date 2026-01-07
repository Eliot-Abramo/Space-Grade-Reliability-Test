"""
Component Editor Dialog

Provides a user-friendly interface for editing reliability fields on components.
Features dropdown menus, help text, and validation based on IEC TR 62380.
"""

import wx
import wx.lib.scrolledpanel as scrolled
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

from .reliability_math import (
    get_component_types, get_field_definitions, calculate_component_lambda,
    reliability_from_lambda, IC_TYPE_CHOICES, IC_PACKAGE_CHOICES,
    DIODE_BASE_RATES, TRANSISTOR_BASE_RATES, CAPACITOR_PARAMS,
    RESISTOR_PARAMS, INDUCTOR_PARAMS, DISCRETE_PACKAGE_TABLE,
    THERMAL_EXPANSION_SUBSTRATE, INTERFACE_EOS_VALUES, MISC_COMPONENT_RATES
)


@dataclass
class ComponentData:
    """Holds component data for editing."""
    reference: str
    value: str
    component_type: str
    fields: Dict[str, Any]


def classify_component(reference: str, value: str, existing_fields: Dict[str, str] = None) -> str:
    """Classify a component based on reference designator and value."""
    ref_upper = reference.upper()
    value_lower = value.lower() if value else ""
    
    if existing_fields and existing_fields.get("Reliability_Class"):
        rc = existing_fields["Reliability_Class"].lower()
        if "ic" in rc or "integrated" in rc:
            return "Integrated Circuit"
        if "diode" in rc:
            return "Diode"
        if "transistor" in rc or "mosfet" in rc:
            return "Transistor"
        if "capacitor" in rc:
            return "Capacitor"
        if "resistor" in rc:
            return "Resistor"
        if "inductor" in rc or "transformer" in rc:
            return "Inductor/Transformer"
    
    if ref_upper.startswith('R'):
        return "Resistor"
    elif ref_upper.startswith('C'):
        return "Capacitor"
    elif ref_upper.startswith('L'):
        return "Inductor/Transformer"
    elif ref_upper.startswith('D'):
        return "Diode"
    elif ref_upper.startswith('Q') or ref_upper.startswith('T'):
        return "Transistor"
    elif ref_upper.startswith('U') or ref_upper.startswith('IC'):
        return "Integrated Circuit"
    elif ref_upper.startswith('Y') or ref_upper.startswith('X'):
        return "Crystal/Oscillator"
    elif ref_upper.startswith('J') or ref_upper.startswith('P'):
        return "Connector"
    
    return "Miscellaneous"


class FieldEditorPanel(scrolled.ScrolledPanel):
    """Panel for editing component fields with appropriate controls."""
    
    def __init__(self, parent, component_type: str, initial_values: Dict[str, Any] = None,
                 on_change: Callable = None):
        super().__init__(parent, style=wx.VSCROLL | wx.HSCROLL)
        
        self.component_type = component_type
        self.field_controls = {}
        self.on_change = on_change
        
        self._create_ui(initial_values or {})
        self.SetupScrolling(scroll_x=False)
    
    def _create_ui(self, initial_values: Dict[str, Any]):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        fields = get_field_definitions(self.component_type)
        
        required_fields = {k: v for k, v in fields.items() if v.get("required", False)}
        optional_fields = {k: v for k, v in fields.items() if not v.get("required", False)}
        
        if required_fields:
            box = wx.StaticBox(self, label="Required Fields")
            box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
            for field_name, field_def in required_fields.items():
                ctrl = self._create_field_control(field_name, field_def, initial_values)
                box_sizer.Add(ctrl, 0, wx.EXPAND | wx.ALL, 3)
            main_sizer.Add(box_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        if optional_fields:
            box = wx.StaticBox(self, label="Optional Fields")
            box_sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
            for field_name, field_def in optional_fields.items():
                ctrl = self._create_field_control(field_name, field_def, initial_values)
                box_sizer.Add(ctrl, 0, wx.EXPAND | wx.ALL, 3)
            main_sizer.Add(box_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(main_sizer)
    
    def _create_field_control(self, field_name: str, field_def: Dict, 
                              initial_values: Dict[str, Any]) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        label_text = field_name.replace("_", " ").title()
        if field_def.get("required"):
            label_text += " *"
        label = wx.StaticText(self, label=label_text)
        label.SetFont(label.GetFont().Bold())
        sizer.Add(label, 0, wx.LEFT, 2)
        
        help_text = field_def.get("help", "")
        if help_text:
            help_label = wx.StaticText(self, label=help_text)
            help_label.SetForegroundColour(wx.Colour(100, 100, 100))
            sizer.Add(help_label, 0, wx.LEFT | wx.BOTTOM, 2)
        
        field_type = field_def.get("type", "text")
        default = field_def.get("default")
        initial = initial_values.get(field_name, default)
        
        if field_type == "choice":
            choices = field_def.get("choices", [])
            ctrl = wx.ComboBox(self, choices=choices, style=wx.CB_DROPDOWN)
            if initial and initial in choices:
                ctrl.SetValue(initial)
            elif choices:
                ctrl.SetValue(choices[0])
            ctrl.Bind(wx.EVT_COMBOBOX, self._on_field_change)
        elif field_type == "bool":
            ctrl = wx.CheckBox(self, label="Yes")
            ctrl.SetValue(bool(initial))
            ctrl.Bind(wx.EVT_CHECKBOX, self._on_field_change)
        elif field_type == "int":
            ctrl = wx.SpinCtrl(self, min=0, max=1000000000, initial=int(initial or 0))
            ctrl.Bind(wx.EVT_SPINCTRL, self._on_field_change)
        elif field_type == "float":
            ctrl = wx.TextCtrl(self, value=str(initial or ""))
            ctrl.Bind(wx.EVT_TEXT, self._on_field_change)
        else:
            ctrl = wx.TextCtrl(self, value=str(initial or ""))
            ctrl.Bind(wx.EVT_TEXT, self._on_field_change)
        
        sizer.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 2)
        self.field_controls[field_name] = (ctrl, field_type, field_def)
        return sizer
    
    def _on_field_change(self, event):
        if self.on_change:
            self.on_change()
        event.Skip()
    
    def get_values(self) -> Dict[str, Any]:
        values = {}
        for field_name, (ctrl, field_type, field_def) in self.field_controls.items():
            try:
                if field_type == "choice":
                    values[field_name] = ctrl.GetValue()
                elif field_type == "bool":
                    values[field_name] = ctrl.GetValue()
                elif field_type == "int":
                    values[field_name] = ctrl.GetValue()
                elif field_type == "float":
                    text = ctrl.GetValue().strip()
                    values[field_name] = float(text) if text else field_def.get("default", 0.0)
                else:
                    values[field_name] = ctrl.GetValue()
            except (ValueError, TypeError):
                values[field_name] = field_def.get("default")
        return values
    
    def set_component_type(self, component_type: str, initial_values: Dict[str, Any] = None):
        self.component_type = component_type
        self.field_controls.clear()
        self.DestroyChildren()
        self._create_ui(initial_values or {})
        self.SetupScrolling(scroll_x=False)
        self.Layout()


class ComponentEditorDialog(wx.Dialog):
    """Dialog for editing reliability fields on a single component."""
    
    def __init__(self, parent, component: ComponentData, mission_hours: float = 43800):
        super().__init__(parent, title=f"Edit Component: {component.reference}",
                        size=(550, 700), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.component = component
        self.mission_hours = mission_hours
        self.result_fields = None
        
        self._create_ui()
        self._update_preview()
        self.Centre()
    
    def _create_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ref_label = wx.StaticText(panel, label=f"Reference: {self.component.reference}")
        ref_label.SetFont(ref_label.GetFont().Bold())
        header_sizer.Add(ref_label, 0, wx.ALL, 5)
        val_label = wx.StaticText(panel, label=f"Value: {self.component.value}")
        header_sizer.Add(val_label, 0, wx.ALL, 5)
        main_sizer.Add(header_sizer, 0, wx.EXPAND)
        
        type_sizer = wx.BoxSizer(wx.HORIZONTAL)
        type_sizer.Add(wx.StaticText(panel, label="Component Type:"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.type_combo = wx.ComboBox(panel, choices=get_component_types(), 
                                       style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.type_combo.SetValue(self.component.component_type)
        self.type_combo.Bind(wx.EVT_COMBOBOX, self._on_type_change)
        type_sizer.Add(self.type_combo, 1, wx.ALL | wx.EXPAND, 5)
        main_sizer.Add(type_sizer, 0, wx.EXPAND)
        
        main_sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 5)
        
        self.field_panel = FieldEditorPanel(panel, self.component.component_type, 
                                            self.component.fields, on_change=self._update_preview)
        main_sizer.Add(self.field_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        preview_box = wx.StaticBox(panel, label="Calculated Reliability Preview")
        preview_sizer = wx.StaticBoxSizer(preview_box, wx.VERTICAL)
        self.preview_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 80))
        self.preview_text.SetBackgroundColour(wx.Colour(240, 240, 240))
        preview_sizer.Add(self.preview_text, 1, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(preview_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Apply")
        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)
        btn_sizer.AddButton(ok_btn)
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Cancel")
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(main_sizer)
    
    def _on_type_change(self, event):
        new_type = self.type_combo.GetValue()
        self.field_panel.set_component_type(new_type, {})
        self._update_preview()
    
    def _update_preview(self):
        try:
            component_type = self.type_combo.GetValue()
            params = self.field_panel.get_values()
            result = calculate_component_lambda(component_type, params)
            lambda_total = result.get("lambda_total", 0)
            fit_total = result.get("fit_total", lambda_total * 1e9)
            
            r = reliability_from_lambda(lambda_total, self.mission_hours)
            mttf_hours = 1 / lambda_total if lambda_total > 0 else float('inf')
            mttf_years = mttf_hours / 8760
            
            preview = f"λ (failure rate): {fit_total:.2f} FIT ({lambda_total:.2e} /h)\n"
            preview += f"R({self.mission_hours/8760:.1f} years): {r:.6f} ({r*100:.4f}%)\n"
            preview += f"MTTF: {mttf_years:.1f} years ({mttf_hours:.0f} hours)"
            self.preview_text.SetValue(preview)
        except Exception as e:
            self.preview_text.SetValue(f"Error: {str(e)}")
    
    def _on_ok(self, event):
        self.result_fields = self.field_panel.get_values()
        self.result_fields["_component_type"] = self.type_combo.GetValue()
        self.EndModal(wx.ID_OK)
    
    def get_result(self) -> Optional[Dict[str, Any]]:
        return self.result_fields


class BatchComponentEditorDialog(wx.Dialog):
    """Dialog for editing reliability fields on multiple components."""
    
    def __init__(self, parent, components: List[ComponentData], mission_hours: float = 43800):
        super().__init__(parent, title="Batch Component Editor",
                        size=(900, 700), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.components = components
        self.mission_hours = mission_hours
        self.results = {}
        
        self._create_ui()
        self.Centre()
    
    def _create_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        left_panel = wx.Panel(panel)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        left_sizer.Add(wx.StaticText(left_panel, label="Components:"), 0, wx.ALL, 5)
        
        self.comp_list = wx.ListCtrl(left_panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.comp_list.InsertColumn(0, "Ref", width=60)
        self.comp_list.InsertColumn(1, "Value", width=100)
        self.comp_list.InsertColumn(2, "Type", width=120)
        self.comp_list.InsertColumn(3, "λ (FIT)", width=80)
        
        for i, comp in enumerate(self.components):
            self.comp_list.InsertItem(i, comp.reference)
            self.comp_list.SetItem(i, 1, comp.value or "")
            self.comp_list.SetItem(i, 2, comp.component_type)
            try:
                result = calculate_component_lambda(comp.component_type, comp.fields)
                fit = result.get("fit_total", 0)
                self.comp_list.SetItem(i, 3, f"{fit:.2f}")
            except:
                self.comp_list.SetItem(i, 3, "?")
        
        self.comp_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)
        self.comp_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit)
        left_sizer.Add(self.comp_list, 1, wx.EXPAND | wx.ALL, 5)
        
        btn_panel = wx.Panel(left_panel)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        edit_btn = wx.Button(btn_panel, label="Edit Selected")
        edit_btn.Bind(wx.EVT_BUTTON, self._on_edit)
        btn_sizer.Add(edit_btn, 0, wx.ALL, 3)
        auto_btn = wx.Button(btn_panel, label="Auto-Classify All")
        auto_btn.Bind(wx.EVT_BUTTON, self._on_auto_classify)
        btn_sizer.Add(auto_btn, 0, wx.ALL, 3)
        btn_panel.SetSizer(btn_sizer)
        left_sizer.Add(btn_panel, 0, wx.EXPAND)
        
        left_panel.SetSizer(left_sizer)
        main_sizer.Add(left_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        right_panel = wx.Panel(panel)
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_sizer.Add(wx.StaticText(right_panel, label="Quick Edit:"), 0, wx.ALL, 5)
        
        type_sizer = wx.BoxSizer(wx.HORIZONTAL)
        type_sizer.Add(wx.StaticText(right_panel, label="Type:"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 3)
        self.type_combo = wx.ComboBox(right_panel, choices=get_component_types(),
                                       style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.type_combo.Bind(wx.EVT_COMBOBOX, self._on_quick_type_change)
        type_sizer.Add(self.type_combo, 1, wx.ALL, 3)
        right_sizer.Add(type_sizer, 0, wx.EXPAND)
        
        self.field_panel = FieldEditorPanel(right_panel, "Resistor", {}, None)
        right_sizer.Add(self.field_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        apply_btn = wx.Button(right_panel, label="Apply to Selected")
        apply_btn.Bind(wx.EVT_BUTTON, self._on_apply_quick)
        right_sizer.Add(apply_btn, 0, wx.EXPAND | wx.ALL, 5)
        
        right_panel.SetSizer(right_sizer)
        main_sizer.Add(right_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(main_sizer)
        
        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(panel, 1, wx.EXPAND)
        
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(self, wx.ID_OK, "Save All")
        ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)
        btn_sizer.AddButton(ok_btn)
        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        dialog_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(dialog_sizer)
        
        if self.components:
            self.comp_list.Select(0)
            self._load_component(0)
    
    def _on_select(self, event):
        self._load_component(event.GetIndex())
    
    def _load_component(self, idx: int):
        if 0 <= idx < len(self.components):
            comp = self.components[idx]
            fields = self.results.get(comp.reference, comp.fields)
            comp_type = fields.get("_component_type", comp.component_type)
            self.type_combo.SetValue(comp_type)
            self.field_panel.set_component_type(comp_type, fields)
    
    def _on_quick_type_change(self, event):
        new_type = self.type_combo.GetValue()
        self.field_panel.set_component_type(new_type, {})
    
    def _on_apply_quick(self, event):
        idx = self.comp_list.GetFirstSelected()
        if idx < 0:
            return
        
        comp = self.components[idx]
        fields = self.field_panel.get_values()
        fields["_component_type"] = self.type_combo.GetValue()
        
        self.results[comp.reference] = fields
        comp.component_type = self.type_combo.GetValue()
        comp.fields = fields
        
        self.comp_list.SetItem(idx, 2, comp.component_type)
        try:
            result = calculate_component_lambda(comp.component_type, fields)
            fit = result.get("fit_total", 0)
            self.comp_list.SetItem(idx, 3, f"{fit:.2f}")
        except:
            self.comp_list.SetItem(idx, 3, "?")
    
    def _on_edit(self, event):
        idx = self.comp_list.GetFirstSelected()
        if idx < 0:
            wx.MessageBox("Please select a component first.", "No Selection", wx.OK | wx.ICON_INFORMATION)
            return
        
        comp = self.components[idx]
        fields = self.results.get(comp.reference, comp.fields)
        comp_type = fields.get("_component_type", comp.component_type)
        
        edit_comp = ComponentData(reference=comp.reference, value=comp.value,
                                  component_type=comp_type, fields=fields)
        
        dlg = ComponentEditorDialog(self, edit_comp, self.mission_hours)
        if dlg.ShowModal() == wx.ID_OK:
            result = dlg.get_result()
            if result:
                self.results[comp.reference] = result
                comp.component_type = result.get("_component_type", comp.component_type)
                comp.fields = result
                
                self.comp_list.SetItem(idx, 2, comp.component_type)
                try:
                    calc_result = calculate_component_lambda(comp.component_type, result)
                    fit = calc_result.get("fit_total", 0)
                    self.comp_list.SetItem(idx, 3, f"{fit:.2f}")
                except:
                    self.comp_list.SetItem(idx, 3, "?")
                
                self._load_component(idx)
        dlg.Destroy()
    
    def _on_auto_classify(self, event):
        for i, comp in enumerate(self.components):
            if comp.reference not in self.results:
                new_type = classify_component(comp.reference, comp.value, comp.fields)
                comp.component_type = new_type
                self.comp_list.SetItem(i, 2, new_type)
                try:
                    result = calculate_component_lambda(new_type, comp.fields)
                    fit = result.get("fit_total", 0)
                    self.comp_list.SetItem(i, 3, f"{fit:.2f}")
                except:
                    self.comp_list.SetItem(i, 3, "?")
    
    def _on_ok(self, event):
        for comp in self.components:
            if comp.reference not in self.results:
                fields = comp.fields.copy()
                fields["_component_type"] = comp.component_type
                self.results[comp.reference] = fields
        self.EndModal(wx.ID_OK)
    
    def get_results(self) -> Dict[str, Dict[str, Any]]:
        return self.results


class QuickReferenceDialog(wx.Dialog):
    """Quick reference dialog showing IEC TR 62380 information."""
    
    def __init__(self, parent):
        super().__init__(parent, title="IEC TR 62380 Quick Reference",
                        size=(700, 600), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        notebook = wx.Notebook(self)
        
        overview = wx.TextCtrl(notebook, style=wx.TE_MULTILINE | wx.TE_READONLY)
        overview.SetValue("""IEC TR 62380 - Reliability Data Handbook
=========================================

Key Concepts:
- λ (Lambda): Failure rate in FIT (Failures In Time = failures per 10^9 hours)
- R(t): Reliability = probability of survival = exp(-λ × t)
- MTTF: Mean Time To Failure = 1/λ

General Model:
λ_component = (λ_die + λ_package + λ_overstress) × 10^-9 /h

Temperature Factor (Arrhenius):
π_t = exp(Ea × (1/T_ref - 1/(273+T_j)))

Activation Energies:
- MOS: Ea = 0.3 eV (3480 K)
- Bipolar: Ea = 0.4 eV (4640 K)
- Passives: Ea = 0.15 eV (1740 K)

Thermal Cycling Factor:
π_n = n^0.76 for n ≤ 8760 cycles/year
π_n = 1.7 × n^0.6 for n > 8760 cycles/year
""")
        notebook.AddPage(overview, "Overview")
        
        ic_info = wx.TextCtrl(notebook, style=wx.TE_MULTILINE | wx.TE_READONLY)
        ic_info.SetValue("""Integrated Circuits (Section 7)
================================

Die Contribution:
λ_die = (λ1 × N × exp(-0.35×a) + λ2) × π_t
- λ1: Per-transistor base rate
- N: Number of transistors
- a: Years since 1998

Package Contribution:
λ_package = 2.75×10^-3 × π_α × π_n × ΔT^0.68 × λ3

π_α = 0.06 × |α_substrate - α_package|^1.68

Typical α values (ppm/°C):
- FR4: 16
- Epoxy package: 21.5
- Ceramic: 6.5
""")
        notebook.AddPage(ic_info, "ICs")
        
        passive_info = wx.TextCtrl(notebook, style=wx.TE_MULTILINE | wx.TE_READONLY)
        passive_info.SetValue("""Capacitors & Resistors
======================

Capacitor Base Rates λ0 (FIT):
- Ceramic Class I (C0G): 0.05
- Ceramic Class II (X7R): 0.15
- Tantalum: 0.4
- Aluminum Electrolytic: 1.3

Resistor Base Rates λ0 (FIT):
- SMD Chip: 0.01 per resistor
- Film (low power): 0.1
- Wirewound: 0.3-0.4

Resistor Temperature:
T_R = T_ambient + K × (P_op/P_rated)
K = 85°C for film, 55°C for SMD
""")
        notebook.AddPage(passive_info, "Passives")
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)
        
        close_btn = wx.Button(self, wx.ID_CLOSE, "Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        sizer.Add(close_btn, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Centre()


def generate_kicad_fields(component_type: str, params: Dict[str, Any]) -> Dict[str, str]:
    """Generate KiCad-compatible field strings from parameters."""
    fields = {"Reliability_Class": component_type}
    for key, value in params.items():
        if key.startswith("_") or value is None:
            continue
        if isinstance(value, bool):
            fields[key] = "Yes" if value else "No"
        elif isinstance(value, float):
            fields[key] = f"{value:.6g}" if value != int(value) else str(int(value))
        else:
            fields[key] = str(value)
    return fields


def parse_kicad_fields(fields: Dict[str, str], component_type: str = None) -> Dict[str, Any]:
    """Parse KiCad field strings into typed parameter values."""
    params = {}
    field_defs = get_field_definitions(component_type) if component_type else {}
    
    for key, value in fields.items():
        if not value:
            continue
        field_def = field_defs.get(key, {})
        field_type = field_def.get("type", "text")
        try:
            if field_type == "bool":
                params[key] = value.lower() in ("yes", "true", "1")
            elif field_type == "int":
                params[key] = int(float(value))
            elif field_type == "float":
                params[key] = float(value)
            else:
                params[key] = value
        except (ValueError, TypeError):
            params[key] = value
    return params
