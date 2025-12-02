"""
Reliability Calculation Core

This module contains all the reliability calculation functions based on
FIDES methodology (or similar standards). The calculations are organized
by component type.

All lambda (failure rate) values are in failures per hour.
Reliability R = exp(-lambda * t) where t is mission time in hours.
"""

import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


# =============================================================================
# Component Classification Enums
# =============================================================================

class ComponentClass(Enum):
    """Supported component classes for reliability calculation."""
    RESISTOR = "Resistor (11.1)"
    CERAMIC_CAPACITOR = "Ceramic Capacitor (10.3)"
    TANTALUM_CAPACITOR = "Tantalum Capacitor (10.4)"
    LOW_POWER_TRANSISTOR = "Low Power Transistor (8.4)"
    POWER_TRANSISTOR = "Power Transistor (8.5)"
    LOW_POWER_DIODE = "Low Power Diode (8.2)"
    POWER_DIODE = "Power Diode (8.3)"
    INTEGRATED_CIRCUIT = "Integrated Circuit (7)"
    INDUCTOR = "Inductor (12)"
    CONVERTER = "Converter <10W (19.6)"
    PRIMARY_BATTERY = "Primary Battery (19.1)"


# =============================================================================
# Data Classes for Component Parameters
# =============================================================================

@dataclass
class ComponentParams:
    """Base parameters common to all components."""
    reference: str
    component_class: str
    n_cycles: int = 5256  # Annual thermal cycles (default: 1 per 100 min)
    delta_t: float = 3.0  # Temperature variation during cycle (°C)
    

@dataclass
class ResistorParams(ComponentParams):
    """Parameters for resistor reliability calculation."""
    t_ambient: float = 25.0  # Ambient temperature (°C)
    operating_power: float = 0.01  # Operating power (W)
    rated_power: float = 0.125  # Rated power (W)


@dataclass
class CapacitorParams(ComponentParams):
    """Parameters for capacitor reliability calculation."""
    t_ambient: float = 25.0  # Ambient temperature (°C)
    cap_type: str = "ceramic"  # "ceramic" or "tantalum"


@dataclass
class TransistorParams(ComponentParams):
    """Parameters for transistor reliability calculation."""
    t_junction: float = 85.0  # Junction temperature (°C)
    transistor_type: str = "MOS"  # "MOS" or "Bipolar"
    power_class: str = "low"  # "low" or "high"
    package: str = "SOT-23, 3 pins"
    # Stress ratios
    v_ce_applied: float = 0.0
    v_ce_specified: float = 1.0
    v_ds_applied: float = 0.0
    v_ds_specified: float = 1.0
    v_gs_applied: float = 0.0
    v_gs_specified: float = 1.0
    pi_i: float = 1.0  # Induced overstress factor
    l_eos: float = 40.0  # EOS failure rate contribution


@dataclass
class DiodeParams(ComponentParams):
    """Parameters for diode reliability calculation."""
    t_junction: float = 85.0
    diode_type: str = "signal"  # signal, recovery, zener, transient, trigger, gallium, thyristors
    power_class: str = "low"  # "low" or "high"
    package: str = "SOD-123, 3 pins"
    pi_i: float = 1.0
    l_eos: float = 40.0


@dataclass
class ICParams(ComponentParams):
    """Parameters for integrated circuit reliability calculation."""
    construction_year: int = 2020
    t_junction: float = 85.0
    ic_type: str = "MOS Standard, Digital circuits, 20000 transistors"
    package: str = "TQFP,10x10"
    substrate_material: str = "Epoxy"
    pcb_material: str = "FR4"


@dataclass
class InductorParams(ComponentParams):
    """Parameters for inductor reliability calculation."""
    t_ambient: float = 25.0
    power_loss: float = 0.1  # Power dissipation (W)
    surface_area: float = 100.0  # Radiating surface (mm²)
    inductor_type: str = "Power Inductor"  # low fixed, low variable, Power Inductor


@dataclass
class ConverterParams(ComponentParams):
    """Parameters for DC-DC converter reliability calculation."""
    power_rating: float = 5.0  # Watts


# =============================================================================
# Lookup Tables
# =============================================================================

