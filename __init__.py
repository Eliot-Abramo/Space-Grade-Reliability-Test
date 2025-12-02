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

from .plugin import ReliabilityPlugin

# Register the plugin
ReliabilityPlugin().register()
