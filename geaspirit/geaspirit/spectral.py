"""Spectral library parsing and matching for Geaspirit Platform."""
import os
import csv
import numpy as np
from pathlib import Path


# Sentinel-2 band centers (nm)
S2_BAND_CENTERS = {
    "B2": 490, "B3": 560, "B4": 665, "B5": 705, "B6": 740,
    "B7": 783, "B8": 842, "B8A": 865, "B11": 1610, "B12": 2190,
}


def resample_spectrum(wavelengths, reflectance, target_centers, bandwidth=20):
    """Resample high-res spectrum to target band centers by averaging within bandwidth."""
    wl = np.array(wavelengths, dtype=float)
    rf = np.array(reflectance, dtype=float)
    resampled = {}
    for band, center in target_centers.items():
        mask = (wl >= center - bandwidth) & (wl <= center + bandwidth)
        if mask.any():
            resampled[band] = float(np.nanmean(rf[mask]))
        else:
            resampled[band] = float('nan')
    return resampled


def spectral_angle(spec_a, spec_b):
    """Spectral Angle Mapper (SAM) — angle between two spectral vectors.

    Returns angle in degrees. Lower = more similar. 0 = identical.
    """
    a = np.array(list(spec_a.values()), dtype=float)
    b = np.array(list(spec_b.values()), dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    if mask.sum() < 2:
        return 90.0
    a, b = a[mask], b[mask]
    cos_angle = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10)
    cos_angle = np.clip(cos_angle, -1, 1)
    return float(np.degrees(np.arccos(cos_angle)))


def parse_usgs_ascii(filepath):
    """Parse a USGS Spectral Library v7 ASCII spectrum file.

    Returns (mineral_name, wavelengths_nm, reflectance).
    """
    wavelengths = []
    reflectance = []
    name = os.path.splitext(os.path.basename(filepath))[0]
    try:
        with open(filepath, 'r', errors='replace') as f:
            header_done = False
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    if 'Name' in line:
                        name = line.split(':', 1)[-1].strip()
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        wl = float(parts[0])
                        rf = float(parts[1])
                        if 0.2 <= wl <= 25:  # microns range
                            wavelengths.append(wl * 1000)  # convert to nm
                            reflectance.append(rf)
                        elif 200 <= wl <= 25000:  # already in nm
                            wavelengths.append(wl)
                            reflectance.append(rf)
                    except ValueError:
                        continue
    except Exception:
        pass
    return name, wavelengths, reflectance
