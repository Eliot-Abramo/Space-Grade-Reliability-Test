"""
KiCad Action Plugin for Reliability Calculation

This module provides the main plugin interface that integrates with KiCad's
Tools menu and toolbar.
"""

import os
import pcbnew
import wx
from pathlib import Path


def get_kicad_project_path():
    """Try to get the current project path from KiCad."""
    try:
        board = pcbnew.GetBoard()
        if board:
            board_file = board.GetFileName()
            if board_file:
                board_path = Path(board_file)
                # Look for .kicad_pro file
                pro_file = board_path.with_suffix('.kicad_pro')
                if pro_file.exists():
                    return str(pro_file.parent)
                # Or just return the board directory
                return str(board_path.parent)
    except Exception:
        pass
    return None


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
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            self.icon_file_name = icon_path
    
    def Run(self):
        """Main entry point when plugin is activated."""
        # Get the parent window
        parent = None
        try:
            top_windows = wx.GetTopLevelWindows()
            if top_windows:
                parent = top_windows[0]
        except Exception:
            pass
        
        # Try to get project path from KiCad
        project_path = get_kicad_project_path()
        
        # Import dialog here to avoid issues during plugin registration
        try:
            from .reliability_dialog import ReliabilityMainDialog
            dlg = ReliabilityMainDialog(parent, project_path)
            dlg.ShowModal()
            dlg.Destroy()
        except Exception as e:
            wx.MessageBox(
                f"Error launching Reliability Calculator:\n\n{str(e)}\n\n"
                "Check the KiCad scripting console for details.",
                "Plugin Error",
                wx.OK | wx.ICON_ERROR
            )
            import traceback
            traceback.print_exc()


# Alternative: Standalone launcher for testing outside KiCad
def run_standalone(project_path=None):
    """Run the reliability calculator as a standalone application for testing."""
    app = wx.App()
    
    from .reliability_dialog import ReliabilityMainDialog
    
    dlg = ReliabilityMainDialog(None, project_path)
    dlg.ShowModal()
    dlg.Destroy()
    
    app.MainLoop()


if __name__ == "__main__":
    run_standalone()
