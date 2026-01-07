"""
Reliability Mathematics Module - IEC TR 62380 Implementation

This module centralizes ALL reliability calculations based on IEC TR 62380.
All formulas are in one place for easy tuning and maintenance.

Units:
- Failure rates (λ): FIT = failures per 10^9 hours (converted to per-hour at output)
- Temperature: °C
- Time: hours (for mission), cycles/year (for thermal cycling)
"""

import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass


# =============================================================================
# CONNECTION TYPE - Used by block_editor
# =============================================================================

class ConnectionType:
    """Types of reliability connections for block diagrams."""
    SERIES = "series"
    PARALLEL = "parallel"
    K_OF_N = "k_of_n"
    
    def __init__(self, value=None):
        """Allow construction from string value."""
        if value is None:
            self._value = self.SERIES
        else:
            self._value = value
    
    @property
    def value(self):
        """Return the string value for serialization."""
        if hasattr(self, '_value'):
            return self._value
        return self.SERIES
    
    def __eq__(self, other):
        if isinstance(other, ConnectionType):
            return self.value == other.value
        return self.value == other
    
    def __hash__(self):
        return hash(self.value)
    
    def __str__(self):
        return self.value


# =============================================================================
# COMPONENT PARAMS - For backward compatibility
# =============================================================================

class ComponentParams:
    """Parameter container for component calculations."""
    
    def __init__(self, **kwargs):
        self.t_ambient = kwargs.get('t_ambient', 25.0)
        self.t_junction = kwargs.get('t_junction', 85.0)
        self.operating_power = kwargs.get('operating_power', 0.01)
        self.rated_power = kwargs.get('rated_power', 0.125)
        self.n_cycles = kwargs.get('n_cycles', 5256)
        self.delta_t = kwargs.get('delta_t', 3.0)
        self.w_on = kwargs.get('w_on', 1.0)
        self.voltage_stress = kwargs.get('voltage_stress', 0.5)
        
        for k, v in kwargs.items():
            if not hasattr(self, k):
                setattr(self, k, v)
    
    def to_dict(self):
        return vars(self)


# =============================================================================
# CONSTANTS AND LOOKUP TABLES (IEC TR 62380)
# =============================================================================

class ActivationEnergy:
    """Activation energies in Kelvin (Ea * 11605)"""
    MOS = 3480        # 0.3 eV
    BIPOLAR = 4640    # 0.4 eV
    CAPACITOR_LOW = 1160   # 0.1 eV (ceramic class I)
    CAPACITOR_MED = 1740   # 0.15 eV (tantalum, resistors)
    CAPACITOR_HIGH = 2900  # 0.25 eV (plastic/paper)
    ALUMINUM_CAP = 4640    # 0.4 eV (aluminum electrolytic)
    RESISTOR = 1740        # 0.15 eV
    GaAs_DIGITAL = 3480    # 0.3 eV
    GaAs_MMIC = 4640       # 0.4 eV


# IC Die Parameters (Table 16)
IC_DIE_TABLE = {
    "MOS_DIGITAL": {"l1": 3.4e-6, "l2": 1.7, "ea": ActivationEnergy.MOS},
    "MOS_LINEAR": {"l1": 3.4e-6, "l2": 1.7, "ea": ActivationEnergy.MOS},
    "MOS_MIXED": {"l1": 3.4e-6, "l2": 1.7, "ea": ActivationEnergy.MOS},
    "MOS_SRAM_FAST": {"l1": 2.7e-4, "l2": 20, "ea": ActivationEnergy.MOS},
    "MOS_FLASH": {"l1": 2.6e-7, "l2": 34, "ea": ActivationEnergy.MOS},
    "MOS_EEPROM": {"l1": 6.5e-7, "l2": 16, "ea": ActivationEnergy.MOS},
    "MOS_LCA": {"l1": 1.2e-5, "l2": 10, "ea": ActivationEnergy.MOS},
    "MOS_PLD": {"l1": 2.0e-5, "l2": 10, "ea": ActivationEnergy.MOS},
    "MOS_CPLD": {"l1": 4.0e-5, "l2": 8.8, "ea": ActivationEnergy.MOS},
    "BIPOLAR_LINEAR": {"l1": 2.7e-2, "l2": 20, "ea": ActivationEnergy.BIPOLAR},
    "BIPOLAR_DIGITAL": {"l1": 2.7e-3, "l2": 20, "ea": ActivationEnergy.BIPOLAR},
    "BICMOS_LOW_V": {"l1": 2.7e-4, "l2": 20, "ea": ActivationEnergy.MOS},
    "BICMOS_HIGH_V": {"l1": 2.7e-3, "l2": 20, "ea": ActivationEnergy.BIPOLAR},
    "GaAs_DIGITAL": {"l1": 1.0e-3, "l2": 10, "ea": ActivationEnergy.GaAs_DIGITAL},
    "GaAs_MMIC": {"l1": 1.5e-3, "l2": 10, "ea": ActivationEnergy.GaAs_MMIC},
}

