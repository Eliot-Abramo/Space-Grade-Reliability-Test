"""
Reliability Calculation Core

All the reliability calculation functions based on FIDES methodology.
Lambda (failure rate) values are in failures per hour.
Reliability R = exp(-lambda * t) where t is mission time in hours.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Any
from enum import Enum


from .reliability_math import ComponentParams, component_failure_rate as ecss_component_failure_rate


class ConnectionType(Enum):
    """Types of reliability connections."""
    SERIES = "series"
    PARALLEL = "parallel"
    K_OF_N = "k_of_n"


# =============================================================================
# Lookup Tables
# =============================================================================

IC_DIE_PARAMS = {
    "MOS Standard, Digital circuits, 20000 transistors": {"l1": 3.4e-6, "l2": 1.7, "n": 20000},
    "MOS Standard, Digital circuits, 810 transistors": {"l1": 3.4e-6, "l2": 1.7, "n": 810},
    "MOS Standard, Digital circuits, 2 gates": {"l1": 3.4e-6, "l2": 1.7, "n": 8},
    "BICMOS, SRAM, 8-bit": {"l1": 6.8e-7, "l2": 8.8, "n": 32},
    "MOS ASIC, Gate Arrays, 12 gates": {"l1": 2.0e-5, "l2": 10, "n": 48},
    "Bipolar, Linear/Digital low voltage, 15 transistors": {"l1": 2.7e-4, "l2": 20, "n": 15},
    "BICMOS, Linear/Digital high voltage, 500 transistors": {"l1": 2.7e-3, "l2": 20, "n": 500},
    "Bipolar, Linear/Digital high voltage, 5000 transistors": {"l1": 2.7e-2, "l2": 20, "n": 5000},
    "BICMOS, Linear/Digital high voltage, 20 transistors": {"l1": 2.7e-3, "l2": 20, "n": 20},
    "BICMOS, Linear/Digital low voltage, 20 transistors": {"l1": 2.7e-4, "l2": 20, "n": 20},
}

IC_PACKAGE_PARAMS = {
    "TSSOP-16": 0.011 * (16 ** 1.4),
    "TSOP-20": 20 ** 0.36,
    "SOIC-8": 0.012 * (8 ** 1.65),
    "SOIC-16": 0.012 * (16 ** 1.65),
    "TQFP-32": 4.1,
    "TQFP-48": 4.1,
    "TQFP-64": 4.1,
    "TQFP-100": 4.1,
    "QFN-16": 1.3,
    "QFN-32": 1.3,
    "QFN-48": 1.3,
    "BGA-256": 6.0,
}

DISCRETE_PACKAGE_PARAMS = {
    "D2PAK": 5.7,
    "SOT-23": 1.0,
    "SOT-223": 2.0,
    "SOD-123": 1.0,
    "SOD-323": 1.0,
    "TO-220": 5.7,
    "TO-252": 5.1,
    "TO-263": 5.7,
    "TO-247": 6.9,
    "0402": 0.5,
    "0603": 0.6,
    "0805": 0.8,
    "1206": 1.0,
}

DIODE_BASE_RATES = {
    "signal": 0.07,
    "recovery": 0.1,
    "schottky": 0.15,
    "zener": 0.4,
    "TVS": 2.3,
    "LED": 0.5,
}


# =============================================================================
# Pi Factor Calculations
# =============================================================================

def pi_n(n_cycles: float) -> float:
    """Thermal cycling factor."""
    if n_cycles <= 8760:
        return n_cycles ** 0.76
    return 1.7 * (n_cycles ** 0.6)


def pi_thermal(t: float, ea: float, t_ref: float) -> float:
    """Generic thermal acceleration factor."""
    return math.exp(ea * ((1 / t_ref) - (1 / (273 + t))))


# =============================================================================
# Component Lambda Calculations  
# =============================================================================

def lambda_resistor(t_ambient: float = 25.0, op_power: float = 0.01, 
                    rated_power: float = 0.125, n_cycles: int = 5256, 
                    delta_t: float = 3.0) -> float:
    """Calculate resistor failure rate."""
    t_r = t_ambient + 85 * (op_power / max(rated_power, 0.001))
    pi_t = math.exp(1740 * ((1/303) - (1/(273 + t_r))))
    pi_cyc = pi_n(n_cycles) * (delta_t ** 0.68)
    return 0.1 * (pi_t + 1.4e-3 * pi_cyc) * 1e-9


def lambda_capacitor(t_ambient: float = 25.0, cap_type: str = "ceramic",
                     n_cycles: int = 5256, delta_t: float = 3.0) -> float:
    """Calculate capacitor failure rate."""
    ea = 1740 if cap_type == "tantalum" else 1160
    pi_t = math.exp(ea * ((1/303) - (1/(273 + t_ambient))))
    pi_cyc = pi_n(n_cycles) * (delta_t ** 0.68)
    
    if cap_type == "tantalum":
        return 0.4 * (pi_t + 3.8e-3 * pi_cyc) * 1e-9
    return 0.15 * (pi_t + 3.3e-3 * pi_cyc) * 1e-9


def lambda_transistor(t_junction: float = 85.0, transistor_type: str = "MOS",
                      power_class: str = "low", package: str = "SOT-23",
                      stress_ratio: float = 0.5, n_cycles: int = 5256,
                      delta_t: float = 3.0) -> float:
    """Calculate transistor failure rate."""
    is_bipolar = transistor_type.upper() == "BIPOLAR"
    
    # Die contribution
    ea = 4640 if is_bipolar else 3480
    pi_t = math.exp(ea * ((1/373) - (1/(t_junction + 273))))
    pi_s = 0.22 * math.exp(1.7 * stress_ratio)
    l0 = 0.75 if power_class == "low" else 2.0
    lambda_die = pi_s * l0 * pi_t
    
    # Package contribution
    l_b = DISCRETE_PACKAGE_PARAMS.get(package, 1.0)
    lambda_pkg = 2.75e-3 * pi_n(n_cycles) * (delta_t ** 0.68) * l_b
    
    # Overstress contribution (default values)
    lambda_eos = 40
    
    return (lambda_die + lambda_pkg + lambda_eos) * 1e-9


def lambda_diode(t_junction: float = 85.0, diode_type: str = "signal",
                 package: str = "SOD-123", n_cycles: int = 5256,
                 delta_t: float = 3.0) -> float:
    """Calculate diode failure rate."""
    pi_t = math.exp(4640 * ((1/313) - (1/(273 + t_junction))))
    l0 = DIODE_BASE_RATES.get(diode_type.lower(), 0.1)
    lambda_die = l0 * pi_t
    
    l_b = DISCRETE_PACKAGE_PARAMS.get(package, 1.0)
    lambda_pkg = 2.75e-3 * pi_n(n_cycles) * (delta_t ** 0.68) * l_b
    
    lambda_eos = 40
    
    return (lambda_die + lambda_pkg + lambda_eos) * 1e-9


def lambda_ic(t_junction: float = 85.0, ic_type: str = None,
              package: str = "TQFP-48", construction_year: int = 2020,
              n_cycles: int = 5256, delta_t: float = 3.0) -> float:
    """Calculate integrated circuit failure rate."""
    # Default IC type if not specified
    if not ic_type or ic_type not in IC_DIE_PARAMS:
        ic_type = "MOS Standard, Digital circuits, 20000 transistors"
    
    die_params = IC_DIE_PARAMS.get(ic_type)
    if not die_params:
        return 50e-9  # Default for unknown
    
    l1, l2, n = die_params["l1"], die_params["l2"], die_params["n"]
    
    is_bipolar = "Bipolar" in ic_type or "high voltage" in ic_type
    ea = 4640 if is_bipolar else 3480
    
    # Die contribution
    year_factor = math.exp(-0.35 * (construction_year - 1998))
    pi_t = math.exp(ea * ((1/328) - (1/(273 + t_junction))))
    lambda_die = (l1 * n * year_factor + l2) * pi_t
    
    # Package contribution  
    l3 = IC_PACKAGE_PARAMS.get(package, 4.0)
    # Thermal expansion mismatch (Epoxy on FR4)
    pi_alpha = 0.06 * (abs(16 - 21.5) ** 1.68)
    lambda_pkg = 2.75e-3 * pi_alpha * pi_n(n_cycles) * (delta_t ** 0.68) * l3
    
    lambda_base = 40
    
    return (lambda_die + lambda_pkg + lambda_base) * 1e-9


def lambda_inductor(t_ambient: float = 25.0, power_loss: float = 0.1,
                    surface_area: float = 100.0, inductor_type: str = "power",
                    n_cycles: int = 5256, delta_t: float = 3.0) -> float:
    """Calculate inductor failure rate."""
    l0_map = {"fixed": 0.2, "variable": 0.4, "power": 0.6}
    l0 = l0_map.get(inductor_type.lower(), 0.6)
    
    t_rise = 8.2 * (power_loss / max(surface_area, 1.0))
    t_op = t_ambient + t_rise
    pi_t = math.exp(1740 * (1/303 - 1/(t_op + 273)))
    pi_cyc = pi_n(n_cycles) * (delta_t ** 0.68)
    
    return l0 * (pi_t + 7e-3 * pi_cyc) * 1e-9


def lambda_converter(power_rating: float = 5.0, n_cycles: int = 5256,
                     delta_t: float = 3.0) -> float:
    """Calculate DC-DC converter failure rate."""
    l0 = 100 if power_rating < 10 else 130
    pi_cyc = pi_n(n_cycles) * (delta_t ** 0.68)
    return l0 * (1 + 3e-3 * pi_cyc) * 1e-9


def lambda_battery() -> float:
    """Calculate primary battery failure rate."""
    return 20e-9


def lambda_connector(n_pins: int = 10) -> float:
    """Calculate connector failure rate."""
    return 0.01 * n_pins * 1e-9


def lambda_crystal() -> float:
    """Calculate crystal/oscillator failure rate."""
    return 5e-9


# =============================================================================
# System Reliability Calculations
# =============================================================================

def reliability(lambda_val: float, mission_hours: float) -> float:
    """Calculate reliability from failure rate."""
    return math.exp(-lambda_val * mission_hours)


def lambda_from_reliability(r: float, mission_hours: float) -> float:
    """Calculate equivalent failure rate from reliability."""
    if r <= 0:
        return float('inf')
    if r >= 1:
        return 0.0
    return -math.log(r) / mission_hours


def r_series(r_list: List[float]) -> float:
    """Series reliability (all must work)."""
    result = 1.0
    for r in r_list:
        result *= r
    return result


def r_parallel(r_list: List[float]) -> float:
    """Parallel reliability (at least one must work)."""
    p_fail = 1.0
    for r in r_list:
        p_fail *= (1 - r)
    return 1.0 - p_fail


def r_k_of_n(r_list: List[float], k: int) -> float:
    """K-of-N redundancy reliability."""
    n = len(r_list)
    if k > n or k < 1:
        return 0.0
    if k == 1:
        return r_parallel(r_list)
    if k == n:
        return r_series(r_list)
    
    # 2-of-3 special case (common)
    if n == 3 and k == 2:
        ra, rb, rc = r_list
        return ra*rb*rc + ra*rb*(1-rc) + ra*(1-rb)*rc + (1-ra)*rb*rc
    
    # General case via recursion
    r_n = r_list[-1]
    r_rest = r_list[:-1]
    return r_n * r_k_of_n(r_rest, k-1) + (1-r_n) * r_k_of_n(r_rest, k)


# =============================================================================
# Component Classification
# =============================================================================

COMPONENT_CLASSES = [
    "Resistor",
    "Ceramic Capacitor", 
    "Tantalum Capacitor",
    "Electrolytic Capacitor",
    "Low Power Transistor",
    "Power Transistor",
    "Low Power Diode",
    "Power Diode",
    "Integrated Circuit",
    "Inductor",
    "Transformer",
    "DC-DC Converter",
    "LDO Regulator",
    "Crystal/Oscillator",
    "Connector",
    "Primary Battery",
    "Relay",
]


def calculate_lambda(component_class: str, params: Dict[str, Any] = None) -> float:
    """
    Calculate failure rate for a component.
    
    Args:
        component_class: Component type string
        params: Optional parameters dict
    
    Returns:
        Failure rate in failures/hour
    """
    if params is None:
        params = {}

    # ECSS-style path: if ECSS category is provided, use centralized ECSS math
    if params.get("ecss_category"):
        cp = ComponentParams(
            category=params.get("ecss_category"),
            subtype=params.get("ecss_subtype", "default"),
            quality=params.get("ecss_quality", "B"),
            environment=params.get("ecss_environment", "GB"),
            stress_ratio=params.get("ecss_stress_ratio", 0.5),
            temperature=params.get("ecss_temperature", params.get("t_ambient", 25.0)),
            mission_time_hours=params.get("mission_hours", 1.0),
            quantity=params.get("ecss_quantity", params.get("quantity", 1)),
            extra=params.get("ecss_extra", {}),
        )
        return ecss_component_failure_rate(cp)

    cls = component_class.lower()
    n_cycles = params.get("n_cycles", 5256)
    delta_t = params.get("delta_t", 3.0)
    
    if "resistor" in cls:
        return lambda_resistor(
            params.get("t_ambient", 25),
            params.get("operating_power", 0.01),
            params.get("rated_power", 0.125),
            n_cycles, delta_t
        )
    
    if "ceramic" in cls and "capacitor" in cls:
        return lambda_capacitor(params.get("t_ambient", 25), "ceramic", n_cycles, delta_t)
    
    if "tantalum" in cls or "electrolytic" in cls:
        return lambda_capacitor(params.get("t_ambient", 25), "tantalum", n_cycles, delta_t)
    
    if "transistor" in cls:
        power = "high" if "power" in cls else "low"
        return lambda_transistor(
            params.get("t_junction", 85),
            params.get("transistor_type", "MOS"),
            power,
            params.get("package", "SOT-23"),
            params.get("stress_ratio", 0.5),
            n_cycles, delta_t
        )
    
    if "diode" in cls:
        return lambda_diode(
            params.get("t_junction", 85),
            params.get("diode_type", "signal"),
            params.get("package", "SOD-123"),
            n_cycles, delta_t
        )
    
    if "integrated circuit" in cls or cls in ("ic", "mcu", "microcontroller", "fpga"):
        return lambda_ic(
            params.get("t_junction", 85),
            params.get("ic_type"),
            params.get("package", "TQFP-48"),
            params.get("construction_year", 2020),
            n_cycles, delta_t
        )
    
    if "inductor" in cls:
        return lambda_inductor(
            params.get("t_ambient", 25),
            params.get("power_loss", 0.1),
            params.get("surface_area", 100),
            params.get("inductor_type", "power"),
            n_cycles, delta_t
        )
    
    if "transformer" in cls:
        return lambda_inductor(
            params.get("t_ambient", 25),
            params.get("power_loss", 0.5),
            params.get("surface_area", 200),
            "power", n_cycles, delta_t
        ) * 2  # Transformers have higher base rate
    
    if "converter" in cls or "dc-dc" in cls or "buck" in cls or "boost" in cls:
        return lambda_converter(params.get("power_rating", 5), n_cycles, delta_t)
    
    if "ldo" in cls or "regulator" in cls:
        return lambda_ic(
            params.get("t_junction", 100),
            "BICMOS, Linear/Digital low voltage, 20 transistors",
            params.get("package", "SOT-223"),
            2020, n_cycles, delta_t
        )
    
    if "crystal" in cls or "oscillator" in cls:
        return lambda_crystal()
    
    if "connector" in cls:
        return lambda_connector(params.get("n_pins", 10))
    
    if "battery" in cls:
        return lambda_battery()
    
    if "relay" in cls:
        return 100e-9  # Default relay failure rate
    
    # Default for unknown components
    return 10e-9
