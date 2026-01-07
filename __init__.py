# KiCad Reliability Calculator Plugin
# For KiCad 9.x
#
# This plugin provides:
# - Visual block diagram editor for defining system reliability topology
# - Automatic calculation of component and sheet reliability
# - Table generation on schematic sheets showing reliability data
#
# Installation:
#   Copy this folder to your KiCad plugins directory:
#   - Linux: ~/.local/share/kicad/9.0/scripting/plugins/
#   - Windows: %APPDATA%\kicad\9.0\scripting\plugins\
#   - macOS: ~/Library/Preferences/kicad/9.0/scripting/plugins/

try:
    from .plugin import ReliabilityPlugin
    ReliabilityPlugin().register()
except Exception as e:
    import logging
    logging.warning(f"Could not register ReliabilityPlugin: {e}")