IC_TYPE_CHOICES = {
    "Microcontroller/DSP": "MOS_DIGITAL",
    "FPGA (RAM-based)": "MOS_LCA", 
    "CPLD/FPGA (Flash)": "MOS_CPLD",
    "Standard Logic (74xx)": "MOS_DIGITAL",
    "Op-Amp/Comparator": "BIPOLAR_LINEAR",
    "Voltage Reference": "BIPOLAR_LINEAR",
    "LDO Regulator": "BICMOS_LOW_V",
    "DC-DC Controller": "BICMOS_HIGH_V",
    "Power Management IC": "BICMOS_HIGH_V",
    "ADC/DAC": "MOS_MIXED",
    "Memory - SRAM": "MOS_SRAM_FAST",
    "Memory - Flash": "MOS_FLASH",
    "Memory - EEPROM": "MOS_EEPROM",
    "Interface IC (UART/SPI/I2C)": "MOS_DIGITAL",
    "CAN/RS-485 Transceiver": "BICMOS_HIGH_V",
    "RF/Wireless IC": "GaAs_MMIC",
}

# IC Package Parameters (Table 17)
IC_PACKAGE_TABLE = {
    "SO": {"formula": "pins", "coef": 0.012, "exp": 1.65},
    "TSSOP": {"formula": "pins", "coef": 0.011, "exp": 1.4},
    "SSOP": {"formula": "pins", "coef": 0.013, "exp": 1.35},
    "PLCC": {"formula": "pins", "coef": 0.021, "exp": 1.57},
    "TQFP-7x7": {"formula": "fixed", "value": 2.5},
    "TQFP-10x10": {"formula": "fixed", "value": 4.1},
    "PQFP-14x14": {"formula": "fixed", "value": 7.2},
    "PQFP-20x20": {"formula": "fixed", "value": 16.0},
    "PBGA-17x19": {"formula": "fixed", "value": 16.6},
    "PBGA-23x23": {"formula": "fixed", "value": 26.6},
    "PDIP": {"formula": "pins_alt", "coef": 9.0, "exp": 0.9},
    "QFN": {"formula": "diagonal", "coef": 0.048, "exp": 1.68},
}

IC_PACKAGE_CHOICES = {
    "SOIC-8": ("SO", 8),
    "SOIC-14": ("SO", 14),
    "SOIC-16": ("SO", 16),
    "TSSOP-14": ("TSSOP", 14),
    "TSSOP-20": ("TSSOP", 20),
    "TSSOP-24": ("TSSOP", 24),
    "QFP-32 (7x7mm)": ("TQFP-7x7", 32),
    "QFP-48 (7x7mm)": ("TQFP-7x7", 48),
    "QFP-64 (10x10mm)": ("TQFP-10x10", 64),
    "QFP-100 (14x14mm)": ("PQFP-14x14", 100),
    "QFN-16 (4x4mm)": ("QFN", 16, 5.66),
    "QFN-32 (5x5mm)": ("QFN", 32, 7.07),
    "QFN-48 (7x7mm)": ("QFN", 48, 9.90),
    "BGA-256 (17x17mm)": ("PBGA-17x19", 256),
    "PDIP-8": ("PDIP", 8),
    "PDIP-14": ("PDIP", 14),
    "PDIP-28": ("PDIP", 28),
}

# Discrete Package Parameters (Table 18)
DISCRETE_PACKAGE_TABLE = {
    "TO-92": {"lb": 1.0, "rja": 300},
    "TO-220": {"lb": 5.7, "rja": 60},
    "TO-247": {"lb": 6.9, "rja": 35},
    "TO-263 (D2PAK)": {"lb": 5.7, "rja": 15},
    "TO-252 (DPAK)": {"lb": 5.1, "rja": 30},
    "SOT-23": {"lb": 1.0, "rja": 400},
    "SOT-89": {"lb": 2.0, "rja": 125},
    "SOT-223": {"lb": 3.4, "rja": 85},
    "SOT-323": {"lb": 0.8, "rja": 600},
    "DO-35": {"lb": 2.5, "rja": 400},
    "DO-41": {"lb": 2.5, "rja": 100},
    "SOD-123": {"lb": 1.0, "rja": 600},
    "SOD-323": {"lb": 0.7, "rja": 600},
    "SMA": {"lb": 1.8, "rja": 600},
    "SMB": {"lb": 2.4, "rja": 75},
    "0402": {"lb": 0.5},
    "0603": {"lb": 0.6},
    "0805": {"lb": 0.8},
    "1206": {"lb": 1.0},
}

THERMAL_EXPANSION_SUBSTRATE = {
    "FR4 (Epoxy Glass)": 16.0,
    "Polyimide Flex": 6.5,
    "Alumina (Ceramic)": 6.5,
    "Aluminum (Metal Core)": 23.0,
}

