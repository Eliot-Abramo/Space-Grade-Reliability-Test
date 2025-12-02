"""
KiCad Schematic Parser

This module reads KiCad 9 schematic files (.kicad_sch) and extracts:
- Hierarchical sheet structure
- Component symbols and their custom fields for reliability parameters
- Sheet instances and their paths
"""

import os
import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path


@dataclass
class ComponentField:
    """Represents a custom field on a component symbol."""
    name: str
    value: str


@dataclass
class Component:
    """Represents a component in the schematic."""
    reference: str
    value: str
    lib_id: str
    sheet_path: str
    fields: Dict[str, str] = field(default_factory=dict)
    
    def get_field(self, name: str, default: Any = None) -> Any:
        """Get a field value, with optional default."""
        # Normalize field name (case-insensitive, underscore/space flexible)
        name_lower = name.lower().replace(" ", "_")
        for key, val in self.fields.items():
            if key.lower().replace(" ", "_") == name_lower:
                return val
        return default
    
    def get_float_field(self, name: str, default: float = 0.0) -> float:
        """Get a field value as float."""
        val = self.get_field(name)
        if val is None:
            return default
        try:
            # Handle scientific notation and common suffixes
            val = str(val).strip().upper()
            multipliers = {'K': 1e3, 'M': 1e6, 'G': 1e9, 'U': 1e-6, 'N': 1e-9, 'P': 1e-12}
            for suffix, mult in multipliers.items():
                if val.endswith(suffix):
                    return float(val[:-1]) * mult
            return float(val)
        except ValueError:
            return default
    
    def get_int_field(self, name: str, default: int = 0) -> int:
        """Get a field value as integer."""
        val = self.get_field(name)
        if val is None:
            return default
        try:
            return int(float(val))
        except ValueError:
            return default


@dataclass  
class Sheet:
    """Represents a hierarchical sheet in the schematic."""
    name: str
    path: str  # Full hierarchical path like "/Power/Deploy/Buck/"
    filename: str  # The .kicad_sch file
    components: List[Component] = field(default_factory=list)
    child_sheets: List[str] = field(default_factory=list)  # Paths to child sheets


