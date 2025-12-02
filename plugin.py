"""
KiCad Action Plugin for Reliability Calculation

This module provides the main plugin interface that integrates with KiCad's
Tools menu and toolbar.
"""

import os
import pcbnew
import wx

# Try to import eeschema API (available when running in eeschema context)
try:
    import eeschema
    HAS_EESCHEMA = True
except ImportError:
    HAS_EESCHEMA = False


class ReliabilityPlugin(pcbnew.ActionPlugin):
    """
    KiCad Action Plugin for calculating and displaying reliability data.
    
    This plugin:
    1. Reads component reliability parameters from symbol fields
    2. Provides a visual editor for defining sheet interconnections
    3. Calculates per-component, per-sheet, and system reliability
    4. Generates tables on schematic sheets with reliability data
    """
    
    def defaults(self):
        self.name = "Reliability Calculator"
        self.category = "Analysis"
        self.description = "Calculate and display system reliability based on component data"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")
    
    def Run(self):
        """Main entry point when plugin is activated."""
        # Import here to avoid issues during plugin registration
        from .reliability_dialog import ReliabilityMainDialog
        
        # Get the parent window
        parent = wx.GetTopLevelWindows()[0] if wx.GetTopLevelWindows() else None
        
        # Create and show the main dialog
        dlg = ReliabilityMainDialog(parent)
        dlg.ShowModal()
        dlg.Destroy()


# Alternative: Standalone launcher for testing outside KiCad
def run_standalone():
    """Run the reliability calculator as a standalone application for testing."""
    app = wx.App()
    
    from .reliability_dialog import ReliabilityMainDialog
    
    frame = wx.Frame(None, title="Reliability Calculator - Standalone Mode", size=(1200, 800))
    dlg = ReliabilityMainDialog(frame)
    frame.Show()
    dlg.ShowModal()
    
    app.MainLoop()


if __name__ == "__main__":
    run_standalone()