INTERFACE_EOS_VALUES = {
    "Not Interface": {"pi_i": 0, "l_eos": 0},
    "Computer": {"pi_i": 1, "l_eos": 10},
    "Telecom (Switching)": {"pi_i": 1, "l_eos": 15},
    "Telecom (Subscriber)": {"pi_i": 1, "l_eos": 70},
    "Avionics": {"pi_i": 1, "l_eos": 20},
    "Power Supply": {"pi_i": 1, "l_eos": 40},
}

DIODE_BASE_RATES = {
    "Signal (<1A)": {"l0": 0.07, "power_class": "low"},
    "Recovery/Rectifier (1-3A)": {"l0": 0.1, "power_class": "low"},
    "Zener (≤1.5W)": {"l0": 0.4, "power_class": "low"},
    "TVS": {"l0": 2.3, "power_class": "low"},
    "Schottky (<3A)": {"l0": 0.15, "power_class": "low"},
    "LED": {"l0": 0.5, "power_class": "low"},
    "Recovery/Rectifier (>3A)": {"l0": 0.7, "power_class": "high"},
    "Zener (>1.5W)": {"l0": 0.7, "power_class": "high"},
    "Schottky (≥3A)": {"l0": 0.7, "power_class": "high"},
}

TRANSISTOR_BASE_RATES = {
    "Silicon BJT (≤5W)": {"l0": 0.75, "power_class": "low", "tech": "bipolar"},
    "Silicon MOSFET (≤5W)": {"l0": 0.75, "power_class": "low", "tech": "mos"},
    "Silicon JFET (≤5W)": {"l0": 0.75, "power_class": "low", "tech": "mos"},
    "Silicon BJT (>5W)": {"l0": 2.0, "power_class": "high", "tech": "bipolar"},
    "Silicon MOSFET (>5W)": {"l0": 2.0, "power_class": "high", "tech": "mos"},
    "Silicon IGBT": {"l0": 2.0, "power_class": "high", "tech": "igbt"},
}

CAPACITOR_PARAMS = {
    "Plastic/Paper Film": {"l0": 0.1, "pkg_coef": 1.4e-3, "ea": ActivationEnergy.CAPACITOR_HIGH, "t_ref": 303},
    "Ceramic Class I (C0G/NP0)": {"l0": 0.05, "pkg_coef": 3.3e-3, "ea": ActivationEnergy.CAPACITOR_LOW, "t_ref": 303},
    "Ceramic Class II (X7R/X5R)": {"l0": 0.15, "pkg_coef": 3.3e-3, "ea": ActivationEnergy.CAPACITOR_LOW, "t_ref": 303},
    "Tantalum Solid": {"l0": 0.4, "pkg_coef": 3.8e-3, "ea": ActivationEnergy.CAPACITOR_MED, "t_ref": 303},
    "Aluminum Electrolytic (Non-Solid)": {"l0": 1.3, "pkg_coef": 1.4e-3, "ea": ActivationEnergy.ALUMINUM_CAP, "t_ref": 313},
}

RESISTOR_PARAMS = {
    "Film (Low Dissipation)": {"l0": 0.1, "pkg_coef": 1.4e-3, "temp_coef": 85},
    "Carbon Composition": {"l0": 0.5, "pkg_coef": 1.4e-3, "temp_coef": 60},
    "Wirewound (Low Dissipation)": {"l0": 0.3, "pkg_coef": 1.4e-3, "temp_coef": 30},
    "SMD Chip Resistor": {"l0": 0.01, "pkg_coef": 3.3e-3, "temp_coef": 55},
}

INDUCTOR_PARAMS = {
    "Fixed (Low Current)": {"l0": 0.2},
    "Variable": {"l0": 0.4},
    "Power Inductor": {"l0": 0.6},
    "Signal Transformer": {"l0": 1.5},
    "Power Transformer": {"l0": 3.0},
}

MISC_COMPONENT_RATES = {
    "Crystal Oscillator (XO)": 10.0,
    "VCXO/TCXO": 15.0,
    "Quartz Resonator": 5.0,
    "Relay (Reed)": 50.0,
    "Connector (per contact)": 0.5,
    "DC-DC Converter (<10W)": 100.0,
    "DC-DC Converter (≥10W)": 130.0,
    "Fuse": 2.0,
    "Ferrite Bead": 0.5,
}


# =============================================================================
# CORE CALCULATION FUNCTIONS
# =============================================================================

def pi_thermal_cycles(n_cycles: float) -> float:
    """Thermal cycling factor π_n (IEC TR 62380 Section 5.7)"""
    if n_cycles <= 8760:
        return n_cycles ** 0.76
    else:
        return 1.7 * (n_cycles ** 0.6)


def pi_temperature(t: float, ea: float, t_ref: float) -> float:
    """Temperature acceleration factor π_t (Arrhenius model)"""
    return math.exp(ea * ((1/t_ref) - (1/(273 + t))))


def pi_alpha(alpha_substrate: float, alpha_package: float) -> float:
    """Thermal expansion mismatch factor π_α"""
    return 0.06 * (abs(alpha_substrate - alpha_package) ** 1.68)


