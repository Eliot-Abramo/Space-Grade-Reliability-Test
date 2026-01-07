
"""
ECSS field and category loader.

This module loads ECSS categories and field definitions from JSON files:
    - ecss_categories.json : UI + mapping to math models
    - ecss_tables.json     : numerical tables (base rates, pi factors, ...)

It provides a stable API for the GUI and math code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent

_CATEGORIES: Dict[str, Any] = {}
_TABLES: Dict[str, Any] = {}


def _load_json(name: str) -> Dict[str, Any]:
    path = BASE_DIR / name
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_specs() -> None:
    """Load JSON specs into module-level caches."""
    global _CATEGORIES, _TABLES
    data = _load_json("ecss_categories.json")
    _CATEGORIES = data.get("categories", {})
    _TABLES = _load_json("ecss_tables.json")


# Load at import-time for convenience
load_specs()


def get_categories() -> Dict[str, Any]:
    return _CATEGORIES


def get_tables() -> Dict[str, Any]:
    return _TABLES


def get_category_fields(category: str) -> Dict[str, Any]:
    """Return full definition dict for a category key."""
    cat = _CATEGORIES.get(category)
    if not cat:
        # Fallback with empty fields so the dialog still works
        return {"display_name": category, "fields": {}}
    return cat


def infer_category_from_class(component_class: str, footprint: str = "") -> str:
    """Heuristic mapping from KiCad 'Class' / 'Reliability_Class' + footprint
    to an ECSS category key defined in the JSON.

    This is intentionally simple; you can always override the category in the
    ECSS dialog itself.
    """
    cls = (component_class or "").lower()
    fp = (footprint or "").lower()

    # Passives
    if "res" in cls or "resistor" in cls:
        return "resistor"
    if "cap" in cls or "capa" in cls:
        if "tant" in cls or "tant" in fp:
            return "capacitor_tantalum"
        return "capacitor_ceramic"

    # Diodes / transistors
    if "diod" in cls or "diode" in cls or "led" in cls or "zener" in cls or "tvs" in cls:
        return "diode"
    if "bjt" in cls or "npn" in cls or "pnp" in cls or "bipolar" in cls:
        return "bjt"
    if "mosfet" in cls or "fet" in cls or "igbt" in cls:
        return "mosfet"

    # ICs
    if "fpga" in cls:
        return "fpga"
    if "opamp" in cls or "opa" in cls or "analog" in cls:
        return "ic_analog"
    if "ic" in cls or cls.startswith("u") or "mcu" in cls or "logic" in cls or "asic" in cls:
        return "ic_digital"

    # Connectors
    if "conn" in cls or "hdr" in fp or "connector" in cls:
        return "connector"

    # Power modules
    if "dcdc" in cls or "dc-dc" in cls or "converter" in cls or "regulator" in cls:
        return "converter"

    # Magnetics
    if "inductor" in cls or "choke" in cls or "transformer" in cls:
        return "inductor"

    # Crystals / oscillators
    if "crystal" in cls or "osc" in cls:
        return "crystal"

    # Batteries
    if "battery" in cls or "cell" in cls:
        return "battery"

    # Relays
    if "relay" in cls:
        return "relay"

    # Fallback
    return "resistor"
