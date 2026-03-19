"""Material DNA — canonical schema for the SOST Materials Discovery Engine.

This is the Phase I data contract. All fields are documented as:
  [C] = Canonical (core identity, always present)
  [D] = Derived (computed from canonical fields)
  [O] = Optional (may be absent depending on source)
  [P] = Provisional (may change in Phase II)

Phase I status: STABLE CONTRACT
"""

import hashlib
import json
import math
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional

log = logging.getLogger(__name__)

NORMALIZER_VERSION = "1.0.0"


@dataclass
class Material:
    # --- [C] Identity (canonical, source-independent) ---
    canonical_id: str = ""          # SHA256(formula|spacegroup)[:16], source-independent
    source: str = ""                # [C] "materials_project", "aflow", "cod", "jarvis"
    source_id: str = ""             # [C] ID in the source database

    # --- [C] Chemical identity ---
    formula: str = ""               # [C] Reduced chemical formula (e.g., "Fe2O3")
    formula_pretty: str = ""        # [O] Human-readable name
    elements: List[str] = field(default_factory=list)  # [D] Sorted element symbols
    n_elements: int = 0             # [D] len(elements)

    # --- [O] Crystal structure ---
    spacegroup: Optional[int] = None         # [O] Space group number (1-230)
    spacegroup_symbol: Optional[str] = None  # [O] e.g., "Fm-3m"
    crystal_system: Optional[str] = None     # [O] cubic, hexagonal, etc.
    lattice_params: Optional[dict] = None    # [O] {a,b,c,alpha,beta,gamma} Å/deg
    nsites: Optional[int] = None             # [O] Number of sites in unit cell

    # --- [O] Structure data ---
    structure_ref: Optional[str] = None       # [O] URL or path to CIF/POSCAR
    structure_format: Optional[str] = None    # [O] "cif", "poscar", "json", None
    structure_data: Optional[str] = None      # [O] Raw CIF/structure text (if stored inline)
    structure_sha256: Optional[str] = None    # [D] SHA256 of structure_data
    has_valid_structure: Optional[bool] = None # [D] True if structure parses correctly

    # --- [O] Electronic properties ---
    band_gap: Optional[float] = None          # [O] eV
    band_gap_direct: Optional[bool] = None    # [O]

    # --- [O] Thermodynamic properties ---
    formation_energy: Optional[float] = None  # [O] eV/atom
    energy_above_hull: Optional[float] = None # [O] eV/atom

    # --- [O] Mechanical properties ---
    bulk_modulus: Optional[float] = None      # [O] GPa
    shear_modulus: Optional[float] = None     # [O] GPa

    # --- [O] Magnetic properties ---
    total_magnetization: Optional[float] = None  # [O] μB

    # --- [C] Provenance ---
    raw_payload_sha256: Optional[str] = None  # [C] SHA256 of raw JSON from source
    source_url: Optional[str] = None          # [C] URL used to fetch this record
    ingested_at: Optional[str] = None         # [C] ISO timestamp
    normalized_at: Optional[str] = None       # [C] ISO timestamp
    normalizer_version: str = NORMALIZER_VERSION  # [C]

    # --- [O] Metadata ---
    confidence: float = 0.0                   # [O] 0.0-1.0
    applications: List[str] = field(default_factory=list)  # [P]
    formula_parse_method: Optional[str] = None  # [D] "pymatgen" or "regex_fallback"

    # --- [P] Phase II stubs ---
    embedding: Optional[List[float]] = None   # [P] Vector embedding (Phase II)

    def compute_canonical_id(self) -> str:
        """Deterministic hash from formula + spacegroup. Source-independent."""
        key = f"{self.formula}|{self.spacegroup or 0}"
        self.canonical_id = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.canonical_id

    def canonical_json(self) -> str:
        """Stable JSON for hashing/manifests. Sorted keys, no spaces."""
        d = self.to_dict()
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    def validate(self) -> List[str]:
        """Returns list of validation errors. Empty = valid."""
        errors = []
        if not self.source:
            errors.append("source is required")
        if not self.formula:
            errors.append("formula is empty")
        if self.confidence < 0.0 or self.confidence > 1.0:
            errors.append(f"confidence {self.confidence} not in [0,1]")
        if self.elements and self.n_elements != len(self.elements):
            errors.append(f"n_elements ({self.n_elements}) != len(elements) ({len(self.elements)})")
        if self.embedding is not None:
            if not isinstance(self.embedding, list):
                errors.append("embedding must be list or None")
            elif not all(isinstance(x, (int, float)) for x in self.embedding):
                errors.append("embedding contains non-numeric values")
        if self.spacegroup is not None and (self.spacegroup < 1 or self.spacegroup > 230):
            errors.append(f"spacegroup {self.spacegroup} not in [1,230]")
        return errors

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> "Material":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "Material":
        return cls.from_dict(json.loads(s))

    def similarity(self, other: "Material") -> float:
        """Cosine similarity between embeddings."""
        if not self.embedding or not other.embedding:
            return 0.0
        a, b = self.embedding, other.embedding
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