def calculate_ic_lambda3(package_type: str, pins: int = None, diagonal: float = None) -> float:
    """Calculate IC package failure rate contribution λ3"""
    pkg = IC_PACKAGE_TABLE.get(package_type)
    if not pkg:
        return 4.0
    
    formula = pkg.get("formula", "fixed")
    if formula == "fixed":
        return pkg["value"]
    elif formula == "pins" and pins:
        return pkg["coef"] * (pins ** pkg["exp"])
    elif formula == "pins_alt" and pins:
        return pkg["coef"] + pins ** pkg["exp"]
    elif formula == "diagonal" and diagonal:
        return pkg["coef"] * (diagonal ** pkg["exp"])
    return 4.0


# =============================================================================
# COMPONENT LAMBDA CALCULATIONS
# =============================================================================

def lambda_integrated_circuit(
    ic_type: str = "MOS_DIGITAL",
    transistor_count: int = 10000,
    construction_year: int = 2020,
    t_junction: float = 85.0,
    package_type: str = "TQFP-10x10",
    pins: int = 48,
    substrate_alpha: float = 16.0,
    package_alpha: float = 21.5,
    is_interface: bool = False,
    interface_type: str = "Not Interface",
    n_cycles: int = 5256,
    delta_t: float = 3.0,
    w_on: float = 1.0,
    **kwargs
) -> Dict[str, float]:
    """Calculate IC failure rate per IEC TR 62380 Section 7"""
    die_params = IC_DIE_TABLE.get(ic_type, IC_DIE_TABLE["MOS_DIGITAL"])
    l1 = die_params["l1"]
    l2 = die_params["l2"]
    ea = die_params["ea"]
    
    a = max(0, construction_year - 1998)
    year_factor = math.exp(-0.35 * a)
    
    t_ref = 328
    pi_t = pi_temperature(t_junction, ea, t_ref)
    
    lambda_die = (l1 * transistor_count * year_factor + l2) * pi_t * w_on
    
    l3 = calculate_ic_lambda3(package_type, pins)
    pi_a = pi_alpha(substrate_alpha, package_alpha)
    pi_n = pi_thermal_cycles(n_cycles)
    lambda_package = 2.75e-3 * pi_a * pi_n * (delta_t ** 0.68) * l3
    
    eos_params = INTERFACE_EOS_VALUES.get(interface_type, INTERFACE_EOS_VALUES["Not Interface"])
    lambda_eos = eos_params["pi_i"] * eos_params["l_eos"] if is_interface else 0
    
    lambda_total = (lambda_die + lambda_package + lambda_eos) * 1e-9
    
    return {
        "lambda_die": lambda_die * 1e-9,
        "lambda_package": lambda_package * 1e-9,
        "lambda_eos": lambda_eos * 1e-9,
        "lambda_total": lambda_total,
        "fit_total": lambda_die + lambda_package + lambda_eos
    }


def lambda_diode(
    diode_type: str = "Signal (<1A)",
    t_junction: float = 85.0,
    package: str = "SOD-123",
    is_interface: bool = False,
    interface_type: str = "Not Interface",
    n_cycles: int = 5256,
    delta_t: float = 3.0,
    w_on: float = 1.0,
    **kwargs
) -> Dict[str, float]:
    """Calculate diode failure rate per IEC TR 62380 Sections 8.2/8.3"""
    params = DIODE_BASE_RATES.get(diode_type, DIODE_BASE_RATES["Signal (<1A)"])
    l0 = params["l0"]
    
    pi_t = pi_temperature(t_junction, ActivationEnergy.BIPOLAR, 313)
    lambda_die = l0 * pi_t * w_on
    
    pkg_params = DISCRETE_PACKAGE_TABLE.get(package, {"lb": 1.0})
    lb = pkg_params.get("lb", 1.0)
    pi_n = pi_thermal_cycles(n_cycles)
    lambda_package = 2.75e-3 * pi_n * (delta_t ** 0.68) * lb
    
    eos_params = INTERFACE_EOS_VALUES.get(interface_type, INTERFACE_EOS_VALUES["Not Interface"])
    lambda_eos = eos_params["pi_i"] * eos_params["l_eos"] if is_interface else 0
    
    lambda_total = (lambda_die + lambda_package + lambda_eos) * 1e-9
    
    return {
        "lambda_die": lambda_die * 1e-9,
        "lambda_package": lambda_package * 1e-9,
        "lambda_eos": lambda_eos * 1e-9,
        "lambda_total": lambda_total,
        "fit_total": lambda_die + lambda_package + lambda_eos
    }


