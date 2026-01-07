"""
Reliability Core - Backward Compatibility Module

This module provides backward compatibility with older imports.
All actual calculations are now in reliability_math.py.
"""

# Re-export everything from reliability_math for backward compatibility
from .reliability_math import (
    # Core calculation functions
    calculate_lambda,
    calculate_component_lambda,
    reliability_from_lambda,
    lambda_from_reliability,
    mttf_from_lambda,
    
    # System reliability
    r_series,
    r_parallel,
    r_k_of_n,
    lambda_series,
    
    # Pi factors
    pi_thermal_cycles,
    pi_temperature,
    pi_alpha,
    
    # Lookup tables
    IC_DIE_TABLE,
    IC_TYPE_CHOICES,
    IC_PACKAGE_TABLE,
    IC_PACKAGE_CHOICES,
    DISCRETE_PACKAGE_TABLE,
    DIODE_BASE_RATES,
    TRANSISTOR_BASE_RATES,
    CAPACITOR_PARAMS,
    RESISTOR_PARAMS,
    INDUCTOR_PARAMS,
    MISC_COMPONENT_RATES,
    THERMAL_EXPANSION_SUBSTRATE,
    INTERFACE_EOS_VALUES,
    
    # Field definitions
    get_component_types,
    get_field_definitions,
    
    # Classes
    ConnectionType,
    ComponentParams,
    ActivationEnergy,
    
    # Legacy functions
    component_failure_rate,
    ecss_component_failure_rate,
)

# Alias
reliability = reliability_from_lambda


# Component classes for backward compatibility
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