# IC die parameters (Table 16 equivalent)
IC_DIE_PARAMS = {
    "MOS Standard, Digital circuits, 20000 transistors": {"l1": 3.4e-6, "l2": 1.7, "n": 20000},
    "MOS Standard, Digital circuits, 810 transistors": {"l1": 3.4e-6, "l2": 1.7, "n": 810},
    "MOS Standard, Digital circuits, 2 gates": {"l1": 3.4e-6, "l2": 1.7, "n": 8},
    "BICMOS, SRAM, Static Read Access Memory, 8-bit": {"l1": 6.8e-7, "l2": 8.8, "n": 32},
    "MOS ASIC, Gate Arrays, 12 gates": {"l1": 2.0e-5, "l2": 10, "n": 48},
    "Bipolar, Linear/Digital circuit low voltage, 15 transistors": {"l1": 2.7e-4, "l2": 20, "n": 15},
    "BICMOS, linear/digital circuits, high voltage, 500 transistors": {"l1": 2.7e-3, "l2": 20, "n": 500},
    "Bipolar circuits, linear/digital circuits, high voltage, 5000 transistors": {"l1": 2.7e-2, "l2": 20, "n": 5000},
    "BICMOS, linear/digital circuits, high voltage, 20 transistors": {"l1": 2.7e-3, "l2": 20, "n": 20},
    "BICMOS, linear/digital circuits, low voltage, 20 transistors": {"l1": 2.7e-4, "l2": 20, "n": 20},
}

# IC package parameters (Table 17a equivalent)
IC_PACKAGE_PARAMS = {
    "TSSOP, 16 pins": lambda: 0.011 * (16 ** 1.4),
    "TSOP I: 0.5mm pitch, 20 pins": lambda: 20 ** 0.36,
    "SO,SOP, 8 pins": lambda: 0.012 * (8 ** 1.65),
    "SO,SOP, 16 pins": lambda: 0.012 * (16 ** 1.65),
    "TQFP,10x10": lambda: 4.1,
    "TQFP, 5x5": lambda: 1.3,
    "PQFP, TQFP, 5x5": lambda: 1.3,
}

# Discrete package parameters (Table 18 equivalent)
DISCRETE_PACKAGE_PARAMS = {
    "D2PACK, 3 pins": 5.7,
    "SOT-23, 3 pins": 1.0,
    "SOD-123, 3 pins": 1.0,
    "TO-220, 3 pins": 5.7,
    "DPACK, 6 pins": 5.1,
    "TO-247, 3 pins": 6.9,
}

# Diode base failure rates
DIODE_BASE_RATES = {
    ("signal", "low"): 0.07,
    ("signal", "high"): 0.07,
    ("recovery", "low"): 0.1,
    ("recovery", "high"): 0.7,
    ("zener", "low"): 0.4,
    ("zener", "high"): 0.7,
    ("transient", "low"): 2.3,
    ("transient", "high"): 0.7,
    ("trigger", "low"): 2.0,
    ("trigger", "high"): 3.0,
    ("gallium", "low"): 0.3,
    ("gallium", "high"): 1.0,
    ("thyristors", "low"): 1.0,
    ("thyristors", "high"): 3.0,
}

# Inductor base failure rates
INDUCTOR_BASE_RATES = {
    ("inductor", "low fixed"): 0.2,
    ("inductor", "low variable"): 0.4,
    ("inductor", "Power Inductor"): 0.6,
    ("transformer", "signal"): 1.5,
    ("transformer", "power"): 3.0,
}

# Thermal expansion coefficients
THERMAL_EXPANSION = {
    "Epoxy": 16,
    "FR4": 21.5,
}


# =============================================================================
# Common Pi Factors
# =============================================================================

def pi_n(n_cycles: float) -> float:
    """Calculate thermal cycling factor."""
    if n_cycles <= 8760:
        return n_cycles ** 0.76
    return 1.7 * (n_cycles ** 0.6)


def pi_thermal_ic(t_junction: float, is_bipolar: bool = False) -> float:
    """Calculate IC thermal acceleration factor."""
    ea = 4640 if is_bipolar else 3480  # Activation energy
    t_ref = 328  # Reference temperature (K)
    return math.exp(ea * ((1 / t_ref) - (1 / (273 + t_junction))))


def pi_thermal_diode(t_junction: float) -> float:
    """Calculate diode thermal acceleration factor."""
    return math.exp(4640 * ((1 / 313) - (1 / (273 + t_junction))))


def pi_thermal_transistor(t_junction: float, is_bipolar: bool = True) -> float:
    """Calculate transistor thermal acceleration factor."""
    ea = 4640 if is_bipolar else 3480
    t_ref = 373
    return math.exp(ea * ((1 / t_ref) - (1 / (t_junction + 273))))