def lambda_transistor(
    transistor_type: str = "Silicon MOSFET (≤5W)",
    t_junction: float = 85.0,
    package: str = "SOT-23",
    voltage_stress_vce: float = 0.5,
    voltage_stress_vds: float = 0.5,
    voltage_stress_vgs: float = 0.5,
    is_interface: bool = False,
    interface_type: str = "Not Interface",
    n_cycles: int = 5256,
    delta_t: float = 3.0,
    w_on: float = 1.0,
    **kwargs
) -> Dict[str, float]:
    """Calculate transistor failure rate per IEC TR 62380 Sections 8.4/8.5"""
    params = TRANSISTOR_BASE_RATES.get(transistor_type, TRANSISTOR_BASE_RATES["Silicon MOSFET (≤5W)"])
    l0 = params["l0"]
    tech = params["tech"]
    
    ea = ActivationEnergy.BIPOLAR if tech == "bipolar" else ActivationEnergy.MOS
    pi_t = pi_temperature(t_junction, ea, 373)
    
    if tech == "bipolar":
        s = min(voltage_stress_vce, 1.0)
        pi_s = 0.22 * math.exp(1.7 * s)
    else:
        s1 = min(voltage_stress_vds, 1.0)
        s2 = min(voltage_stress_vgs, 1.0)
        pi_s1 = 0.22 * math.exp(1.7 * s1)
        pi_s2 = 0.22 * math.exp(3 * s2)
        pi_s = pi_s1 * pi_s2
    
    lambda_die = pi_s * l0 * pi_t * w_on
    
    pkg_params = DISCRETE_PACKAGE_TABLE.get(package, {"lb": 1.0})
    lb = pkg_params.get("lb", 1.0)
    pi_n = pi_thermal_cycles(n_cycles)
    lambda_package = 2.75e-3 * pi_n * (delta_t ** 0.68) * lb
    
    eos_params = INTERFACE_EOS_VALUES.get(interface_type, INTERFACE_EOS_VALUES["Not Interface"])
    lambda_eos = eos_params["pi_i"] * eos_params["l_eos"] if is_interface else 0
    
    lambda_total = (lambda_die + lambda_package + lambda_eos) * 1e-9
    
    return {
        "lambda_die": lambda_die * 1e-9,
        "lambda_package": lambda_package * 1e-9,
        "lambda_eos": lambda_eos * 1e-9,
        "lambda_total": lambda_total,
        "fit_total": lambda_die + lambda_package + lambda_eos,
        "pi_s": pi_s
    }


def lambda_capacitor(
    capacitor_type: str = "Ceramic Class II (X7R/X5R)",
    t_ambient: float = 25.0,
    ripple_ratio: float = 0.0,
    n_cycles: int = 5256,
    delta_t: float = 3.0,
    w_on: float = 1.0,
    **kwargs
) -> Dict[str, float]:
    """Calculate capacitor failure rate per IEC TR 62380 Section 10"""
    params = CAPACITOR_PARAMS.get(capacitor_type, CAPACITOR_PARAMS["Ceramic Class II (X7R/X5R)"])
    l0 = params["l0"]
    pkg_coef = params["pkg_coef"]
    ea = params["ea"]
    t_ref = params["t_ref"]
    
    t_op = t_ambient
    if "Aluminum" in capacitor_type and ripple_ratio > 0:
        t_op = t_ambient + 20 * (ripple_ratio ** 2)
    
    pi_t = pi_temperature(t_op, ea, t_ref)
    pi_n = pi_thermal_cycles(n_cycles)
    pkg_factor = pkg_coef * pi_n * (delta_t ** 0.68)
    
    lambda_base = l0 * pi_t * w_on
    lambda_package = l0 * pkg_factor
    lambda_total = (lambda_base + lambda_package) * 1e-9
    
    return {
        "lambda_base": lambda_base * 1e-9,
        "lambda_package": lambda_package * 1e-9,
        "lambda_total": lambda_total,
        "fit_total": lambda_base + lambda_package,
        "pi_t": pi_t
    }


def lambda_resistor(
    resistor_type: str = "SMD Chip Resistor",
    t_ambient: float = 25.0,
    operating_power: float = 0.01,
    rated_power: float = 0.125,
    n_resistors: int = 1,
    n_cycles: int = 5256,
    delta_t: float = 3.0,
    w_on: float = 1.0,
    **kwargs
) -> Dict[str, float]:
    """Calculate resistor failure rate per IEC TR 62380 Section 11"""
    params = RESISTOR_PARAMS.get(resistor_type, RESISTOR_PARAMS["SMD Chip Resistor"])
    l0 = params["l0"]
    pkg_coef = params["pkg_coef"]
    temp_coef = params["temp_coef"]
    
    power_ratio = operating_power / max(rated_power, 1e-6)
    t_resistor = t_ambient + temp_coef * power_ratio
    
    pi_t = pi_temperature(t_resistor, ActivationEnergy.RESISTOR, 303)
    pi_n = pi_thermal_cycles(n_cycles)
    pkg_factor = pkg_coef * pi_n * (delta_t ** 0.68)
    
    l0_effective = l0 * n_resistors
    
    lambda_base = l0_effective * pi_t * w_on
    lambda_package = l0_effective * pkg_factor
    lambda_total = (lambda_base + lambda_package) * 1e-9
    
    return {
        "lambda_base": lambda_base * 1e-9,
        "lambda_package": lambda_package * 1e-9,
        "lambda_total": lambda_total,
        "fit_total": lambda_base + lambda_package,
        "t_resistor": t_resistor,
        "pi_t": pi_t
    }


