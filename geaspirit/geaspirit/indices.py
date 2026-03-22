"""Mineral index computation from Sentinel-2 bands."""
import numpy as np


def compute_ratio_index(band_num, band_den, nodata=-9999):
    """Compute band ratio index, handling zeros and nodata."""
    mask = (band_den != 0) & (band_num != nodata) & (band_den != nodata)
    result = np.full_like(band_num, np.nan, dtype=np.float32)
    result[mask] = band_num[mask].astype(np.float32) / band_den[mask].astype(np.float32)
    return result


def iron_oxide(b4, b2):
    """Iron Oxide Index = B4/B2. High values indicate ferric iron (gossans, laterites)."""
    return compute_ratio_index(b4, b2)


def clay_hydroxyl(b11, b12):
    """Clay/Hydroxyl Index = B11/B12. High values indicate clay minerals (alteration zones)."""
    return compute_ratio_index(b11, b12)


def ferrous_iron(b11, b8a):
    """Ferrous Iron Index = B11/B8A. Indicates ferrous iron minerals."""
    return compute_ratio_index(b11, b8a)


def laterite(b4, b3):
    """Laterite Index = B4/B3. Indicates lateritic weathering."""
    return compute_ratio_index(b4, b3)


def ndvi(b8, b4):
    """NDVI = (B8-B4)/(B8+B4). For vegetation masking."""
    denom = b8.astype(np.float32) + b4.astype(np.float32)
    mask = denom != 0
    result = np.full_like(b8, np.nan, dtype=np.float32)
    result[mask] = (b8[mask].astype(np.float32) - b4[mask].astype(np.float32)) / denom[mask]
    return result