def pi_thermal_capacitor(t_ambient: float, is_tantalum: bool = False) -> float:
    """Calculate capacitor thermal acceleration factor."""
    ea = 1740 if is_tantalum else 1160
    return math.exp(ea * ((1 / 303) - (1 / (273 + t_ambient))))


def pi_thermal_resistor(t_ambient: float, op_power: float, rated_power: float) -> float:
    """Calculate resistor thermal acceleration factor."""
    t_resistor = t_ambient + 85 * (op_power / rated_power)
    return math.exp(1740 * ((1 / 303) - (1 / (273 + t_resistor))))


def pi_thermal_inductor(t_ambient: float, power_loss: float, surface: float) -> float:
    """Calculate inductor thermal acceleration factor."""
    t_rise = 8.2 * (power_loss / surface)
    t_operating = t_ambient + t_rise
    return math.exp(1740 * (1 / 303 - 1 / (t_operating + 273)))


def pi_alpha(substrate: str, pcb: str) -> float:
    """Calculate thermal expansion mismatch factor."""
    alpha_s = THERMAL_EXPANSION.get(substrate, 16)
    alpha_c = THERMAL_EXPANSION.get(pcb, 21.5)
    return 0.06 * (abs(alpha_s - alpha_c) ** 1.68)


def pi_stress_transistor(
    transistor_type: str,
    v_ce: float, v_ce_max: float,
    v_ds: float, v_ds_max: float,
    v_gs: float, v_gs_max: float
) -> float:
    """Calculate transistor electrical stress factor."""
    if transistor_type == "Bipolar":
        s = v_ce / v_ce_max if v_ce_max > 0 else 0
        return 0.22 * math.exp(1.7 * s)
    else:  # MOS
        s1 = v_ds / v_ds_max if v_ds_max > 0 else 0
        s2 = v_gs / v_gs_max if v_gs_max > 0 else 0
        return 0.22 * math.exp(1.7 * s1) * 0.22 * math.exp(3 * s2)


# =============================================================================
# Component Lambda Calculations
# =============================================================================

def lambda_resistor(params: ResistorParams) -> float:
    """Calculate resistor failure rate (failures/hour)."""
    pi_t = pi_thermal_resistor(params.t_ambient, params.operating_power, params.rated_power)
    pi_cyc = pi_n(params.n_cycles) * (params.delta_t ** 0.68)
    return 0.1 * (pi_t + 1.4e-3 * pi_cyc) * 1e-9


def lambda_capacitor(params: CapacitorParams) -> float:
    """Calculate capacitor failure rate (failures/hour)."""
    is_tantalum = params.cap_type.lower() == "tantalum"
    pi_t = pi_thermal_capacitor(params.t_ambient, is_tantalum)
    pi_cyc = pi_n(params.n_cycles) * (params.delta_t ** 0.68)
    
    if is_tantalum:
        return 0.4 * (pi_t + 3.8e-3 * pi_cyc) * 1e-9
    return 0.15 * (pi_t + 3.3e-3 * pi_cyc) * 1e-9


def lambda_transistor(params: TransistorParams) -> float:
    """Calculate transistor failure rate (failures/hour)."""
    is_bipolar = params.transistor_type == "Bipolar"
    
    # Die contribution
    pi_t = pi_thermal_transistor(params.t_junction, is_bipolar)
    pi_s = pi_stress_transistor(
        params.transistor_type,
        params.v_ce_applied, params.v_ce_specified,
        params.v_ds_applied, params.v_ds_specified,
        params.v_gs_applied, params.v_gs_specified
    )
    l0 = 0.75 if params.power_class == "low" else 2.0
    lambda_die = pi_s * l0 * pi_t
    
    # Package contribution
    l_b = DISCRETE_PACKAGE_PARAMS.get(params.package, 1.0)
    lambda_pkg = 2.75e-3 * pi_n(params.n_cycles) * (params.delta_t ** 0.68) * l_b
    
    # Overstress contribution
    lambda_eos = params.pi_i * params.l_eos
    
    return (lambda_die + lambda_pkg + lambda_eos) * 1e-9


