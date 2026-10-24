"""Reference values for the Bar30 (MS5837-30BA) depth / pressure calculation.

Set in the CONNECT VEHICLE dialog (and saved with each vehicle profile), editable
during a session from the console's File > Reference Values... dialog. The console
sends them to the Pi (see the reference packet in link.py), which passes them on to
the STM32 that reads the Bar30.

    surface_hpa   surface barometric pressure reference, always held in hPa (= mbar)
    unit          how the operator likes to see it: "hPa", "kPa" or "mbar" (display only)
    density       water density, kg/m^3 (1000 fresh water, ~1025 sea water)
    second_order  Bar30 second-order pressure calibration for water below 20 C
"""

from dataclasses import dataclass

from command_center_py.config import SECOND_ORDER_CAL, SURFACE_PRESSURE_HPA, WATER_DENSITY

UNITS = ("hPa", "kPa", "mbar")
SURFACE_RANGE_HPA = (800.0, 1100.0)     # sanity limits for the surface pressure
DENSITY_RANGE = (900.0, 1100.0)         # sanity limits for the water density, kg/m^3
RANGE_ERROR = "Surface pressure must be 800–1100 hPa (80–110 kPa) and water density 900–1100 kg/m³"


def to_hpa(value, unit):
    return value * 10.0 if unit == "kPa" else value       # hPa and mbar are the same size


def from_hpa(hpa, unit):
    return hpa / 10.0 if unit == "kPa" else hpa


def format_surface(hpa, unit):
    """Surface pressure as text in the chosen unit, e.g. '1013.25' (hPa) or '101.325' (kPa)."""
    v = from_hpa(hpa, unit)
    return f"{v:.3f}".rstrip("0").rstrip(".") if unit == "kPa" else f"{v:.2f}".rstrip("0").rstrip(".")


def format_density(density):
    return f"{density:.1f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class RefValues:
    surface_hpa: float = SURFACE_PRESSURE_HPA
    unit: str = "hPa"
    density: float = WATER_DENSITY
    second_order: bool = SECOND_ORDER_CAL

    def summary(self):
        return (f"{format_surface(self.surface_hpa, self.unit)} {self.unit} · "
                f"{format_density(self.density)} kg/m³ · 2nd-order {'ON' if self.second_order else 'OFF'}")

    def to_profile(self):
        return {"surface_pressure_hpa": self.surface_hpa, "surface_unit": self.unit,
                "water_density": self.density, "second_order": self.second_order}


def parse(surface_text, unit, density_text, second_order):
    """Validate the dialog's text fields. Returns (RefValues, None) or (None, error message)."""
    try:
        hpa = to_hpa(float(surface_text), unit)
        density = float(density_text)
    except (TypeError, ValueError):
        return None, RANGE_ERROR
    if not (SURFACE_RANGE_HPA[0] <= hpa <= SURFACE_RANGE_HPA[1]
            and DENSITY_RANGE[0] <= density <= DENSITY_RANGE[1]):
        return None, RANGE_ERROR
    return RefValues(hpa, unit if unit in UNITS else "hPa", density, bool(second_order)), None


def from_profile(data):
    """RefValues from a saved profile dict; missing or bad keys fall back to the defaults."""
    d = RefValues()
    try:
        hpa = float(data.get("surface_pressure_hpa", d.surface_hpa))
        density = float(data.get("water_density", d.density))
    except (TypeError, ValueError):
        return d
    unit = data.get("surface_unit", d.unit)
    r, err = parse(format_surface(hpa, "hPa"), "hPa", format_density(density),
                   data.get("second_order", d.second_order))
    if err:
        return d
    return RefValues(r.surface_hpa, unit if unit in UNITS else "hPa", r.density, r.second_order)