class KiCadSchematicParser:
    """
    Parser for KiCad 9 schematic files.
    
    KiCad 9 uses S-expression format for schematic files.
    This parser extracts hierarchy and component data without requiring
    the full KiCad libraries.
    """
    
    # Field names we look for (case-insensitive)
    RELIABILITY_FIELDS = [
        "Reliability_Class", "Class",
        "Temperature_Junction", "T_Junction", "Tj",
        "Temperature_Ambient", "T_Ambient", "Ta",
        "Rated_Power", "P_Rated",
        "Operating_Power", "P_Operating",
        "Package", "Footprint_Type",
        "Transistor_Type", "Diode_Type", "IC_Type", "Inductor_Type",
        "Construction_Year", "Construction_Date",
        "V_CE_Applied", "V_CE_Specified",
        "V_DS_Applied", "V_DS_Specified", 
        "V_GS_Applied", "V_GS_Specified",
        "Power_Loss", "Surface_Area", "Radiating_Surface",
        "N_Cycles", "Delta_T",
    ]
    
    def __init__(self, project_path: str):
        """
        Initialize parser with project path.
        
        Args:
            project_path: Path to .kicad_pro file or directory containing it
        """
        self.project_path = Path(project_path)
        
        if self.project_path.is_file():
            self.project_dir = self.project_path.parent
            self.project_name = self.project_path.stem
        else:
            self.project_dir = self.project_path
            # Find .kicad_pro file
            pro_files = list(self.project_dir.glob("*.kicad_pro"))
            if pro_files:
                self.project_name = pro_files[0].stem
            else:
                self.project_name = self.project_dir.name
        
        self.sheets: Dict[str, Sheet] = {}
        self.components: List[Component] = []
        self.root_sheet_path = "/"
    
    def parse(self) -> bool:
        """
        Parse the schematic hierarchy.
        
        Returns:
            True if parsing was successful
        """
        # Find root schematic
        root_sch = self.project_dir / f"{self.project_name}.kicad_sch"
        
        if not root_sch.exists():
            # Try to find any .kicad_sch file
            sch_files = list(self.project_dir.glob("*.kicad_sch"))
            if sch_files:
                root_sch = sch_files[0]
            else:
                return False
        
        # Parse recursively
        self._parse_sheet(root_sch, "/")
        return True
    
    def _parse_sheet(self, sch_path: Path, hierarchy_path: str):
        """Parse a single schematic sheet and its children."""
        if not sch_path.exists():
            return
        
        try:
            content = sch_path.read_text(encoding='utf-8')
        except Exception:
            return
        
        # Create sheet record
        sheet_name = sch_path.stem
        if hierarchy_path == "/":
            display_path = "/" + sheet_name + "/"
        else:
            display_path = hierarchy_path
        
        sheet = Sheet(
            name=sheet_name,
            path=display_path,
            filename=str(sch_path),
        )
        
        # Parse components (symbols)
        sheet.components = self._parse_components(content, display_path)
        self.components.extend(sheet.components)
        
        # Parse child sheets
        child_sheets = self._parse_child_sheets(content, sch_path.parent)
        for child_name, child_file in child_sheets:
            child_path = display_path.rstrip('/') + "/" + child_name + "/"
            sheet.child_sheets.append(child_path)
            
            # Recursively parse child
            child_sch = sch_path.parent / child_file
            self._parse_sheet(child_sch, child_path)
        
        self.sheets[display_path] = sheet
    
    def _parse_components(self, content: str, sheet_path: str) -> List[Component]:
        """Extract components from schematic content."""
        components = []
        
        # Find all symbol blocks
        # KiCad 9 format: (symbol (lib_id "...") ... (property "Reference" "R1") ...)
        symbol_pattern = r'\(symbol\s+\(lib_id\s+"([^"]+)"\)'
        
        # Simple state machine to parse S-expressions
        pos = 0
        while True:
            match = re.search(symbol_pattern, content[pos:])
            if not match:
                break
            
            start = pos + match.start()
            lib_id = match.group(1)
            
            # Find the matching closing paren
            symbol_content = self._extract_sexp(content, start)
            if not symbol_content:
                pos = start + 1
                continue
            
            # Extract properties
            props = self._extract_properties(symbol_content)
            
            reference = props.get("Reference", "?")
            value = props.get("Value", "")
            
            # Skip power symbols and other special components
            if reference.startswith("#") or lib_id.startswith("power:"):
                pos = start + len(symbol_content)
                continue
            
            # Build component
            comp = Component(
                reference=reference,
                value=value,
                lib_id=lib_id,
                sheet_path=sheet_path,
                fields={k: v for k, v in props.items() 
                        if k not in ("Reference", "Value", "Footprint", "Datasheet")}
            )
            components.append(comp)
            
            pos = start + len(symbol_content)
        
        return components
    
    def _parse_child_sheets(self, content: str, base_dir: Path) -> List[Tuple[str, str]]:
        """Extract child sheet references."""
        children = []
        
        # KiCad 9 format: (sheet ... (property "Sheetname" "name") ... (property "Sheetfile" "file.kicad_sch"))
        sheet_pattern = r'\(sheet\s+'
        
        pos = 0
        while True:
            match = re.search(sheet_pattern, content[pos:])
            if not match:
                break
            
            start = pos + match.start()
            sheet_content = self._extract_sexp(content, start)
            if not sheet_content:
                pos = start + 1
                continue
            
            props = self._extract_properties(sheet_content)
            
            sheet_name = props.get("Sheetname", props.get("Sheet name", ""))
            sheet_file = props.get("Sheetfile", props.get("Sheet file", ""))
            
            if sheet_name and sheet_file:
                children.append((sheet_name, sheet_file))
            
            pos = start + len(sheet_content)
        
        return children
    
    def _extract_sexp(self, content: str, start: int) -> Optional[str]:
        """Extract a complete S-expression starting at position."""
        if content[start] != '(':
            return None
        
        depth = 0
        i = start
        in_string = False
        escape_next = False
        
        while i < len(content):
            c = content[i]
            
            if escape_next:
                escape_next = False
                i += 1
                continue
            
            if c == '\\':
                escape_next = True
                i += 1
                continue
            
            if c == '"':
                in_string = not in_string
            elif not in_string:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        return content[start:i+1]
            
            i += 1
        
        return None
    
    def _extract_properties(self, sexp: str) -> Dict[str, str]:
        """Extract property name-value pairs from an S-expression."""
        props = {}
        
        # Match (property "name" "value" ...) patterns
        prop_pattern = r'\(property\s+"([^"]+)"\s+"([^"]*)"'
        
        for match in re.finditer(prop_pattern, sexp):
            name = match.group(1)
            value = match.group(2)
            props[name] = value
        
        return props
    
    def get_sheet_paths(self) -> List[str]:
        """Get list of all sheet paths."""
        return list(self.sheets.keys())
    
    def get_sheet_components(self, sheet_path: str) -> List[Component]:
        """Get components for a specific sheet."""
        sheet = self.sheets.get(sheet_path)
        return sheet.components if sheet else []
    
    def get_all_components(self) -> List[Component]:
        """Get all components across all sheets."""
        return self.components
    
    def get_hierarchy(self) -> Dict[str, List[str]]:
        """Get sheet hierarchy as dict of parent -> children."""
        hierarchy = {}
        for path, sheet in self.sheets.items():
            hierarchy[path] = sheet.child_sheets
        return hierarchy