def lambda_diode(params: DiodeParams) -> float:
    """Calculate diode failure rate (failures/hour)."""
    # Die contribution
    pi_t = pi_thermal_diode(params.t_junction)
    power_key = "low" if params.power_class == "low" else "high"
    l0 = DIODE_BASE_RATES.get((params.diode_type, power_key), 0.1)
    pi_u = 10 if params.diode_type == "thyristors" else 1
    lambda_die = pi_u * l0 * pi_t
    
    # Package contribution
    l_b = DISCRETE_PACKAGE_PARAMS.get(params.package, 1.0)
    lambda_pkg = 2.75e-3 * pi_n(params.n_cycles) * (params.delta_t ** 0.68) * l_b
    
    # Overstress contribution
    lambda_eos = params.pi_i * params.l_eos
    
    return (lambda_die + lambda_pkg + lambda_eos) * 1e-9


def lambda_ic(params: ICParams) -> float:
    """Calculate integrated circuit failure rate (failures/hour)."""
    # Get die parameters
    die_params = IC_DIE_PARAMS.get(params.ic_type)
    if die_params is None:
        return 0.0
    
    l1, l2, n_transistors = die_params["l1"], die_params["l2"], die_params["n"]
    
    # Check if bipolar type
    is_bipolar = "Bipolar" in params.ic_type or "high voltage" in params.ic_type
    
    # Die contribution
    year_factor = math.exp(-0.35 * (params.construction_year - 1998))
    pi_t = pi_thermal_ic(params.t_junction, is_bipolar)
    lambda_die = (l1 * n_transistors * year_factor + l2) * pi_t
    
    # Package contribution
    pkg_func = IC_PACKAGE_PARAMS.get(params.package)
    l3 = pkg_func() if pkg_func else 1.0
    pi_a = pi_alpha(params.substrate_material, params.pcb_material)
    lambda_pkg = 2.75e-3 * pi_a * pi_n(params.n_cycles) * (params.delta_t ** 0.68) * l3
    
    # Base contribution
    lambda_base = 40
    
    return (lambda_die + lambda_pkg + lambda_base) * 1e-9


def lambda_inductor(params: InductorParams) -> float:
    """Calculate inductor failure rate (failures/hour)."""
    # Get base rate
    l0 = INDUCTOR_BASE_RATES.get(("inductor", params.inductor_type), 0.6)
    
    # Thermal contribution
    pi_t = pi_thermal_inductor(params.t_ambient, params.power_loss, params.surface_area)
    
    # Cycling contribution
    pi_cyc = pi_n(params.n_cycles) * (params.delta_t ** 0.68)
    
    return l0 * (pi_t + 7e-3 * pi_cyc) * 1e-9


def lambda_converter(params: ConverterParams) -> float:
    """Calculate DC-DC converter failure rate (failures/hour)."""
    l0 = 100 if params.power_rating < 10 else 130
    pi_cyc = pi_n(params.n_cycles) * (params.delta_t ** 0.68)
    return l0 * (1 + 3e-3 * pi_cyc) * 1e-9


def lambda_battery() -> float:
    """Calculate primary battery failure rate (failures/hour)."""
    return 20e-9


# =============================================================================
# System Reliability Calculations
# =============================================================================

def reliability(lambda_val: float, mission_hours: float) -> float:
    """Calculate reliability from failure rate and mission time."""
    return math.exp(-lambda_val * mission_hours)


def lambda_from_reliability(r: float, mission_hours: float) -> float:
    """Calculate equivalent failure rate from reliability."""
    if r <= 0 or r > 1:
        return float('inf') if r <= 0 else 0.0
    return -math.log(r) / mission_hours


def r_series(r_list: List[float]) -> float:
    """Calculate series reliability (all must work)."""
    result = 1.0
    for r in r_list:
        result *= r
    return result


def r_parallel(r_list: List[float]) -> float:
    """Calculate parallel reliability (at least one must work)."""
    p_fail = 1.0
    for r in r_list:
        p_fail *= (1 - r)
    return 1.0 - p_fail


def r_k_of_n(r_list: List[float], k: int) -> float:
    """
    Calculate k-of-n redundancy reliability.
    At least k out of n components must work.
    
    For identical components with reliability r:
    R = sum_{i=k}^{n} C(n,i) * r^i * (1-r)^(n-i)
    
    For non-identical, we use inclusion-exclusion or approximation.
    """
    n = len(r_list)
    if k > n or k < 1:
        return 0.0
    if k == 1:
        return r_parallel(r_list)
    if k == n:
        return r_series(r_list)
    
    # For 2-of-3 with identical components (common case)
    if n == 3 and k == 2:
        ra, rb, rc = r_list[0], r_list[1], r_list[2]
        # P(at least 2 work) = P(all 3) + P(exactly 2)
        p_all = ra * rb * rc
        p_ab = ra * rb * (1 - rc)
        p_ac = ra * (1 - rb) * rc
        p_bc = (1 - ra) * rb * rc
        return p_all + p_ab + p_ac + p_bc
    
    # General case using recursion (can be slow for large n)
    # R(k,n) = r_n * R(k-1, n-1) + (1-r_n) * R(k, n-1)
    if n == 1:
        return r_list[0] if k == 1 else 0.0
    
    r_n = r_list[-1]
    r_rest = r_list[:-1]
    
    return r_n * r_k_of_n(r_rest, k - 1) + (1 - r_n) * r_k_of_n(r_rest, k)


