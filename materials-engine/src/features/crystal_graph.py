"""Crystal graph featurization for GNN models.

Converts pymatgen Structure → graph with atom features + bond features.
Used by CGCNN-style models.
"""

import logging
import numpy as np
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# Atom features: one-hot encoding of common elements (first 94)
ELEM_LIST = [
    'H','He','Li','Be','B','C','N','O','F','Ne','Na','Mg','Al','Si','P','S',
    'Cl','Ar','K','Ca','Sc','Ti','V','Cr','Mn','Fe','Co','Ni','Cu','Zn',
    'Ga','Ge','As','Se','Br','Kr','Rb','Sr','Y','Zr','Nb','Mo','Tc','Ru',
    'Rh','Pd','Ag','Cd','In','Sn','Sb','Te','I','Xe','Cs','Ba','La','Ce',
    'Pr','Nd','Pm','Sm','Eu','Gd','Tb','Dy','Ho','Er','Tm','Yb','Lu','Hf',
    'Ta','W','Re','Os','Ir','Pt','Au','Hg','Tl','Pb','Bi','Po','At','Rn',
    'Fr','Ra','Ac','Th','Pa','U','Np','Pu'
]
ELEM_TO_IDX = {e: i for i, e in enumerate(ELEM_LIST)}
N_ELEM = len(ELEM_LIST)


def structure_to_graph(structure, radius: float = 8.0, max_neighbors: int = 12
                       ) -> Optional[dict]:
    """Convert pymatgen Structure to a graph dict.

    Returns dict with:
      atom_features: (N, N_ELEM) one-hot
      bond_distances: (N, max_neighbors) distances in Angstrom
      neighbor_indices: (N, max_neighbors) neighbor atom indices
      n_atoms: int
    """
    try:
        n_atoms = len(structure)
        if n_atoms == 0:
            return None

        # Atom features: one-hot element encoding
        atom_feats = np.zeros((n_atoms, N_ELEM), dtype=np.float32)
        for i, site in enumerate(structure):
            elem = str(site.specie)
            idx = ELEM_TO_IDX.get(elem, -1)
            if idx >= 0:
                atom_feats[i, idx] = 1.0

        # Bond features: distances to nearest neighbors
        all_neighbors = structure.get_all_neighbors(radius, include_index=True)
        bond_dists = np.zeros((n_atoms, max_neighbors), dtype=np.float32)
        nbr_indices = np.zeros((n_atoms, max_neighbors), dtype=np.int64)

        for i, neighbors in enumerate(all_neighbors):
            if not neighbors:
                continue
            # Sort by distance
            sorted_nbrs = sorted(neighbors, key=lambda x: x[1])[:max_neighbors]
            for j, nbr in enumerate(sorted_nbrs):
                bond_dists[i, j] = nbr[1]  # distance
                nbr_indices[i, j] = nbr[2]  # neighbor index

        return {
            "atom_features": atom_feats,
            "bond_distances": bond_dists,
            "neighbor_indices": nbr_indices,
            "n_atoms": n_atoms,
        }
    except Exception as e:
        log.debug("Graph conversion failed: %s", e)
        return None


def composition_fingerprint(elements: list, n_dim: int = N_ELEM) -> np.ndarray:
    """Simple composition-based fingerprint for similarity search.

    Returns normalized element frequency vector.
    """
    fp = np.zeros(n_dim, dtype=np.float32)
    for elem in elements:
        idx = ELEM_TO_IDX.get(elem, -1)
        if idx >= 0:
            fp[idx] += 1.0
    total = fp.sum()
    if total > 0:
        fp /= total
    return fp