# =============================================================================
# Mock data for testing without actual KiCad files
# =============================================================================

def create_mock_parser(sheet_names: List[str]) -> KiCadSchematicParser:
    """
    Create a mock parser with predefined sheets for testing.
    
    Args:
        sheet_names: List of sheet paths to create
    """
    parser = KiCadSchematicParser("/mock/project")
    
    for path in sheet_names:
        name = path.rstrip('/').split('/')[-1] or "Root"
        sheet = Sheet(
            name=name,
            path=path,
            filename=f"/mock/{name}.kicad_sch",
        )
        
        # Add some mock components
        if "Power" in path:
            sheet.components = [
                Component("R1", "10k", "Device:R", path, {"Reliability_Class": "Resistor (11.1)", "Temperature_Ambient": "25", "Operating_Power": "0.01", "Rated_Power": "0.125"}),
                Component("C1", "100n", "Device:C", path, {"Reliability_Class": "Ceramic Capacitor (10.3)", "Temperature_Ambient": "25"}),
            ]
        elif "MCU" in path:
            sheet.components = [
                Component("U1", "STM32", "MCU:STM32", path, {"Reliability_Class": "Integrated Circuit (7)", "Temperature_Junction": "85", "IC_Type": "MOS Standard, Digital circuits, 20000 transistors"}),
            ]
        else:
            sheet.components = [
                Component("R1", "1k", "Device:R", path, {"Reliability_Class": "Resistor (11.1)"}),
            ]
        
        parser.sheets[path] = sheet
        parser.components.extend(sheet.components)
    
    return parser


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    # Test with mock data
    sheets = [
        "/Project Architecture/",
        "/Project Architecture/Power/",
        "/Project Architecture/Power/Protection Satellite 24V/",
        "/Project Architecture/Power/Battery Charger/",
        "/Project Architecture/Power/LDO_3v3_sat/",
        "/Project Architecture/Power/Deploy/",
        "/Project Architecture/Power/Deploy/Buck/",
        "/Project Architecture/Control/MCU_A/",
    ]
    
    parser = create_mock_parser(sheets)
    
    print("Sheets found:")
    for path in parser.get_sheet_paths():
        print(f"  {path}")
        for comp in parser.get_sheet_components(path):
            print(f"    - {comp.reference}: {comp.value} ({comp.get_field('Reliability_Class', 'N/A')})")
