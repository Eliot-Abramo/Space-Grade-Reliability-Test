# KiCad Reliability Calculator Plugin

**IEC TR 62380 Reliability Prediction for Electronic Assemblies**

A professional-grade KiCad plugin for calculating system reliability based on the IEC TR 62380 standard (Reliability data handbook – Universal model for reliability prediction of electronics components, PCBs and equipment).

## Features

### 1. Integrated Component Field Editor
- **No ECSS Reference Required**: All component parameters accessible via dropdown menus with help text
- **Auto-Classification**: Automatically determines component type from reference designators (R*, C*, U*, Q*, D*, etc.)
- **Real-time Preview**: See calculated failure rates as you edit parameters
- **Batch Editing**: Edit all components at once or by schematic sheet

### 2. IEC TR 62380 Calculations
All formulas implemented per the standard:
- **Temperature Factors (πt)**: Arrhenius model with correct activation energies
- **Thermal Cycling Factors (πn)**: Based on annual cycle count
- **Package Factors**: Complete Table 17a/17b implementation
- **Interface/Overstress (λEOS)**: Environment-specific overstress rates

### 3. Centralized Math Module (`reliability_math.py`)
All calculations in one place for easy tuning:
- Modify failure rate constants
- Adjust activation energies
- Tune package stress factors
- Add new component types

### 4. System Block Diagram Editor
- Visual reliability block diagram
- Series/Parallel/K-of-N redundancy
- Drag-and-drop organization
- Automatic system reliability calculation

## Installation

1. Copy the plugin folder to your KiCad plugins directory:
   - Windows: `%APPDATA%\kicad\8.0\scripting\plugins\`
   - Linux: `~/.local/share/kicad/8.0/scripting/plugins/`
   - macOS: `~/Library/Application Support/kicad/8.0/scripting/plugins/`

2. Restart KiCad

3. Access via **Tools → Generate BOM** menu

## Usage

### Quick Start
1. Open your KiCad project
2. Launch the plugin from Tools → Generate BOM
3. Add schematic sheets to the block diagram
4. Double-click components to edit reliability fields
5. Click "Calculate System Reliability"

### Editing Component Fields
Each component type has specific fields:

**Integrated Circuits:**
- IC Type (Microcontroller, FPGA, Op-Amp, etc.)
- Transistor Count
- Package Type (SOIC, QFP, BGA, etc.)
- Junction Temperature
- Interface Type (for protection circuits)

**Transistors:**
- Technology (BJT, MOSFET, IGBT)
- Power Class (Low ≤5W, High >5W)
- Voltage Stress Ratios (VDS/VGS or VCE)
- Package Type

**Diodes:**
- Type (Signal, Zener, TVS, Schottky, LED)
- Power Class
- Package Type

**Capacitors:**
- Type (Ceramic Class I/II, Tantalum, Aluminum)
- Ambient Temperature
- Ripple Current Ratio (for electrolytics)

**Resistors:**
- Type (SMD, Film, Wirewound)
- Operating/Rated Power
- Ambient Temperature

### Mission Profile Settings
- **Mission Duration**: 1-30 years
- **Annual Thermal Cycles**: LEO satellite default is 5256/year
- **Temperature Swing (ΔT)**: Per-cycle temperature change

## File Structure

```
kicad_reliability_plugin/
├── bom_reliability.py       # KiCad BOM plugin entry point
├── reliability_launcher.py  # Project selector dialog
├── reliability_dialog.py    # Main UI with block editor
├── reliability_math.py      # ALL FORMULAS - edit here for tuning
├── component_editor.py      # Field editor with dropdowns
├── block_editor.py          # Visual block diagram editor
├── schematic_parser.py      # KiCad schematic reader
└── README.md
```

## Modifying Calculations

All reliability formulas are in `reliability_math.py`. Key sections:

### Adding New Component Types
```python
# In IC_DIE_TABLE, add new IC technologies:
IC_DIE_TABLE["MY_NEW_IC"] = {
    "l1": 1.0e-5,  # Per-transistor rate
    "l2": 15,      # Fixed rate
    "ea": ActivationEnergy.MOS
}

# In IC_TYPE_CHOICES, add user-friendly name:
IC_TYPE_CHOICES["My New IC Type"] = "MY_NEW_IC"
```

### Adjusting Failure Rates
```python
# Modify base rates in lookup tables:
DIODE_BASE_RATES["Signal (<1A)"]["l0"] = 0.05  # Lower base rate

CAPACITOR_PARAMS["Ceramic Class II (X7R/X5R)"]["l0"] = 0.12
```

### Changing Activation Energies
```python
class ActivationEnergy:
    MOS = 3480        # Adjust for different process nodes
    BIPOLAR = 4640
    # Add custom values as needed
```

## IEC TR 62380 Reference

### Key Formulas

**Temperature Factor:**
```
πt = exp(Ea × (1/Tref - 1/(273+Tj)))
```

**Thermal Cycling Factor:**
```
πn = n^0.76          for n ≤ 8760 cycles/year
πn = 1.7 × n^0.6     for n > 8760 cycles/year
```

**IC Failure Rate:**
```
λ = (λdie + λpackage + λEOS) × 10^-9 /h

λdie = (λ1 × N × exp(-0.35×a) + λ2) × πt
λpackage = 2.75×10^-3 × πα × πn × ΔT^0.68 × λ3
```

**System Reliability:**
```
R(t) = exp(-λ × t)
MTTF = 1/λ
```

### Standard Activation Energies
| Technology | Ea (eV) | Ea (K) |
|------------|---------|--------|
| MOS | 0.3 | 3480 |
| Bipolar | 0.4 | 4640 |
| Ceramic Cap | 0.1 | 1160 |
| Passives | 0.15 | 1740 |
| Aluminum Cap | 0.4 | 4640 |

## Export Formats

- **HTML**: Formatted report with tables
- **Markdown**: GitHub-compatible documentation
- **CSV**: Spreadsheet import for further analysis

## Configuration Files

Save/load configurations as JSON files containing:
- Block diagram structure
- Mission profile settings
- All edited component fields

## License

MIT License

## Author

Created for professional space electronics reliability analysis.
