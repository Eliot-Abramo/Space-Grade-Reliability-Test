# KiCad Reliability Calculator Plugin

A comprehensive reliability analysis plugin for KiCad 9 that calculates component and system reliability based on FIDES methodology.

## Features

- **Visual Block Diagram Editor**: Drag-and-drop interface to define how schematic sheets are connected (series, parallel, k-of-n redundancy)
- **Automatic Schematic Parsing**: Reads KiCad 9 schematic hierarchy and component fields
- **Real-time Calculations**: Instant reliability updates as you modify the system structure
- **Component-level Analysis**: Detailed failure rates for resistors, capacitors, transistors, diodes, ICs, inductors, converters, and batteries
- **Table Injection**: Generate reliability tables directly in your schematic sheets
- **Report Export**: Export analysis to HTML, Markdown, or CSV

## Installation

### KiCad Plugin Installation

1. Copy the entire `kicad_reliability_plugin` folder to your KiCad plugins directory:
   - **Linux**: `~/.local/share/kicad/9.0/scripting/plugins/`
   - **Windows**: `%APPDATA%\kicad\9.0\scripting\plugins\`
   - **macOS**: `~/Library/Preferences/kicad/9.0/scripting/plugins/`

2. Restart KiCad

3. The plugin will appear in **Tools → External Plugins → Reliability Calculator**

### Standalone Usage (for testing)

```bash
cd kicad_reliability_plugin
python run_standalone.py [optional_project_path]
```

## Setting Up Your Schematic

For the plugin to calculate reliability, you need to add custom fields to your component symbols. The plugin looks for these fields:

### Required Field

| Field Name | Description | Example |
|------------|-------------|---------|
| `Reliability_Class` or `Class` | Component classification | `Resistor (11.1)` |

### Supported Component Classes

- `Resistor (11.1)`
- `Ceramic Capacitor (10.3)`
- `Tantalum Capacitor (10.4)`
- `Low Power Transistor (8.4)`
- `Power Transistor (8.5)`
- `Low Power Diode (8.2)`
- `Power Diode (8.3)`
- `Integrated Circuit (7)`
- `Inductor (12)`
- `Converter <10W (19.6)`
- `Primary Battery (19.1)`

### Optional Fields (for more accurate calculations)

| Field Name | Description | Default | Unit |
|------------|-------------|---------|------|
| `Temperature_Ambient` / `T_Ambient` | Ambient temperature | 25 | °C |
| `Temperature_Junction` / `T_Junction` | Junction temperature | 85 | °C |
| `Operating_Power` / `P_Operating` | Operating power | 0.01 | W |
| `Rated_Power` / `P_Rated` | Rated power | 0.125 | W |
| `Package` | Package type | (varies) | - |
| `Transistor_Type` | MOS or Bipolar | MOS | - |
| `Diode_Type` | signal, zener, etc. | signal | - |
| `IC_Type` | IC classification | (varies) | - |
| `Construction_Year` | Year of manufacture | 2020 | - |
| `Power_Loss` | Inductor power loss | 0.1 | W |
| `Surface_Area` | Radiating surface | 100 | mm² |

### Example Symbol Fields

For a resistor:
```
Reliability_Class: Resistor (11.1)
Temperature_Ambient: 25
Operating_Power: 0.005
Rated_Power: 0.1
```

For an IC:
```
Reliability_Class: Integrated Circuit (7)
Temperature_Junction: 85
IC_Type: MOS Standard, Digital circuits, 20000 transistors
Package: TQFP,10x10
Construction_Year: 2022
```

## Using the Plugin

### 1. Loading Your Project

Click **Load Project...** and select your KiCad project directory. The plugin will parse all schematic sheets and their hierarchy.

### 2. Adding Sheets to the Block Diagram

- Select sheets from the left panel
- Click **Add to Diagram** or double-click to add them to the visual editor
- Use **Add All** to add all sheets at once

### 3. Defining System Topology

The block diagram editor lets you define how subsystems are connected:

- **Drag blocks** to arrange them visually
- **Select multiple blocks** by dragging a rectangle around them
- **Right-click the selection** to group as:
  - **Series**: All blocks must work (reliability = R₁ × R₂ × ...)
  - **Parallel**: At least one must work (reliability = 1 - (1-R₁)(1-R₂)...)
  - **K-of-N**: K out of N must work (for redundancy)

- **Double-click a group** to change its type
- **Press Delete** to ungroup or remove blocks

### 4. Calculating Results

Click **Calculate System Reliability** to compute:
- Individual sheet reliability
- Group reliability (series/parallel/k-of-n)
- Overall system reliability
- Failure rates (λ)
- Mean Time To Failure (MTTF)

### 5. Configuring Parameters

Use the Settings panel to adjust:
- **Mission Time**: How long the system needs to operate (years)
- **Thermal Cycles/Year**: Number of temperature cycles per year
- **Temperature Swing (ΔT)**: Temperature variation during cycles (°C)

### 6. Exporting Results

**Inject Tables**: Adds reliability tables directly into your schematic files. After injection, reload the schematic in KiCad to see the tables.

**Export Report**: Generate a standalone report in:
- HTML (with styling)
- Markdown
- CSV (for spreadsheet analysis)

### 7. Saving/Loading Configurations

Use **Save Config** and **Load Config** to save and restore:
- Block diagram layout
- Group connections
- Settings

Configurations are saved as JSON files alongside your project.

## Reliability Calculations

The plugin implements reliability calculations based on FIDES methodology (similar to MIL-HDBK-217):

### Component Failure Rate (λ)

Each component type has a specific failure rate model considering:
- **Base failure rate** (component type dependent)
- **Temperature acceleration** (Arrhenius model)
- **Thermal cycling stress**
- **Electrical stress factors**
- **Package type**

### System Reliability

System reliability is calculated from the block diagram:

- **Series**: R_system = R₁ × R₂ × R₃ × ...
- **Parallel**: R_system = 1 - (1-R₁)(1-R₂)(1-R₃)...
- **K-of-N**: Binomial probability that at least K of N work

### Output Values

- **R** (Reliability): Probability of survival for mission time (0 to 1)
- **λ** (Lambda): Failure rate in failures per hour
- **MTTF**: Mean Time To Failure = 1/λ

## Troubleshooting

### "No components found"
- Check that your symbols have the `Reliability_Class` field
- Verify the field values match supported component classes

### Tables not appearing in schematic
- After injection, reload the schematic in KiCad (close and reopen)
- Check the schematic file for the text box (search for "Reliability Analysis")

### Parser errors
- Ensure you're using KiCad 9 format schematics
- Check that .kicad_sch files are not corrupted

## File Structure

```
kicad_reliability_plugin/
├── __init__.py           # Plugin registration
├── plugin.py             # KiCad action plugin interface
├── reliability_core.py   # Failure rate calculations
├── block_editor.py       # Visual block diagram editor
├── schematic_parser.py   # KiCad schematic parser
├── table_generator.py    # Table/report generation
├── reliability_dialog.py # Main UI dialog
├── run_standalone.py     # Standalone launcher
├── icon.png              # Toolbar icon
└── README.md             # This file
```

## Contributing

This plugin was developed for space system reliability analysis but can be adapted for other applications. Contributions welcome!

## License

MIT License - Feel free to use and modify for your projects.

## References

- FIDES Guide 2009 (Reliability Methodology)
- MIL-HDBK-217F (Reliability Prediction)
- ECSS-Q-ST-30-02C (Space Product Assurance)
