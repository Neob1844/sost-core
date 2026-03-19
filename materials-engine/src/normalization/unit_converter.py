"""Unit conversions for materials science quantities."""


def ev_to_j(ev: float) -> float:
    return ev * 1.602176634e-19

def j_to_ev(j: float) -> float:
    return j / 1.602176634e-19

def ev_to_kj_per_mol(ev: float) -> float:
    return ev * 96.485

def kj_per_mol_to_ev(kj: float) -> float:
    return kj / 96.485

def gpa_to_bar(gpa: float) -> float:
    return gpa * 10000.0

def bar_to_gpa(bar: float) -> float:
    return bar / 10000.0

def angstrom_to_nm(a: float) -> float:
    return a * 0.1

def nm_to_angstrom(nm: float) -> float:
    return nm * 10.0

def angstrom_to_pm(a: float) -> float:
    return a * 100.0

def kelvin_to_celsius(k: float) -> float:
    return k - 273.15

def celsius_to_kelvin(c: float) -> float:
    return c + 273.15
