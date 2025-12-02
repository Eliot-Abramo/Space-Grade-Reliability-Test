"""
KiCad Table Generator

This module generates and updates table objects in KiCad 9 schematics
to display reliability data.

KiCad 9 supports table objects in schematics with the following S-expression format:
(table (at X Y) (columns N) (column_width W1 W2 ...) 
  (effects (font (size H W)))
  (cells 
    (cell "text")
    ...
  )
)
"""

import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path


@dataclass
class TableCell:
    """Represents a cell in a reliability table."""
    text: str
    bold: bool = False
    

@dataclass
class ReliabilityTable:
    """Represents a reliability data table for a sheet."""
    sheet_path: str
    x: float = 200.0  # Position in mm
    y: float = 20.0
    
    # Header row
    headers: List[str] = None
    
    # Data rows: list of [reference, class, lambda, R]
    rows: List[List[str]] = None
    
    # Summary
    total_lambda: float = 0.0
    sheet_reliability: float = 1.0
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = ["Reference", "Class", "λ (1/h)", "R"]
        if self.rows is None:
            self.rows = []


class KiCadTableGenerator:
    """
    Generates KiCad 9 table objects for reliability data.
    
    The tables show per-component reliability data and are inserted
    into the schematic files.
    """
    
    # Table styling
    FONT_SIZE = 1.27  # mm
    CELL_HEIGHT = 4.0  # mm
    COLUMN_WIDTHS = [25, 45, 25, 20]  # mm for each column
    HEADER_BG = "#E0E0E0"
    
    def __init__(self):
        self.tables: Dict[str, ReliabilityTable] = {}
    
    def create_table(self, sheet_path: str, components: List[Dict],
                     total_lambda: float, sheet_r: float,
                     x: float = 200.0, y: float = 20.0) -> ReliabilityTable:
        """
        Create a reliability table for a sheet.
        
        Args:
            sheet_path: Path to the sheet
            components: List of component dicts with keys:
                        reference, class, lambda, reliability
            total_lambda: Total failure rate for the sheet
            sheet_r: Overall reliability of the sheet
            x, y: Position in mm
        """
        table = ReliabilityTable(
            sheet_path=sheet_path,
            x=x,
            y=y,
            total_lambda=total_lambda,
            sheet_reliability=sheet_r,
        )
        
        # Build data rows
        for comp in components:
            row = [
                comp.get("reference", "?"),
                comp.get("class", "Unknown")[:20],  # Truncate long class names
                f"{comp.get('lambda', 0):.2e}",
                f"{comp.get('reliability', 1.0):.4f}",
            ]
            table.rows.append(row)
        
        self.tables[sheet_path] = table
        return table
    
    def generate_sexp(self, table: ReliabilityTable) -> str:
        """
        Generate KiCad S-expression for the table.
        
        Returns:
            S-expression string that can be inserted into a .kicad_sch file
        """
        num_cols = len(table.headers)
        num_rows = len(table.rows) + 2  # Header + data + summary
        
        # Calculate total width and column widths string
        col_widths = " ".join(str(w) for w in self.COLUMN_WIDTHS[:num_cols])
        
        lines = []
        lines.append(f'  (table (id "reliability_table")')
        lines.append(f'    (at {table.x} {table.y})')
        lines.append(f'    (columns {num_cols})')
        lines.append(f'    (column_widths {col_widths})')
        lines.append(f'    (effects')
        lines.append(f'      (font (size {self.FONT_SIZE} {self.FONT_SIZE}))')
        lines.append(f'    )')
        lines.append(f'    (border (width 0.254))')
        
        # Generate cells
        lines.append(f'    (cells')
        
        # Header row
        for header in table.headers:
            lines.append(f'      (cell "{header}" (effects (font (bold yes))))')
        
        # Data rows
        for row in table.rows:
            for cell in row:
                lines.append(f'      (cell "{cell}")')
        
        # Summary row
        lines.append(f'      (cell "TOTAL" (effects (font (bold yes))))')
        lines.append(f'      (cell "")')
        lines.append(f'      (cell "{table.total_lambda:.2e}" (effects (font (bold yes))))')
        lines.append(f'      (cell "{table.sheet_reliability:.4f}" (effects (font (bold yes))))')
        
        lines.append(f'    )')
        lines.append(f'  )')
        
        return '\n'.join(lines)
    
    def generate_text_box(self, table: ReliabilityTable) -> str:
        """
        Generate a text box with reliability summary as fallback.
        
        This is simpler than a full table and more compatible.
        """
        text_lines = [
            f"=== Reliability Analysis ===",
            f"Sheet: {table.sheet_path}",
            f"",
            f"{'Ref':<8} {'λ (1/h)':<12} {'R':>8}",
            f"{'-'*30}",
        ]
        
        for row in table.rows[:10]:  # Limit to 10 components
            ref, cls, lam, r = row
            text_lines.append(f"{ref:<8} {lam:<12} {r:>8}")
        
        if len(table.rows) > 10:
            text_lines.append(f"... and {len(table.rows) - 10} more")
        
        text_lines.extend([
            f"{'-'*30}",
            f"{'TOTAL':<8} {table.total_lambda:.2e} {table.sheet_reliability:.4f}",
        ])
        
        text = "\\n".join(text_lines)
        
        sexp = f'''  (text_box "{text}"
    (at {table.x} {table.y})
    (size 120 {5 + len(text_lines) * 3})
    (effects
      (font (face "Monospace") (size 1.5 1.5))
      (justify left top)
    )
    (border (width 0.254))
    (fill (type background) (color 255 255 240 1))
  )'''
        
        return sexp
    
    def inject_into_schematic(self, sch_path: str, table: ReliabilityTable,
                              use_text_box: bool = True) -> bool:
        """
        Inject table into an existing schematic file.
        
        Args:
            sch_path: Path to .kicad_sch file
            table: The table to inject
            use_text_box: Use text box instead of table (more compatible)
            
        Returns:
            True if successful
        """
        path = Path(sch_path)
        if not path.exists():
            return False
        
        try:
            content = path.read_text(encoding='utf-8')
        except Exception:
            return False
        
        # Remove any existing reliability table/text_box
        # Look for our marker
        import re
        content = re.sub(
            r'\s*\((?:table|text_box)[^)]*\(id "reliability_table"\)[^)]*\)(?:\s*\))+',
            '',
            content,
            flags=re.DOTALL
        )
        
        # Also try simpler pattern for text boxes without id
        content = re.sub(
            r'\s*\(text_box "=== Reliability Analysis ===[^"]*"[^)]*(?:\([^)]*\))*\s*\)',
            '',
            content,
            flags=re.DOTALL
        )
        
        # Generate new table/text_box
        if use_text_box:
            new_content = self.generate_text_box(table)
        else:
            new_content = self.generate_sexp(table)
        
        # Find position to insert - before closing paren of kicad_sch
        # The schematic format is (kicad_sch ... )
        insert_pos = content.rfind(')')
        if insert_pos == -1:
            return False
        
        # Insert table before final closing paren
        content = content[:insert_pos] + '\n' + new_content + '\n' + content[insert_pos:]
        
        try:
            path.write_text(content, encoding='utf-8')
            return True
        except Exception:
            return False
    
    def remove_from_schematic(self, sch_path: str) -> bool:
        """Remove reliability table from a schematic."""
        path = Path(sch_path)
        if not path.exists():
            return False
        
        try:
            content = path.read_text(encoding='utf-8')
        except Exception:
            return False
        
        import re
        
        # Remove table with id
        content = re.sub(
            r'\s*\((?:table|text_box)[^)]*\(id "reliability_table"\)[^)]*\)(?:\s*\))+',
            '',
            content,
            flags=re.DOTALL
        )
        
        # Remove text box by content
        content = re.sub(
            r'\s*\(text_box "=== Reliability Analysis ===[^"]*"[^)]*(?:\([^)]*\))*\s*\)',
            '',
            content,
            flags=re.DOTALL
        )
        
        try:
            path.write_text(content, encoding='utf-8')
            return True
        except Exception:
            return False