def lambda_inductor(
    inductor_type: str = "Power Inductor",
    t_ambient: float = 25.0,
    power_loss: float = 0.1,
    surface_area_mm2: float = 100.0,
    n_cycles: int = 5256,
    delta_t: float = 3.0,
    w_on: float = 1.0,
    **kwargs
) -> Dict[str, float]:
    """Calculate inductor/transformer failure rate per IEC TR 62380 Section 12"""
    params = INDUCTOR_PARAMS.get(inductor_type, INDUCTOR_PARAMS["Power Inductor"])
    l0 = params["l0"]
    
    surface_dm2 = surface_area_mm2 / 10000.0
    t_rise = 8.2 * (power_loss / max(surface_dm2, 0.01))
    t_component = t_ambient + t_rise
    
    pi_t = pi_temperature(t_component, ActivationEnergy.RESISTOR, 303)
    pi_n = pi_thermal_cycles(n_cycles)
    pkg_factor = 7e-3 * pi_n * (delta_t ** 0.68)
    
    lambda_base = l0 * pi_t * w_on
    lambda_package = l0 * pkg_factor
    lambda_total = (lambda_base + lambda_package) * 1e-9
    
    return {
        "lambda_base": lambda_base * 1e-9,
        "lambda_package": lambda_package * 1e-9,
        "lambda_total": lambda_total,
        "fit_total": lambda_base + lambda_package,
        "t_component": t_component
    }


def lambda_misc_component(
    component_type: str,
    n_contacts: int = 1,
    n_cycles: int = 5256,
    delta_t: float = 3.0,
    w_on: float = 1.0,
    **kwargs
) -> Dict[str, float]:
    """Calculate failure rate for miscellaneous components"""
    base_rate = MISC_COMPONENT_RATES.get(component_type, 10.0)
    
    if "Connector" in component_type:
        base_rate = base_rate * n_contacts
    
    pi_n = pi_thermal_cycles(n_cycles)
    pkg_factor = 3e-3 * pi_n * (delta_t ** 0.68)
    
    lambda_total = base_rate * (1 + pkg_factor) * 1e-9 * w_on
    
    return {
        "lambda_total": lambda_total,
        "fit_total": base_rate * (1 + pkg_factor)
    }


# =============================================================================
# SYSTEM RELIABILITY CALCULATIONS
# =============================================================================

def reliability_from_lambda(lambda_val: float, mission_hours: float) -> float:
    """Calculate reliability from failure rate: R(t) = exp(-λ × t)"""
    return math.exp(-lambda_val * mission_hours)


def lambda_from_reliability(r: float, mission_hours: float) -> float:
    """Calculate equivalent failure rate from reliability: λ = -ln(R) / t"""
    if r <= 0:
        return float('inf')
    if r >= 1:
        return 0.0
    return -math.log(r) / mission_hours


def mttf_from_lambda(lambda_val: float) -> float:
    """Calculate Mean Time To Failure: MTTF = 1/λ"""
    if lambda_val <= 0:
        return float('inf')
    return 1.0 / lambda_val


def r_series(r_list: List[float]) -> float:
    """Series system reliability: R = R1 × R2 × ... × Rn"""
    result = 1.0
    for r in r_list:
        result *= r
    return result


def r_parallel(r_list: List[float]) -> float:
    """Parallel system reliability: R = 1 - (1-R1) × (1-R2) × ... × (1-Rn)"""
    p_fail = 1.0
    for r in r_list:
        p_fail *= (1 - r)
    return 1.0 - p_fail


def r_k_of_n(r_list: List[float], k: int) -> float:
    """K-of-N redundancy system reliability"""
    n = len(r_list)
    
    if k > n or k < 1:
        return 0.0
    if k == 1:
        return r_parallel(r_list)
    if k == n:
        return r_series(r_list)
    
    if len(set(r_list)) == 1:
        r = r_list[0]
        result = 0.0
        for i in range(k, n + 1):
            binom = math.comb(n, i)
            result += binom * (r ** i) * ((1 - r) ** (n - i))
        return result
    
    r_n = r_list[-1]
    r_rest = r_list[:-1]
    return r_n * r_k_of_n(r_rest, k - 1) + (1 - r_n) * r_k_of_n(r_rest, k)


def lambda_series(lambda_list: List[float]) -> float:
    """Series system failure rate: λ = λ1 + λ2 + ... + λn"""
    return sum(lambda_list)


# =============================================================================
# FIELD DEFINITIONS FOR UI
# =============================================================================

def get_component_types() -> List[str]:
    """Get list of all supported component type categories."""
    return [
        "Integrated Circuit",
        "Diode",
        "Transistor",
        "Capacitor",
        "Resistor",
        "Inductor/Transformer",
        "Crystal/Oscillator",
        "Connector",
        "Miscellaneous"
    ]


