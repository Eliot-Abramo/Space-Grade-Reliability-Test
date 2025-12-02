#!/usr/bin/env python3
"""
Standalone launcher for the Reliability Calculator.

This script allows you to run and test the reliability calculator
outside of KiCad. It's useful for development and testing.

Usage:
    python run_standalone.py [project_path]

If project_path is provided, it will try to load the KiCad project
from that directory.
"""

import sys
import os

# Add the plugin directory to path
plugin_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(plugin_dir))

import wx

def main():
    # Import after wx is available
    from kicad_reliability_plugin.reliability_dialog import ReliabilityMainDialog
    
    app = wx.App()
    
    # Set up a proper application name
    app.SetAppName("Reliability Calculator")
    
    # Create and show the main dialog
    dlg = ReliabilityMainDialog(None)
    
    # If a project path was provided, try to load it
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
        if os.path.exists(project_path):
            dlg.project_path = project_path
            dlg.txt_project.SetValue(project_path)
            
            from kicad_reliability_plugin.schematic_parser import KiCadSchematicParser
            dlg.parser = KiCadSchematicParser(project_path)
            if dlg.parser.parse():
                sheets = dlg.parser.get_sheet_paths()
                dlg.sheet_panel.set_sheets(sheets)
                dlg._calculate_all_sheets()
    
    dlg.ShowModal()
    dlg.Destroy()


if __name__ == "__main__":
    main()