# =============================================================================
# Alternative: Generate standalone report file
# =============================================================================

class ReliabilityReportGenerator:
    """
    Generates standalone reliability reports in various formats.
    
    This is an alternative to injecting tables into schematics,
    useful for documentation and review.
    """
    
    def generate_markdown(self, tables: Dict[str, ReliabilityTable],
                          system_r: float, system_lambda: float) -> str:
        """Generate a Markdown report."""
        lines = [
            "# Reliability Analysis Report",
            "",
            "## System Summary",
            "",
            f"- **System Reliability**: {system_r:.6f}",
            f"- **System Failure Rate**: {system_lambda:.2e} failures/hour",
            "",
            "## Per-Sheet Analysis",
            "",
        ]
        
        for path, table in sorted(tables.items()):
            lines.extend([
                f"### {path}",
                "",
                f"Sheet Reliability: **{table.sheet_reliability:.6f}**",
                f"Sheet λ: {table.total_lambda:.2e}",
                "",
                "| Reference | Class | λ (1/h) | R |",
                "|-----------|-------|---------|---|",
            ])
            
            for row in table.rows:
                lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
            
            lines.append("")
        
        return '\n'.join(lines)
    
    def generate_csv(self, tables: Dict[str, ReliabilityTable]) -> str:
        """Generate a CSV report."""
        lines = ["Sheet,Reference,Class,Lambda,Reliability"]
        
        for path, table in sorted(tables.items()):
            for row in table.rows:
                lines.append(f'"{path}","{row[0]}","{row[1]}",{row[2]},{row[3]}')
        
        return '\n'.join(lines)
    
    def generate_html(self, tables: Dict[str, ReliabilityTable],
                      system_r: float, system_lambda: float) -> str:
        """Generate an HTML report with styling."""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Reliability Analysis Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        h2 { color: #555; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
        h3 { color: #666; }
        table { border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #f5f5f5; }
        .summary { background: #e8f4e8; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .lambda { font-family: monospace; }
    </style>
</head>
<body>
    <h1>Reliability Analysis Report</h1>
    
    <div class="summary">
        <h2>System Summary</h2>
        <p><strong>System Reliability:</strong> ''' + f'{system_r:.6f}' + '''</p>
        <p><strong>System Failure Rate:</strong> <span class="lambda">''' + f'{system_lambda:.2e}' + '''</span> failures/hour</p>
    </div>
    
    <h2>Per-Sheet Analysis</h2>
'''
        
        for path, table in sorted(tables.items()):
            html += f'''
    <h3>{path}</h3>
    <p>Sheet Reliability: <strong>{table.sheet_reliability:.6f}</strong> | 
       Sheet λ: <span class="lambda">{table.total_lambda:.2e}</span></p>
    <table>
        <tr><th>Reference</th><th>Class</th><th>λ (1/h)</th><th>R</th></tr>
'''
            for row in table.rows:
                html += f'        <tr><td>{row[0]}</td><td>{row[1]}</td><td class="lambda">{row[2]}</td><td>{row[3]}</td></tr>\n'
            
            html += '    </table>\n'
        
        html += '''
</body>
</html>'''
        
        return html


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    # Test table generation
    gen = KiCadTableGenerator()
    
    components = [
        {"reference": "R1", "class": "Resistor (11.1)", "lambda": 1.5e-10, "reliability": 0.9999},
        {"reference": "C1", "class": "Ceramic Cap (10.3)", "lambda": 2.1e-10, "reliability": 0.9998},
        {"reference": "U1", "class": "IC (7)", "lambda": 5.0e-9, "reliability": 0.9950},
    ]
    
    table = gen.create_table(
        "/Power/Buck/",
        components,
        total_lambda=5.35e-9,
        sheet_r=0.9947
    )
    
    print("Generated S-expression table:")
    print(gen.generate_sexp(table))
    print("\n" + "="*50 + "\n")
    print("Generated text box:")
    print(gen.generate_text_box(table))