def get_field_definitions(component_type: str) -> Dict[str, Dict]:
    """Get field definitions for a component type."""
    common_fields = {
        "n_cycles": {"type": "int", "default": 5256, "help": "Annual thermal cycles", "required": False},
        "delta_t": {"type": "float", "default": 3.0, "help": "Temperature swing (°C)", "required": False},
        "w_on": {"type": "float", "default": 1.0, "help": "Working time ratio", "required": False},
    }
    
    if component_type == "Integrated Circuit":
        return {
            "ic_type": {"type": "choice", "choices": list(IC_TYPE_CHOICES.keys()), "default": "Microcontroller/DSP", "help": "IC type", "required": True},
            "transistor_count": {"type": "int", "default": 10000, "help": "Transistor count", "required": True},
            "construction_year": {"type": "int", "default": 2020, "help": "Manufacturing year", "required": False},
            "t_junction": {"type": "float", "default": 85.0, "help": "Junction temp (°C)", "required": True},
            "package": {"type": "choice", "choices": list(IC_PACKAGE_CHOICES.keys()), "default": "QFP-48 (7x7mm)", "help": "Package", "required": True},
            "substrate": {"type": "choice", "choices": list(THERMAL_EXPANSION_SUBSTRATE.keys()), "default": "FR4 (Epoxy Glass)", "help": "PCB substrate", "required": False},
            "is_interface": {"type": "bool", "default": False, "help": "Interface circuit?", "required": False},
            "interface_type": {"type": "choice", "choices": list(INTERFACE_EOS_VALUES.keys()), "default": "Not Interface", "help": "Interface type", "required": False},
            **common_fields
        }
    elif component_type == "Diode":
        return {
            "diode_type": {"type": "choice", "choices": list(DIODE_BASE_RATES.keys()), "default": "Signal (<1A)", "help": "Diode type", "required": True},
            "t_junction": {"type": "float", "default": 85.0, "help": "Junction temp (°C)", "required": True},
            "package": {"type": "choice", "choices": [k for k in DISCRETE_PACKAGE_TABLE.keys() if "SOD" in k or "DO" in k or "SM" in k], "default": "SOD-123", "help": "Package", "required": True},
            "is_interface": {"type": "bool", "default": False, "help": "Protection interface?", "required": False},
            **common_fields
        }
    elif component_type == "Transistor":
        return {
            "transistor_type": {"type": "choice", "choices": list(TRANSISTOR_BASE_RATES.keys()), "default": "Silicon MOSFET (≤5W)", "help": "Transistor type", "required": True},
            "t_junction": {"type": "float", "default": 85.0, "help": "Junction temp (°C)", "required": True},
            "package": {"type": "choice", "choices": [k for k in DISCRETE_PACKAGE_TABLE.keys() if "TO" in k or "SOT" in k], "default": "SOT-23", "help": "Package", "required": True},
            "voltage_stress_vds": {"type": "float", "default": 0.5, "help": "VDS stress ratio", "required": False},
            "voltage_stress_vgs": {"type": "float", "default": 0.5, "help": "VGS stress ratio", "required": False},
            "voltage_stress_vce": {"type": "float", "default": 0.5, "help": "VCE stress ratio (BJT)", "required": False},
            **common_fields
        }
    elif component_type == "Capacitor":
        return {
            "capacitor_type": {"type": "choice", "choices": list(CAPACITOR_PARAMS.keys()), "default": "Ceramic Class II (X7R/X5R)", "help": "Capacitor type", "required": True},
            "t_ambient": {"type": "float", "default": 25.0, "help": "Ambient temp (°C)", "required": True},
            "ripple_ratio": {"type": "float", "default": 0.0, "help": "Ripple current ratio", "required": False},
            **common_fields
        }
    elif component_type == "Resistor":
        return {
            "resistor_type": {"type": "choice", "choices": list(RESISTOR_PARAMS.keys()), "default": "SMD Chip Resistor", "help": "Resistor type", "required": True},
            "t_ambient": {"type": "float", "default": 25.0, "help": "Ambient temp (°C)", "required": True},
            "operating_power": {"type": "float", "default": 0.01, "help": "Operating power (W)", "required": True},
            "rated_power": {"type": "float", "default": 0.125, "help": "Rated power (W)", "required": True},
            **common_fields
        }
    elif component_type == "Inductor/Transformer":
        return {
            "inductor_type": {"type": "choice", "choices": list(INDUCTOR_PARAMS.keys()), "default": "Power Inductor", "help": "Type", "required": True},
            "t_ambient": {"type": "float", "default": 25.0, "help": "Ambient temp (°C)", "required": True},
            "power_loss": {"type": "float", "default": 0.1, "help": "Power loss (W)", "required": True},
            "surface_area_mm2": {"type": "float", "default": 100.0, "help": "Surface area (mm²)", "required": True},
            **common_fields
        }
    else:
        return {
            "component_subtype": {"type": "choice", "choices": list(MISC_COMPONENT_RATES.keys()), "default": "Crystal Oscillator (XO)", "help": "Subtype", "required": True},
            "n_contacts": {"type": "int", "default": 1, "help": "Contacts (connectors)", "required": False},
            **common_fields
        }