# =============================================================================
# Component Factory
# =============================================================================

def calculate_component_lambda(component_class: str, params: Dict[str, Any]) -> float:
    """
    Calculate failure rate for a component based on its class and parameters.
    
    Args:
        component_class: The component classification string
        params: Dictionary of component parameters from symbol fields
        
    Returns:
        Failure rate in failures per hour
    """
    # Normalize class name
    cls = component_class.lower()
    
    # Default values
    n_cycles = params.get("n_cycles", 5256)
    delta_t = params.get("delta_t", 3.0)
    
    if "resistor" in cls:
        p = ResistorParams(
            reference=params.get("reference", "R?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            t_ambient=params.get("t_ambient", 25.0),
            operating_power=params.get("operating_power", 0.01),
            rated_power=params.get("rated_power", 0.125),
        )
        return lambda_resistor(p)
    
    elif "ceramic" in cls and "capacitor" in cls:
        p = CapacitorParams(
            reference=params.get("reference", "C?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            t_ambient=params.get("t_ambient", 25.0),
            cap_type="ceramic",
        )
        return lambda_capacitor(p)
    
    elif "tantalum" in cls and "capacitor" in cls:
        p = CapacitorParams(
            reference=params.get("reference", "C?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            t_ambient=params.get("t_ambient", 25.0),
            cap_type="tantalum",
        )
        return lambda_capacitor(p)
    
    elif "transistor" in cls:
        is_power = "power" in cls
        p = TransistorParams(
            reference=params.get("reference", "Q?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            t_junction=params.get("t_junction", 85.0),
            transistor_type=params.get("transistor_type", "MOS"),
            power_class="high" if is_power else "low",
            package=params.get("package", "SOT-23, 3 pins"),
            v_ce_applied=params.get("v_ce_applied", 0.0),
            v_ce_specified=params.get("v_ce_specified", 1.0),
            v_ds_applied=params.get("v_ds_applied", 0.0),
            v_ds_specified=params.get("v_ds_specified", 1.0),
            v_gs_applied=params.get("v_gs_applied", 0.0),
            v_gs_specified=params.get("v_gs_specified", 1.0),
        )
        return lambda_transistor(p)
    
    elif "diode" in cls:
        is_power = "power" in cls
        p = DiodeParams(
            reference=params.get("reference", "D?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            t_junction=params.get("t_junction", 85.0),
            diode_type=params.get("diode_type", "signal"),
            power_class="high" if is_power else "low",
            package=params.get("package", "SOD-123, 3 pins"),
        )
        return lambda_diode(p)
    
    elif "integrated circuit" in cls or "ic" in cls:
        p = ICParams(
            reference=params.get("reference", "U?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            construction_year=params.get("construction_year", 2020),
            t_junction=params.get("t_junction", 85.0),
            ic_type=params.get("ic_type", "MOS Standard, Digital circuits, 20000 transistors"),
            package=params.get("package", "TQFP,10x10"),
            substrate_material=params.get("substrate", "Epoxy"),
            pcb_material=params.get("pcb", "FR4"),
        )
        return lambda_ic(p)
    
    elif "inductor" in cls:
        p = InductorParams(
            reference=params.get("reference", "L?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            t_ambient=params.get("t_ambient", 25.0),
            power_loss=params.get("power_loss", 0.1),
            surface_area=params.get("surface_area", 100.0),
            inductor_type=params.get("inductor_type", "Power Inductor"),
        )
        return lambda_inductor(p)
    
    elif "converter" in cls:
        p = ConverterParams(
            reference=params.get("reference", "PS?"),
            component_class=component_class,
            n_cycles=n_cycles,
            delta_t=delta_t,
            power_rating=params.get("power_rating", 5.0),
        )
        return lambda_converter(p)
    
    elif "battery" in cls:
        return lambda_battery()
    
    # Unknown component type
    return 0.0