def calculate_component_lambda(component_type: str, params: Dict[str, Any]) -> Dict[str, float]:
    """Universal dispatcher to calculate lambda for any component type."""
    if component_type == "Integrated Circuit":
        ic_key = IC_TYPE_CHOICES.get(params.get("ic_type", "Microcontroller/DSP"), "MOS_DIGITAL")
        pkg_choice = params.get("package", "QFP-48 (7x7mm)")
        pkg_info = IC_PACKAGE_CHOICES.get(pkg_choice, ("TQFP-10x10", 48))
        pkg_type = pkg_info[0]
        pins = pkg_info[1] if len(pkg_info) > 1 else 48
        
        substrate = params.get("substrate", "FR4 (Epoxy Glass)")
        substrate_alpha = THERMAL_EXPANSION_SUBSTRATE.get(substrate, 16.0)
        
        return lambda_integrated_circuit(
            ic_type=ic_key, transistor_count=params.get("transistor_count", 10000),
            construction_year=params.get("construction_year", 2020),
            t_junction=params.get("t_junction", 85.0), package_type=pkg_type, pins=pins,
            substrate_alpha=substrate_alpha, is_interface=params.get("is_interface", False),
            interface_type=params.get("interface_type", "Not Interface"),
            n_cycles=params.get("n_cycles", 5256), delta_t=params.get("delta_t", 3.0),
            w_on=params.get("w_on", 1.0)
        )
    elif component_type == "Diode":
        return lambda_diode(**params)
    elif component_type == "Transistor":
        return lambda_transistor(**params)
    elif component_type == "Capacitor":
        return lambda_capacitor(**params)
    elif component_type == "Resistor":
        return lambda_resistor(**params)
    elif component_type == "Inductor/Transformer":
        return lambda_inductor(**params)
    else:
        return lambda_misc_component(component_type=params.get("component_subtype", "Crystal Oscillator (XO)"), **params)


def calculate_lambda(component_class: str, params: Dict[str, Any] = None) -> float:
    """Legacy interface for calculate_lambda."""
    if params is None:
        params = {}
    
    cls = component_class.lower()
    n_cycles = params.get("n_cycles", 5256)
    delta_t = params.get("delta_t", 3.0)
    
    if "resistor" in cls:
        result = lambda_resistor(
            t_ambient=params.get("t_ambient", 25),
            operating_power=params.get("operating_power", 0.01),
            rated_power=params.get("rated_power", 0.125),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "ceramic" in cls and "capacitor" in cls:
        result = lambda_capacitor(
            capacitor_type="Ceramic Class II (X7R/X5R)",
            t_ambient=params.get("t_ambient", 25),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "tantalum" in cls or "electrolytic" in cls:
        cap_type = "Tantalum Solid" if "tantalum" in cls else "Aluminum Electrolytic (Non-Solid)"
        result = lambda_capacitor(
            capacitor_type=cap_type,
            t_ambient=params.get("t_ambient", 25),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "transistor" in cls:
        result = lambda_transistor(
            t_junction=params.get("t_junction", 85),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "diode" in cls:
        result = lambda_diode(
            t_junction=params.get("t_junction", 85),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "integrated circuit" in cls or cls in ("ic", "mcu", "microcontroller", "fpga"):
        result = lambda_integrated_circuit(
            t_junction=params.get("t_junction", 85),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "inductor" in cls:
        result = lambda_inductor(
            t_ambient=params.get("t_ambient", 25),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "converter" in cls or "dc-dc" in cls:
        return lambda_misc_component("DC-DC Converter (<10W)", n_cycles=n_cycles, delta_t=delta_t)["lambda_total"]
    
    if "ldo" in cls or "regulator" in cls:
        result = lambda_integrated_circuit(
            ic_type="BICMOS_LOW_V",
            t_junction=params.get("t_junction", 100),
            n_cycles=n_cycles, delta_t=delta_t
        )
        return result["lambda_total"]
    
    if "crystal" in cls or "oscillator" in cls:
        return lambda_misc_component("Crystal Oscillator (XO)")["lambda_total"]
    
    if "connector" in cls:
        return lambda_misc_component("Connector (per contact)", n_contacts=params.get("n_pins", 10))["lambda_total"]
    
    # Default
    return 10e-9


# =============================================================================
# BACKWARD COMPATIBILITY EXPORTS
# =============================================================================

def component_failure_rate(component_class: str, params: ComponentParams = None) -> float:
    """Legacy function name for calculate_lambda."""
    param_dict = params.to_dict() if params else {}
    return calculate_lambda(component_class, param_dict)


# Aliases
ecss_component_failure_rate = component_failure_rate
reliability = reliability_from_lambda
