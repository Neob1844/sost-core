"""FastAPI server for the Materials Discovery Engine.

Phase II.8: Baseline ML prediction + Thermo-Pressure scaffold.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional, List

import yaml
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel

from ..storage.db import MaterialsDB

log = logging.getLogger(__name__)

_db: Optional[MaterialsDB] = None


def _get_db() -> MaterialsDB:
    global _db
    if _db is None:
        cfg_path = os.environ.get("ME_CONFIG", "config.yaml")
        try:
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f)
            db_path = cfg.get("storage", {}).get("db_path", "materials.db")
        except FileNotFoundError:
            db_path = "materials.db"
        _db = MaterialsDB(db_path)
    return _db


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Materials Engine API starting")
    _get_db()
    yield
    log.info("Materials Engine API shutting down")


app = FastAPI(
    title="SOST Materials Discovery Engine",
    version="1.4.0",
    description="Phase IV.A: Scaled Retraining Ladder (Formation Energy).",
    lifespan=lifespan,
)


# --- Response models ---

class MaterialResponse(BaseModel):
    canonical_id: str = ""
    source: str = ""
    source_id: str = ""
    formula: str = ""
    elements: List[str] = []
    n_elements: int = 0
    spacegroup: Optional[int] = None
    crystal_system: Optional[str] = None
    band_gap: Optional[float] = None
    formation_energy: Optional[float] = None
    bulk_modulus: Optional[float] = None
    confidence: float = 0.0

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel):
    total: int
    limit: int
    offset: int
    data: list


class StatsResponse(BaseModel):
    total: int
    by_source: dict
    by_crystal_system: dict


class StubResponse(BaseModel):
    status: str = "not_implemented"
    message: str
    phase: str


# --- Endpoints ---

@app.get("/status")
def status():
    db = _get_db()
    return {"status": "ok", "version": "2.7.0", "phase": "hierarchical_bandgap",
            "materials_count": db.count()}


@app.get("/stats", response_model=StatsResponse)
def stats():
    return _get_db().stats()


@app.get("/materials", response_model=PaginatedResponse)
def list_materials(limit: int = Query(20, ge=1, le=100),
                   offset: int = Query(0, ge=0)):
    db = _get_db()
    materials = db.list_materials(limit=limit, offset=offset)
    return {"total": db.count(), "limit": limit, "offset": offset,
            "data": [m.to_dict() for m in materials]}


@app.get("/materials/{material_id}")
def get_material(material_id: str):
    m = _get_db().get_material(material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    return m.to_dict()


@app.get("/search", response_model=PaginatedResponse)
def search(
    formula: Optional[str] = None,
    elements: Optional[str] = Query(None, description="Comma-separated, e.g. Fe,O"),
    band_gap_min: Optional[float] = None,
    band_gap_max: Optional[float] = None,
    formation_energy_min: Optional[float] = None,
    formation_energy_max: Optional[float] = None,
    bulk_modulus_min: Optional[float] = None,
    bulk_modulus_max: Optional[float] = None,
    source: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # Validate min <= max
    for name, mn, mx in [("band_gap", band_gap_min, band_gap_max),
                          ("formation_energy", formation_energy_min, formation_energy_max),
                          ("bulk_modulus", bulk_modulus_min, bulk_modulus_max)]:
        if mn is not None and mx is not None and mn > mx:
            raise HTTPException(400, f"{name}_min ({mn}) > {name}_max ({mx})")

    el_list = [e.strip() for e in elements.split(",") if e.strip()] if elements else None
    results = _get_db().search_materials(
        formula=formula, elements=el_list,
        band_gap_min=band_gap_min, band_gap_max=band_gap_max,
        formation_energy_min=formation_energy_min, formation_energy_max=formation_energy_max,
        bulk_modulus_min=bulk_modulus_min, bulk_modulus_max=bulk_modulus_max,
        source=source, limit=limit, offset=offset)
    return {"total": len(results), "limit": limit, "offset": offset,
            "data": [m.to_dict() for m in results]}


class PredictRequest(BaseModel):
    cif: str
    target: str = "band_gap"
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None


@app.post("/predict")
def predict(req: PredictRequest):
    """Predict material property from CIF structure using trained GNN model.

    Optionally accepts temperature_K and pressure_GPa for thermo-pressure
    screening context. If provided, the response includes T/P annotation
    and screening metadata. Real T/P conditioning is Phase III+.
    """
    from ..inference.predictor import predict_from_cif

    # Base prediction
    result = predict_from_cif(req.cif, req.target)
    if "error" in result:
        raise HTTPException(400 if "Invalid" in result["error"] else 404, result["error"])

    # If T/P conditions provided, annotate with screening context
    if req.temperature_K is not None or req.pressure_GPa is not None:
        from ..thermo.conditions import (
            ThermoPressureConditions, ConditionValidationError,
            AMBIENT_TEMPERATURE_K, AMBIENT_PRESSURE_GPA)
        from ..thermo.screening import screen_material

        try:
            conditions = ThermoPressureConditions(
                temperature_K=req.temperature_K or AMBIENT_TEMPERATURE_K,
                pressure_GPa=req.pressure_GPa or AMBIENT_PRESSURE_GPA)
            conditions.validate()
        except ConditionValidationError as e:
            raise HTTPException(400, f"Invalid conditions: {e}")

        screening = screen_material(result, conditions)
        result["screening"] = screening.to_dict()

    return result


@app.get("/similar/{material_id}")
def similar(material_id: str, top_k: int = Query(5, ge=1, le=20)):
    """Find similar materials by composition fingerprint."""
    from ..inference.predictor import find_similar
    db = _get_db()
    results = find_similar(material_id, db, top_k=top_k)
    if not results:
        raise HTTPException(404, "Material not found or no similar materials")
    return {"query": material_id, "method": "composition_fingerprint", "results": results}


@app.get("/audit/summary")
def audit_summary():
    """Corpus audit summary with coverage metrics."""
    db = _get_db()
    return db.audit_counts()


@app.get("/materials/{material_id}/structure-status")
def structure_status(material_id: str):
    m = _get_db().get_material(material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    return {
        "canonical_id": m.canonical_id,
        "has_valid_structure": m.has_valid_structure,
        "structure_format": m.structure_format,
        "structure_ref": m.structure_ref,
        "structure_sha256": m.structure_sha256,
    }


# --- Novelty / Exotic endpoints ---

class NoveltyCheckRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None
    lattice_params: Optional[dict] = None
    nsites: Optional[int] = None
    band_gap: Optional[float] = None
    formation_energy: Optional[float] = None


class ExoticRankRequest(BaseModel):
    top_k: int = 20


@app.get("/novelty/{material_id}")
def get_novelty(material_id: str):
    """Assess novelty of a corpus material relative to the rest of the corpus.

    Returns novelty score, band, nearest neighbor, and reason codes.
    NOTE: Novelty is relative to the current ingested corpus only,
    not to all scientific literature.
    """
    from ..novelty.filter import NoveltyFilter
    db = _get_db()
    m = db.get_material(material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    nf = NoveltyFilter(db)
    novelty, exotic = nf.check_exotic(m)
    return {
        "canonical_id": material_id,
        "formula": m.formula,
        "novelty": novelty.to_dict(),
        "exotic": exotic.to_dict(),
        "disclaimer": "Novelty is relative to the current ingested corpus only.",
    }


@app.post("/novelty/check")
def check_novelty(req: NoveltyCheckRequest):
    """Check novelty of an arbitrary material (not necessarily in corpus).

    Provide formula, elements, and optional structural parameters.
    Returns novelty and exotic assessment against corpus.
    """
    from ..novelty.filter import NoveltyFilter
    db = _get_db()
    nf = NoveltyFilter(db)
    novelty = nf.check_novelty_from_params(
        formula=req.formula,
        elements=req.elements,
        spacegroup=req.spacegroup,
        lattice_params=req.lattice_params,
        nsites=req.nsites,
        band_gap=req.band_gap,
        formation_energy=req.formation_energy,
    )
    return {
        "formula": req.formula,
        "novelty": novelty.to_dict(),
        "disclaimer": "Novelty is relative to the current ingested corpus only.",
    }


@app.get("/candidates/exotic")
def exotic_candidates(top_k: int = Query(20, ge=1, le=100)):
    """Rank corpus materials by exotic score (rarest / least explored).

    "Exotic" means rare and unexplored in the corpus — NOT "better" or "useful".
    """
    from ..novelty.filter import NoveltyFilter
    db = _get_db()
    nf = NoveltyFilter(db)
    candidates = nf.rank_exotic(top_k=top_k)
    return {
        "top_k": top_k,
        "corpus_size": nf.corpus_size,
        "candidates": candidates,
        "scoring": {
            "method": "weighted_combination",
            "components": ["novelty_score", "element_rarity",
                           "structure_rarity", "neighbor_sparsity"],
            "note": "'Exotic' means rare/unexplored in corpus, not 'better'.",
        },
        "disclaimer": "All scores are relative to the current ingested corpus only.",
    }


@app.post("/candidates/exotic/rank")
def rank_exotic(req: ExoticRankRequest):
    """Rank corpus by exotic score with custom top_k."""
    from ..novelty.filter import NoveltyFilter
    db = _get_db()
    nf = NoveltyFilter(db)
    candidates = nf.rank_exotic(top_k=req.top_k)
    return {
        "top_k": req.top_k,
        "corpus_size": nf.corpus_size,
        "candidates": candidates,
        "disclaimer": "All scores are relative to the current ingested corpus only.",
    }


# --- Shortlist / Screening endpoints ---

class ShortlistBuildRequest(BaseModel):
    criteria: Optional[dict] = None
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None
    pool_limit: int = 5000


class TPScreeningRequest(BaseModel):
    material_id: str
    temperature_K: float = 300.0
    pressure_GPa: float = 0.000101325


class TPScreeningBatchRequest(BaseModel):
    material_ids: List[str]
    temperature_K: float = 300.0
    pressure_GPa: float = 0.000101325


@app.get("/shortlist/default-criteria")
def get_default_criteria():
    """Return default shortlist criteria with documentation."""
    from ..shortlist.criteria import default_criteria
    c = default_criteria()
    return {
        "criteria": c.to_dict(),
        "note": "Default criteria for general-purpose candidate selection. "
                "All weights and thresholds are configurable via POST /shortlist/build.",
    }


@app.post("/shortlist/build")
def build_shortlist(req: ShortlistBuildRequest):
    """Build a ranked shortlist from the corpus.

    Accepts optional criteria overrides and T/P conditions.
    Returns pool size, decisions summary, and ranked shortlist.
    """
    from ..shortlist.engine import ShortlistEngine
    from ..shortlist.criteria import ShortlistCriteria, CriteriaValidationError
    from ..thermo.conditions import (
        ThermoPressureConditions, ConditionValidationError,
        AMBIENT_TEMPERATURE_K, AMBIENT_PRESSURE_GPA)

    db = _get_db()
    engine = ShortlistEngine(db)

    # Parse criteria
    criteria = None
    if req.criteria:
        try:
            criteria = ShortlistCriteria.from_dict(req.criteria)
            criteria.validate()
        except (CriteriaValidationError, TypeError) as e:
            raise HTTPException(400, f"Invalid criteria: {e}")

    # Parse conditions
    conditions = None
    if req.temperature_K is not None or req.pressure_GPa is not None:
        try:
            conditions = ThermoPressureConditions(
                temperature_K=req.temperature_K or AMBIENT_TEMPERATURE_K,
                pressure_GPa=req.pressure_GPa or AMBIENT_PRESSURE_GPA)
            conditions.validate()
        except ConditionValidationError as e:
            raise HTTPException(400, f"Invalid conditions: {e}")

    result = engine.build(criteria=criteria, conditions=conditions,
                          pool_limit=req.pool_limit)
    return result


@app.post("/screening/thermo-pressure")
def screen_tp(req: TPScreeningRequest):
    """Screen a single corpus material under T/P conditions.

    Uses heuristic proxies — NOT physics simulation.
    Returns risk levels, stability flags, and honest method documentation.
    """
    from ..thermo.conditions import ThermoPressureConditions, ConditionValidationError
    from ..thermo.proxies import screen_tp_proxy

    db = _get_db()
    m = db.get_material(req.material_id)
    if not m:
        raise HTTPException(404, "Material not found")

    try:
        conditions = ThermoPressureConditions(
            temperature_K=req.temperature_K, pressure_GPa=req.pressure_GPa)
        conditions.validate()
    except ConditionValidationError as e:
        raise HTTPException(400, f"Invalid conditions: {e}")

    result = screen_tp_proxy(m, conditions)
    result["material_id"] = req.material_id
    result["formula"] = m.formula
    return result


@app.post("/screening/thermo-pressure/batch")
def screen_tp_batch(req: TPScreeningBatchRequest):
    """Screen multiple corpus materials under the same T/P conditions."""
    from ..thermo.conditions import ThermoPressureConditions, ConditionValidationError
    from ..thermo.proxies import screen_tp_proxy

    db = _get_db()
    try:
        conditions = ThermoPressureConditions(
            temperature_K=req.temperature_K, pressure_GPa=req.pressure_GPa)
        conditions.validate()
    except ConditionValidationError as e:
        raise HTTPException(400, f"Invalid conditions: {e}")

    results = []
    for mid in req.material_ids:
        m = db.get_material(mid)
        if m is None:
            results.append({"material_id": mid, "error": "not_found"})
            continue
        r = screen_tp_proxy(m, conditions)
        r["material_id"] = mid
        r["formula"] = m.formula
        results.append(r)

    return {
        "conditions": conditions.to_dict(),
        "results": results,
        "disclaimer": "Heuristic proxy screening — not physics simulation.",
    }


# --- Campaign / Retrieval endpoints ---

class CampaignRunRequest(BaseModel):
    name: str
    campaign_type: str = "custom"
    objective: str = ""
    criteria: Optional[dict] = None
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None
    top_k: int = 20
    pool_limit: int = 50000


class SimilarSearchRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None
    band_gap: Optional[float] = None
    formation_energy: Optional[float] = None
    top_k: int = 10


@app.get("/campaigns/presets")
def get_campaign_presets():
    """Return available campaign presets."""
    from ..campaigns.spec import ALL_PRESETS
    presets = {}
    for name, fn in ALL_PRESETS.items():
        spec = fn()
        presets[name] = spec.to_dict()
    return {"presets": presets}


@app.post("/campaigns/run")
def run_campaign(req: CampaignRunRequest):
    """Run a search campaign and return results."""
    from ..campaigns.spec import CampaignSpec, CampaignValidationError
    from ..campaigns.engine import CampaignEngine

    spec = CampaignSpec(
        name=req.name, campaign_type=req.campaign_type,
        objective=req.objective, criteria=req.criteria,
        temperature_K=req.temperature_K, pressure_GPa=req.pressure_GPa,
        top_k=req.top_k, pool_limit=req.pool_limit)
    try:
        spec.validate()
    except CampaignValidationError as e:
        raise HTTPException(400, str(e))

    db = _get_db()
    engine = CampaignEngine(db)
    result, _ = engine.run_and_save(spec)
    return result


@app.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str):
    """Retrieve a saved campaign run."""
    from ..campaigns.engine import CampaignEngine
    engine = CampaignEngine(_get_db())
    result = engine.get_run(campaign_id)
    if not result:
        raise HTTPException(404, "Campaign not found")
    return result


@app.get("/retrieval/status")
def retrieval_status():
    """Return retrieval index status."""
    from ..features.fingerprint_store import FingerprintStore
    from ..retrieval.index import RetrievalIndex
    store = FingerprintStore()
    if store.load():
        idx = RetrievalIndex(store)
        idx.build()
        return idx.status()
    return {"ready": False, "note": "Fingerprint store not built. Run corpus scaling first."}


@app.post("/similar/search")
def similar_search(req: SimilarSearchRequest):
    """Find similar materials by fingerprint. Works for materials not in corpus."""
    from ..features.fingerprint_store import FingerprintStore
    from ..retrieval.index import RetrievalIndex
    from ..novelty.fingerprint import combined_fingerprint

    store = FingerprintStore()
    if not store.load():
        raise HTTPException(503, "Fingerprint index not available. Build first.")

    idx = RetrievalIndex(store)
    idx.build()

    fp = combined_fingerprint(
        elements=req.elements, spacegroup=req.spacegroup,
        band_gap=req.band_gap, formation_energy=req.formation_energy)

    results = idx.search(fp, top_k=req.top_k)
    return {
        "query": {"formula": req.formula, "elements": req.elements},
        "results": [{"canonical_id": cid, "formula": f, "similarity": round(s, 4)}
                    for cid, f, s in results],
        "method": "cosine_similarity_104dim",
    }


# --- Generation endpoints ---

class GenerationRunRequest(BaseModel):
    strategy: str = "mixed"
    max_parents: int = 100
    max_candidates: int = 500
    random_seed: int = 42
    allowed_elements: Optional[List[str]] = None
    excluded_elements: Optional[List[str]] = None
    max_n_elements: int = 5
    novelty_threshold: float = 0.0
    formation_energy_max: Optional[float] = None
    band_gap_min: Optional[float] = None
    band_gap_max: Optional[float] = None
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None
    pool_limit: int = 5000


class GenerationCheckRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None


@app.get("/generation/presets")
def get_generation_presets():
    """Return available generation presets."""
    from ..generation.spec import ALL_GENERATION_PRESETS
    presets = {}
    for name, fn in ALL_GENERATION_PRESETS.items():
        presets[name] = fn().to_dict()
    return {"presets": presets}


@app.get("/generation/status")
def generation_status():
    """List recent generation runs."""
    from ..generation.engine import GenerationEngine
    engine = GenerationEngine(_get_db())
    return {"runs": engine.list_runs()}


@app.post("/generation/run")
def run_generation(req: GenerationRunRequest):
    """Run a candidate generation session."""
    from ..generation.spec import GenerationSpec, GenerationValidationError
    from ..generation.engine import GenerationEngine

    spec = GenerationSpec.from_dict(req.model_dump())
    try:
        spec.validate()
    except GenerationValidationError as e:
        raise HTTPException(400, str(e))

    db = _get_db()
    engine = GenerationEngine(db)
    result, _ = engine.run_and_save(spec)
    return result


@app.get("/generation/{run_id}")
def get_generation_run(run_id: str):
    """Retrieve a saved generation run."""
    from ..generation.engine import GenerationEngine
    engine = GenerationEngine(_get_db())
    result = engine.get_run(run_id)
    if not result:
        raise HTTPException(404, "Generation run not found")
    return result


@app.post("/generation/check")
def check_candidate(req: GenerationCheckRequest):
    """Check a manually-provided candidate against the corpus."""
    from ..generation.engine import GenerationEngine
    db = _get_db()
    engine = GenerationEngine(db)
    return engine.check_candidate(req.formula, req.elements, req.spacegroup)


# --- Evaluation endpoints ---

class EvaluateRunRequest(BaseModel):
    run_id: str
    weights: Optional[dict] = None
    band_gap_target: Optional[float] = None
    band_gap_tolerance: float = 2.0
    fe_max_for_stable: float = 0.5


class LiftCheckRequest(BaseModel):
    formula: str
    elements: List[str]
    parent_id: str
    generation_strategy: str = "element_substitution"
    spacegroup: Optional[int] = None


@app.post("/generation/evaluate-run")
def evaluate_generation_run(req: EvaluateRunRequest):
    """Evaluate candidates from a generation run: lift structures + predict properties."""
    from ..generation.evaluator import CandidateEvaluator
    evaluator = CandidateEvaluator(_get_db())
    result, _ = evaluator.evaluate_run_and_save(
        req.run_id, weights=req.weights,
        band_gap_target=req.band_gap_target,
        band_gap_tolerance=req.band_gap_tolerance,
        fe_max_for_stable=req.fe_max_for_stable)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/generation/evaluations/status")
def evaluations_status():
    """List saved evaluation runs."""
    from ..generation.evaluator import CandidateEvaluator
    evaluator = CandidateEvaluator(_get_db())
    return {"evaluations": evaluator.list_evaluations()}


@app.get("/generation/evaluation/{evaluation_id}")
def get_evaluation(evaluation_id: str):
    """Retrieve a saved evaluation run."""
    from ..generation.evaluator import CandidateEvaluator
    evaluator = CandidateEvaluator(_get_db())
    result = evaluator.get_evaluation(evaluation_id)
    if not result:
        raise HTTPException(404, "Evaluation not found")
    return result


@app.post("/generation/lift-check")
def lift_check(req: LiftCheckRequest):
    """Test structure lift for a specific candidate + parent combination."""
    from ..generation.evaluator import CandidateEvaluator
    evaluator = CandidateEvaluator(_get_db())
    return evaluator.lift_check(
        req.formula, req.elements, req.parent_id, req.generation_strategy)


# --- Intelligence endpoints ---

class IntelligenceReportRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None


class IntelligenceCompareRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None
    top_k: int = 5


@app.get("/intelligence/material/{material_id}")
def get_intelligence(material_id: str,
                     temperature_K: Optional[float] = None,
                     pressure_GPa: Optional[float] = None):
    """Generate a Material Intelligence Report for a corpus material."""
    from ..intelligence.report import generate_report
    from ..features.fingerprint_store import FingerprintStore
    db = _get_db()
    m = db.get_material(material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    store = FingerprintStore()
    if not store.load():
        store = None
    report = generate_report(
        formula=m.formula, elements=m.elements,
        spacegroup=m.spacegroup, material_id=material_id,
        db=db, store=store,
        temperature_K=temperature_K, pressure_GPa=pressure_GPa)
    return report


@app.post("/intelligence/report")
def intelligence_report(req: IntelligenceReportRequest):
    """Generate a Material Intelligence Report for any formula."""
    from ..intelligence.report import generate_report
    from ..features.fingerprint_store import FingerprintStore
    db = _get_db()
    store = FingerprintStore()
    if not store.load():
        store = None
    report = generate_report(
        formula=req.formula, elements=req.elements,
        spacegroup=req.spacegroup, db=db, store=store,
        temperature_K=req.temperature_K, pressure_GPa=req.pressure_GPa)
    return report


@app.post("/intelligence/compare")
def intelligence_compare(req: IntelligenceCompareRequest):
    """Compare a material against the corpus — returns comparison table."""
    from ..intelligence.comparison import build_comparison_table
    from ..features.fingerprint_store import FingerprintStore
    db = _get_db()
    store = FingerprintStore()
    if not store.load():
        store = None
    table = build_comparison_table(
        query_material=None, query_formula=req.formula,
        query_elements=req.elements, query_spacegroup=req.spacegroup,
        db=db, store=store, top_k=req.top_k)
    return {
        "query": {"formula": req.formula, "elements": req.elements},
        "comparison_table": table,
        "note": "Comparison against integrated corpus only.",
    }


# --- Dossier endpoints ---

class DossierFromEvalRequest(BaseModel):
    evaluation_id: str
    candidate_index: int = 0


@app.get("/intelligence/status")
def intelligence_status():
    """List saved dossiers."""
    from ..intelligence.dossier import list_dossiers
    return {"dossiers": list_dossiers()}


@app.post("/intelligence/dossier/from-evaluation")
def dossier_from_evaluation(req: DossierFromEvalRequest):
    """Build a validation dossier from an evaluated candidate."""
    from ..intelligence.dossier import build_dossier_from_evaluation, save_dossier
    from ..generation.evaluator import CandidateEvaluator
    from ..features.fingerprint_store import FingerprintStore

    db = _get_db()
    evaluator = CandidateEvaluator(db)
    eval_result = evaluator.get_evaluation(req.evaluation_id)
    if not eval_result:
        raise HTTPException(404, "Evaluation not found")

    candidates = eval_result.get("all_evaluated", [])
    if req.candidate_index >= len(candidates):
        raise HTTPException(400, f"candidate_index {req.candidate_index} out of range")

    cand = candidates[req.candidate_index]
    store = FingerprintStore()
    if not store.load():
        store = None

    dossier = build_dossier_from_evaluation(cand, db, store)
    save_dossier(dossier)
    return dossier


@app.get("/intelligence/dossier/{dossier_id}")
def get_dossier(dossier_id: str):
    """Retrieve a saved validation dossier."""
    from ..intelligence.dossier import load_dossier
    d = load_dossier(dossier_id)
    if not d:
        raise HTTPException(404, "Dossier not found")
    return d


# --- Validation / Learning endpoints ---

# Shared queue + feedback instances (request-scoped in production, but fine for dev)
_validation_queue = None
_feedback_memory = None


def _get_queue():
    global _validation_queue
    if _validation_queue is None:
        from ..validation.queue import ValidationQueue
        _validation_queue = ValidationQueue()
        _validation_queue.load()
    return _validation_queue


def _get_feedback():
    global _feedback_memory
    if _feedback_memory is None:
        from ..learning.feedback import FeedbackMemory
        _feedback_memory = FeedbackMemory()
        _feedback_memory.load()
    return _feedback_memory


class QueueAddRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None
    source_type: str = "custom_formula"
    candidate_id: Optional[str] = None
    novelty_score: float = 0.0
    exotic_score: float = 0.0
    evaluation_score: float = 0.0


class QueueBuildRequest(BaseModel):
    run_id: str


class FeedbackAddRequest(BaseModel):
    formula: str
    elements: List[str] = []
    target_property: str = "formation_energy"
    predicted_value: Optional[float] = None
    observed_value: Optional[float] = None
    observed_result_type: str = "proxy_check"
    decision: str = "keep"
    reviewer: str = "api"
    source_note: str = ""
    validation_id: Optional[str] = None
    candidate_id: Optional[str] = None


@app.get("/validation/presets")
def validation_presets():
    """Return the validation ladder stages."""
    from ..validation.spec import VALIDATION_STAGES
    return {"stages": VALIDATION_STAGES}


@app.post("/validation/queue/add")
def queue_add(req: QueueAddRequest):
    """Add a candidate to the validation queue."""
    from ..validation.spec import ValidationCandidate
    q = _get_queue()
    vc = ValidationCandidate(
        source_type=req.source_type, formula=req.formula,
        elements=req.elements, spacegroup=req.spacegroup,
        candidate_id=req.candidate_id,
        novelty_score=req.novelty_score,
        exotic_score=req.exotic_score,
        evaluation_score=req.evaluation_score)
    result = q.add(vc)
    q.save()
    return result


@app.post("/validation/queue/build-from-generation")
def queue_build_gen(req: QueueBuildRequest):
    """Build queue entries from a generation run."""
    q = _get_queue()
    result = q.build_from_generation(req.run_id, _get_db())
    q.save()
    return result


@app.post("/validation/queue/build-from-evaluation")
def queue_build_eval(req: QueueBuildRequest):
    """Build queue entries from an evaluation run."""
    q = _get_queue()
    result = q.build_from_evaluation(req.run_id, _get_db())
    q.save()
    return result


@app.get("/validation/queue/status")
def queue_status():
    """Return queue summary."""
    return _get_queue().status()


@app.get("/validation/queue/calibrated")
def queue_calibrated():
    """Return validation queue with calibration data."""
    q = _get_queue()
    from ..calibration.confidence import load_calibration, get_calibrated_confidence
    fe_cal = load_calibration("formation_energy")

    candidates = q.get_top(n=50)
    for c in candidates:
        n_elem = len(c.get("elements", []))
        if fe_cal:
            conf = get_calibrated_confidence(fe_cal, n_elements=n_elem)
            c["benchmark_confidence_band"] = conf["confidence_band"]
            c["expected_error_band"] = conf["expected_error"]
        else:
            c["benchmark_confidence_band"] = "unknown"
            c["expected_error_band"] = None
    return {
        "calibrated_queue": candidates,
        "calibration_available": fe_cal is not None,
        "note": "Calibration from benchmark on known corpus. NOT statistical probability.",
    }


@app.get("/validation/queue/{validation_id}")
def queue_get(validation_id: str):
    """Get a specific validation candidate."""
    c = _get_queue().get(validation_id)
    if not c:
        raise HTTPException(404, "Validation candidate not found")
    return c.to_dict()


@app.post("/validation/feedback/add")
def feedback_add(req: FeedbackAddRequest):
    """Record a feedback entry (prediction vs observation)."""
    from ..learning.feedback import FeedbackEntry
    fm = _get_feedback()
    entry = FeedbackEntry(
        formula=req.formula, elements=req.elements,
        target_property=req.target_property,
        predicted_value=req.predicted_value,
        observed_value=req.observed_value,
        observed_result_type=req.observed_result_type,
        decision=req.decision, reviewer=req.reviewer,
        source_note=req.source_note,
        validation_id=req.validation_id,
        candidate_id=req.candidate_id)
    fid = fm.add(entry)
    fm.save()
    return {"feedback_id": fid, "decision": req.decision}


@app.get("/learning/status")
def learning_status():
    """Return feedback memory status."""
    return _get_feedback().status()


@app.get("/learning/queue")
def learning_queue():
    """Return the learning/retraining queue."""
    from ..learning.memory import build_learning_queue
    return {"queue": build_learning_queue(_get_feedback())}


@app.get("/learning/summary")
def learning_summary():
    """Return full learning summary."""
    from ..learning.memory import generate_learning_summary
    return generate_learning_summary(_get_feedback())


# --- Evidence / Benchmark / Calibration endpoints ---

_evidence_registry = None


def _get_evidence():
    global _evidence_registry
    if _evidence_registry is None:
        from ..evidence.spec import EvidenceRegistry
        _evidence_registry = EvidenceRegistry()
        _evidence_registry.load()
    return _evidence_registry


class EvidenceImportRequest(BaseModel):
    records: list


class BenchmarkRunRequest(BaseModel):
    target_property: str = "formation_energy"
    sample_size: int = 200
    seed: int = 42


@app.post("/evidence/import/json")
def evidence_import_json(req: EvidenceImportRequest):
    """Import evidence records from JSON."""
    reg = _get_evidence()
    result = reg.import_json(req.records)
    reg.save()
    return result


@app.post("/evidence/import/csv")
def evidence_import_csv(req: EvidenceImportRequest):
    """Import evidence from CSV-like rows."""
    reg = _get_evidence()
    result = reg.import_csv_rows(req.records)
    reg.save()
    return result


@app.get("/evidence/status")
def evidence_status():
    """Return evidence registry status."""
    return _get_evidence().status()


@app.get("/evidence/feedback-links")
def evidence_feedback_links():
    """Show evidence-feedback auto-link results."""
    from ..evidence.linker import batch_link
    reg = _get_evidence()
    fm = _get_feedback()
    db = _get_db()
    result = batch_link(reg, db, fm)
    fm.save()
    return result


@app.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    """Get a specific evidence record."""
    r = _get_evidence().get(evidence_id)
    if not r:
        raise HTTPException(404, "Evidence not found")
    return r.to_dict()


@app.get("/benchmark/presets")
def benchmark_presets():
    """Return available benchmark targets."""
    return {"targets": ["formation_energy", "band_gap"],
            "default_sample_size": 200, "default_seed": 42}


@app.post("/benchmark/run")
def run_benchmark_endpoint(req: BenchmarkRunRequest):
    """Run a prediction benchmark on known corpus materials."""
    from ..benchmark.runner import run_benchmark, save_benchmark
    db = _get_db()
    report = run_benchmark(db, target_property=req.target_property,
                           sample_size=req.sample_size, seed=req.seed)
    save_benchmark(report)
    return report


@app.get("/benchmark/status")
def benchmark_status():
    """List saved benchmarks."""
    from ..benchmark.runner import list_benchmarks
    return {"benchmarks": list_benchmarks()}


@app.get("/benchmark/{benchmark_id}")
def get_benchmark(benchmark_id: str):
    """Retrieve a saved benchmark."""
    import os, json
    path = os.path.join("artifacts/benchmark", f"{benchmark_id}.json")
    if not os.path.exists(path):
        raise HTTPException(404, "Benchmark not found")
    with open(path) as f:
        return json.load(f)


@app.get("/calibration/status")
def calibration_status():
    """List available calibrations."""
    from ..calibration.confidence import load_calibration
    results = {}
    for target in ["formation_energy", "band_gap"]:
        cal = load_calibration(target)
        if cal:
            results[target] = {
                "overall_mae": cal.get("overall_mae"),
                "overall_confidence": cal.get("overall_confidence_band"),
                "sample_size": cal.get("sample_size"),
            }
    return {"calibrations": results}


@app.get("/calibration/{target_property}")
def get_calibration(target_property: str):
    """Get calibration for a specific target property."""
    from ..calibration.confidence import load_calibration
    cal = load_calibration(target_property)
    if not cal:
        raise HTTPException(404, f"No calibration for {target_property}")
    return cal


# --- Calibrated integration endpoints ---

@app.get("/intelligence/material/{material_id}/calibrated")
def intelligence_calibrated(material_id: str):
    """Material intelligence report with calibration integration."""
    from ..intelligence.dossier import build_dossier
    from ..features.fingerprint_store import FingerprintStore
    db = _get_db()
    m = db.get_material(material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    store = FingerprintStore()
    if not store.load():
        store = None
    dossier = build_dossier(
        formula=m.formula, elements=m.elements, spacegroup=m.spacegroup,
        material_id=material_id, query_type="corpus_material",
        db=db, store=store)
    return dossier


class CalibratedReportRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None


@app.post("/intelligence/report/calibrated")
def intelligence_report_calibrated(req: CalibratedReportRequest):
    """Intelligence report with calibration for any formula."""
    from ..intelligence.dossier import build_dossier
    from ..features.fingerprint_store import FingerprintStore
    db = _get_db()
    store = FingerprintStore()
    if not store.load():
        store = None
    dossier = build_dossier(
        formula=req.formula, elements=req.elements,
        spacegroup=req.spacegroup, db=db, store=store,
        temperature_K=req.temperature_K, pressure_GPa=req.pressure_GPa)
    return dossier


# --- Training ladder endpoints ---

@app.get("/training/ladder/status")
def training_ladder_status():
    """Return status of training ladder rungs."""
    from ..training.ladder import ladder_status
    return ladder_status()


@app.get("/training/ladder/models")
def training_ladder_models():
    """Return all models from the training ladder."""
    from ..models.registry import list_models
    models = list_models()
    return {"models": models}


# --- Frontier endpoints ---

class FrontierRunRequest(BaseModel):
    profile: Optional[str] = "balanced_frontier"
    source: str = "corpus"
    band_gap_target: Optional[float] = None
    band_gap_tolerance: float = 2.0
    fe_max: float = 1.0
    top_k: int = 50
    pool_limit: int = 5000


@app.get("/frontier/presets")
def frontier_presets():
    """Return available frontier profiles."""
    from ..frontier.spec import ALL_FRONTIER_PRESETS
    return {"presets": {n: fn().to_dict() for n, fn in ALL_FRONTIER_PRESETS.items()}}


@app.get("/frontier/status")
def frontier_status():
    """List saved frontier runs."""
    from ..frontier.engine import FrontierEngine
    return {"runs": FrontierEngine(_get_db()).list_runs()}


@app.post("/frontier/run")
def frontier_run(req: FrontierRunRequest):
    """Run a dual-target frontier selection."""
    from ..frontier.engine import FrontierEngine
    from ..frontier.spec import ALL_FRONTIER_PRESETS, FrontierProfile
    db = _get_db()
    engine = FrontierEngine(db)
    if req.profile in ALL_FRONTIER_PRESETS:
        profile = ALL_FRONTIER_PRESETS[req.profile]()
    else:
        profile = FrontierProfile(name=req.profile or "custom")
    if req.band_gap_target is not None:
        profile.band_gap_target = req.band_gap_target
        profile.band_gap_tolerance = req.band_gap_tolerance
    profile.fe_max = req.fe_max
    profile.top_k = req.top_k
    profile.pool_limit = req.pool_limit
    result, _ = engine.run_and_save(profile, source=req.source)
    return result


@app.get("/frontier/{run_id}")
def frontier_get(run_id: str):
    """Retrieve a saved frontier run."""
    from ..frontier.engine import FrontierEngine
    result = FrontierEngine(_get_db()).get_run(run_id)
    if not result:
        raise HTTPException(404, "Frontier run not found")
    return result


# --- Validation Pack endpoints ---

class PackFromFrontierRequest(BaseModel):
    frontier_run_id: str
    top_k: int = 20
    push_to_queue: bool = False


class PackBuildOneRequest(BaseModel):
    formula: str
    elements: List[str]
    spacegroup: Optional[int] = None
    source_type: str = "known_corpus_candidate"


@app.post("/validation-pack/build-from-frontier")
def build_pack_from_frontier(req: PackFromFrontierRequest):
    """Build validation packs from a frontier run."""
    from ..validation_pack.builder import ValidationPackBuilder
    builder = ValidationPackBuilder(_get_db())
    packs = builder.build_from_frontier_id(req.frontier_run_id, req.top_k)
    if not packs:
        raise HTTPException(404, "Frontier run not found or empty")
    path = builder.save_batch(packs, label=req.frontier_run_id[:8])
    result = {
        "pack_count": len(packs),
        "packs": [p.to_dict() for p in packs],
        "saved_to": path,
    }
    if req.push_to_queue:
        queue_result = builder.push_to_queue(packs)
        result["queue_result"] = queue_result
    return result


@app.post("/validation-pack/build-one")
def build_pack_one(req: PackBuildOneRequest):
    """Build a single validation pack for any material."""
    from ..validation_pack.builder import ValidationPackBuilder
    builder = ValidationPackBuilder(_get_db())
    pack = builder.build_one(req.formula, req.elements, req.spacegroup, req.source_type)
    return pack.to_dict()


@app.get("/validation-pack/status")
def pack_status():
    """List saved validation pack batches."""
    import os
    d = "artifacts/validation_pack"
    if not os.path.exists(d):
        return {"batches": []}
    batches = [f for f in sorted(os.listdir(d)) if f.endswith(".json") and "batch" in f]
    return {"batches": batches}


# --- Triage endpoints ---

class TriageRunRequest(BaseModel):
    profile: str = "balanced_review_gate"
    frontier_run_id: Optional[str] = None
    top_k: int = 20


@app.get("/triage/presets")
def triage_presets():
    """Return available triage profiles."""
    from ..triage.spec import ALL_TRIAGE_PRESETS
    return {"presets": {n: fn().to_dict() for n, fn in ALL_TRIAGE_PRESETS.items()}}


@app.get("/triage/status")
def triage_status():
    """List saved triage runs."""
    from ..triage.engine import TriageEngine
    return {"runs": TriageEngine(_get_db()).list_runs()}


@app.post("/triage/from-frontier")
def triage_from_frontier(req: TriageRunRequest):
    """Run triage from a frontier run."""
    from ..triage.engine import TriageEngine
    from ..triage.spec import ALL_TRIAGE_PRESETS
    if not req.frontier_run_id:
        raise HTTPException(400, "frontier_run_id required")
    engine = TriageEngine(_get_db())
    profile = ALL_TRIAGE_PRESETS.get(req.profile, ALL_TRIAGE_PRESETS["balanced_review_gate"])()
    profile.top_k = req.top_k
    result = engine.run_from_frontier(req.frontier_run_id, profile, req.top_k)
    if "error" in result:
        raise HTTPException(404, result["error"])
    engine._save(result)
    return result


@app.get("/triage/{run_id}")
def triage_get(run_id: str):
    """Retrieve a saved triage run."""
    from ..triage.engine import TriageEngine
    result = TriageEngine(_get_db()).get_run(run_id)
    if not result:
        raise HTTPException(404, "Triage run not found")
    return result


# --- Niche Campaign endpoints ---

class NicheRunRequest(BaseModel):
    preset: Optional[str] = None
    name: str = ""
    source_mode: str = "corpus"
    frontier_profile: str = "balanced_frontier"
    triage_profile: str = "balanced_review_gate"
    band_gap_target: Optional[float] = None
    fe_max: float = 1.0
    frontier_top_k: int = 50
    triage_top_k: int = 20
    pool_limit: int = 5000


@app.get("/niche/presets")
def niche_presets():
    """Return available niche campaign presets."""
    from ..niche.spec import ALL_NICHE_PRESETS
    return {"presets": {n: fn().to_dict() for n, fn in ALL_NICHE_PRESETS.items()}}


@app.get("/niche/status")
def niche_status():
    """List saved niche campaign runs."""
    from ..niche.engine import NicheCampaignEngine
    return {"runs": NicheCampaignEngine(_get_db()).list_runs()}


@app.post("/niche/run")
def niche_run(req: NicheRunRequest):
    """Run a niche discovery campaign."""
    from ..niche.engine import NicheCampaignEngine
    from ..niche.spec import ALL_NICHE_PRESETS, NicheCampaignSpec
    engine = NicheCampaignEngine(_get_db())
    if req.preset and req.preset in ALL_NICHE_PRESETS:
        spec = ALL_NICHE_PRESETS[req.preset]()
    else:
        spec = NicheCampaignSpec(
            name=req.name or "custom", source_mode=req.source_mode,
            frontier_profile=req.frontier_profile, triage_profile=req.triage_profile,
            band_gap_target=req.band_gap_target, fe_max=req.fe_max,
            frontier_top_k=req.frontier_top_k, triage_top_k=req.triage_top_k,
            pool_limit=req.pool_limit)
    spec.pool_limit = req.pool_limit
    result, _ = engine.run_and_save(spec)
    return result


@app.get("/niche/{campaign_id}")
def niche_get(campaign_id: str):
    """Retrieve a saved niche campaign."""
    from ..niche.engine import NicheCampaignEngine
    result = NicheCampaignEngine(_get_db()).get_run(campaign_id)
    if not result:
        raise HTTPException(404, "Niche campaign not found")
    return result


@app.post("/niche/compare")
def niche_compare(campaign_ids: List[str] = []):
    """Compare multiple niche campaigns."""
    from ..niche.engine import NicheCampaignEngine
    engine = NicheCampaignEngine(_get_db())
    results = []
    for cid in campaign_ids:
        r = engine.get_run(cid)
        if r:
            results.append(r)
    if not results:
        raise HTTPException(404, "No campaigns found")
    return engine.compare(results)


# --- Orchestrator endpoints ---

@app.get("/orchestrator/status")
def orchestrator_status():
    """Return orchestrator overview — coverage stats and proposal count."""
    from ..orchestrator.coverage import analyze_coverage
    from ..orchestrator.learning import detect_error_hotspots, generate_retraining_proposals
    db = _get_db()
    cov = analyze_coverage(db, limit=5000)
    hotspots = detect_error_hotspots()
    proposals = generate_retraining_proposals(hotspots)
    return {
        "corpus_size": cov.total_materials,
        "elements_covered": cov.total_elements_seen,
        "spacegroups_covered": cov.total_spacegroups_seen,
        "error_hotspots": len(hotspots),
        "retraining_proposals": len(proposals),
        "sparse_regions": len(cov.sparse_regions),
    }


@app.post("/orchestrator/run")
def orchestrator_run():
    """Run full orchestrator analysis and generate report."""
    from ..orchestrator.report import generate_orchestrator_report
    return generate_orchestrator_report(_get_db())


@app.get("/orchestrator/coverage")
def orchestrator_coverage():
    """Get chemical space coverage analysis."""
    from ..orchestrator.coverage import analyze_coverage, identify_exotic_niches
    db = _get_db()
    cov = analyze_coverage(db, limit=10000)
    niches = identify_exotic_niches(cov)
    return {"coverage": cov.to_dict(), "exotic_niches": niches}


@app.get("/orchestrator/retraining-proposals")
def orchestrator_proposals():
    """Get current retraining proposals based on error analysis."""
    from ..orchestrator.learning import detect_error_hotspots, generate_retraining_proposals
    hotspots = detect_error_hotspots()
    proposals = generate_retraining_proposals(hotspots)
    return {"hotspots": [h.to_dict() for h in hotspots],
            "proposals": [p.to_dict() for p in proposals]}


# --- Corpus Sources endpoints ---

@app.get("/corpus-sources/registry")
def corpus_sources_registry():
    """Return the source registry."""
    from ..corpus_sources.spec import SOURCE_REGISTRY
    return {"sources": [s.to_dict() for s in SOURCE_REGISTRY]}


@app.get("/corpus-sources/status")
def corpus_sources_status():
    """Return corpus expansion status."""
    from ..corpus_sources.spec import SOURCE_REGISTRY
    active = sum(1 for s in SOURCE_REGISTRY if s.status == "active")
    planned = sum(1 for s in SOURCE_REGISTRY if s.status == "planned")
    return {"active_sources": active, "planned_sources": planned, "total_sources": len(SOURCE_REGISTRY)}


@app.post("/corpus-sources/stage")
def corpus_sources_stage(source: str = "materials_project"):
    """Run staging analysis for a source (simulated for MP)."""
    from ..corpus_sources.staging import simulate_mp_staging, save_staging
    db = _get_db()
    report = simulate_mp_staging(db, sample_size=200)
    save_staging(report)
    return report.to_dict()


@app.get("/corpus-sources/recommendation")
def corpus_sources_recommendation():
    """Get expansion recommendation based on staging."""
    from ..corpus_sources.staging import simulate_mp_staging, generate_expansion_recommendation
    db = _get_db()
    mp_report = simulate_mp_staging(db, sample_size=200)
    return generate_expansion_recommendation([mp_report])


# --- Pilot Ingestion endpoints ---

@app.get("/corpus-sources/pilot/status")
def pilot_status():
    """Return pilot ingestion status."""
    import os
    d = "artifacts/corpus_sources"
    has_plan = os.path.exists(os.path.join(d, "pilot_plan.json"))
    has_run = os.path.exists(os.path.join(d, "pilot_run.json"))
    return {"plan_exists": has_plan, "run_exists": has_run}


@app.post("/corpus-sources/pilot/plan")
def pilot_plan(target_count: int = 200):
    """Generate a pilot ingestion plan."""
    from ..corpus_sources.pilot import generate_pilot_plan
    db = _get_db()
    plan, candidates = generate_pilot_plan(db, target_count)
    return {"plan": plan.to_dict(), "sample_candidates": [c.to_dict() for c in candidates[:10]]}


@app.post("/corpus-sources/pilot/run")
def pilot_run(target_count: int = 200, dry_run: bool = True):
    """Execute a pilot ingestion (dry_run=True by default for safety)."""
    from ..corpus_sources.pilot import generate_pilot_plan, execute_pilot, save_pilot_artifacts
    db = _get_db()
    plan, candidates = generate_pilot_plan(db, target_count)
    result = execute_pilot(db, plan, candidates, dry_run=dry_run)
    save_pilot_artifacts(plan, result, candidates)
    return result.to_dict()


@app.get("/corpus-sources/pilot/recommendation")
def pilot_recommendation():
    """Get pilot recommendation."""
    import os, json
    path = os.path.join("artifacts/corpus_sources", "pilot_recommendation.json")
    if not os.path.exists(path):
        return {"recommendation": "no_pilot_run_yet"}
    with open(path) as f:
        return json.load(f)


# --- Tier endpoints ---

@app.get("/corpus-sources/tiers/status")
def tiers_status():
    """Return tier classification status."""
    from ..corpus_sources.tiers import ALL_TIERS, TIER_DESCRIPTIONS
    return {"tiers": ALL_TIERS, "descriptions": TIER_DESCRIPTIONS}


@app.get("/corpus-sources/tiers/summary")
def tiers_summary():
    """Compute and return full tier summary."""
    from ..corpus_sources.tiers import compute_tier_summary, save_tier_summary
    db = _get_db()
    summary = compute_tier_summary(db)
    save_tier_summary(summary)
    return summary.to_dict()


# --- COD Pilot endpoints ---

@app.post("/corpus-sources/cod/pilot/plan")
def cod_pilot_plan(target_count: int = 50):
    """Generate a COD pilot ingestion plan."""
    from ..corpus_sources.cod_pilot import generate_cod_plan
    db = _get_db()
    plan, candidates = generate_cod_plan(db, target_count)
    return {"plan": plan.to_dict(), "sample_candidates": [c.to_dict() for c in candidates[:10]]}


@app.post("/corpus-sources/cod/pilot/run")
def cod_pilot_run(target_count: int = 50, dry_run: bool = True):
    """Execute COD pilot ingestion (dry_run=True by default for safety)."""
    from ..corpus_sources.cod_pilot import (
        generate_cod_plan, execute_cod_pilot, compute_value_report, save_cod_artifacts)
    db = _get_db()
    plan, candidates = generate_cod_plan(db, target_count)
    result = execute_cod_pilot(db, plan, candidates, dry_run=dry_run)
    value_report = compute_value_report(db, plan, result, candidates)
    save_cod_artifacts(plan, result, candidates, value_report)
    return result.to_dict()


@app.get("/corpus-sources/cod/pilot/{run_id}")
def cod_pilot_get(run_id: str):
    """Get COD pilot run result by ID."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/corpus_sources", "cod_pilot_run.json")
    if not _os.path.exists(path):
        raise HTTPException(404, "No COD pilot run found")
    with open(path) as f:
        data = _json.load(f)
    if data.get("run_id") != run_id:
        raise HTTPException(404, f"Run {run_id} not found")
    return data


@app.get("/corpus-sources/cod/recommendation")
def cod_recommendation():
    """Get COD operational recommendation."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/corpus_sources", "cod_recommendation.json")
    if not _os.path.exists(path):
        return {"recommendation": "no_cod_pilot_run_yet"}
    with open(path) as f:
        return _json.load(f)


# --- Hierarchical Band Gap endpoints ---

@app.get("/hierarchical-band-gap/status")
def hierarchical_bg_status():
    """Return hierarchical band_gap model status."""
    import os as _os
    d = "artifacts/hierarchical_band_gap"
    has_gate = _os.path.exists(_os.path.join(d, "gate_metrics.json"))
    has_reg = _os.path.exists(_os.path.join(d, "nonmetal_regressor.json"))
    has_dec = _os.path.exists(_os.path.join(d, "promotion_decision.json"))
    return {"target": "band_gap", "phase": "IV.N",
            "gate_trained": has_gate, "regressor_trained": has_reg,
            "decision_made": has_dec}


@app.get("/hierarchical-band-gap/gate")
def hierarchical_bg_gate():
    """Return metal gate classifier metrics."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/hierarchical_band_gap", "gate_metrics.json")
    if not _os.path.exists(path):
        return {"gate": None, "note": "Not trained yet"}
    with open(path) as f:
        return _json.load(f)


@app.get("/hierarchical-band-gap/regressor")
def hierarchical_bg_regressor():
    """Return non-metal regressor metrics."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/hierarchical_band_gap", "nonmetal_regressor.json")
    if not _os.path.exists(path):
        return {"regressor": None, "note": "Not trained yet"}
    with open(path) as f:
        return _json.load(f)


@app.get("/hierarchical-band-gap/comparison")
def hierarchical_bg_comparison():
    """Return pipeline comparison."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/hierarchical_band_gap", "pipeline_comparison.json")
    if not _os.path.exists(path):
        return {"comparison": None}
    with open(path) as f:
        return _json.load(f)


@app.get("/hierarchical-band-gap/decision")
def hierarchical_bg_decision():
    """Return promotion decision."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/hierarchical_band_gap", "promotion_decision.json")
    if not _os.path.exists(path):
        return {"decision": "no_decision_yet"}
    with open(path) as f:
        return _json.load(f)


# --- Stratified Retraining (Band Gap) endpoints ---

@app.get("/stratified-retraining/band-gap/status")
def stratified_retraining_bg_status():
    """Return stratified retraining status."""
    import os as _os
    d = "artifacts/stratified_retraining_band_gap"
    challengers = []
    if _os.path.isdir(d):
        for sub in sorted(_os.listdir(d)):
            rpath = _os.path.join(d, sub, "result.json")
            if _os.path.exists(rpath):
                challengers.append(sub)
    has_decision = _os.path.exists(_os.path.join(d, "promotion_decision.json"))
    return {"target": "band_gap", "phase": "IV.M",
            "challengers_trained": len(challengers),
            "challenger_names": challengers,
            "decision_made": has_decision}


@app.get("/stratified-retraining/band-gap/challengers")
def stratified_retraining_bg_challengers():
    """Return all stratified challenger results."""
    import os as _os, json as _json
    d = "artifacts/stratified_retraining_band_gap"
    results = []
    if _os.path.isdir(d):
        for sub in sorted(_os.listdir(d)):
            rpath = _os.path.join(d, sub, "result.json")
            if _os.path.exists(rpath):
                with open(rpath) as f:
                    results.append(_json.load(f))
    return {"challengers": results}


@app.get("/stratified-retraining/band-gap/comparison")
def stratified_retraining_bg_comparison():
    """Return comparison table."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/stratified_retraining_band_gap", "comparison_table.json")
    if not _os.path.exists(path):
        return {"comparison": [], "note": "Not generated yet"}
    with open(path) as f:
        return {"comparison": _json.load(f)}


@app.get("/stratified-retraining/band-gap/decision")
def stratified_retraining_bg_decision():
    """Return promotion decision."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/stratified_retraining_band_gap", "promotion_decision.json")
    if not _os.path.exists(path):
        return {"decision": "no_decision_yet"}
    with open(path) as f:
        return _json.load(f)


# --- Selective Retraining (Band Gap) endpoints ---

@app.get("/selective-retraining/band-gap/status")
def selective_retraining_bg_status():
    """Return selective retraining status for band_gap."""
    import os as _os
    d = "artifacts/selective_retraining_band_gap"
    challengers = []
    if _os.path.isdir(d):
        for sub in sorted(_os.listdir(d)):
            rpath = _os.path.join(d, sub, "result.json")
            if _os.path.exists(rpath):
                challengers.append(sub)
    has_decision = _os.path.exists(_os.path.join(d, "promotion_decision.json"))
    return {
        "target": "band_gap",
        "challengers_trained": len(challengers),
        "challenger_names": challengers,
        "decision_made": has_decision,
    }


@app.get("/selective-retraining/band-gap/challengers")
def selective_retraining_bg_challengers():
    """Return all challenger results."""
    import os as _os, json as _json
    d = "artifacts/selective_retraining_band_gap"
    results = []
    if _os.path.isdir(d):
        for sub in sorted(_os.listdir(d)):
            rpath = _os.path.join(d, sub, "result.json")
            if _os.path.exists(rpath):
                with open(rpath) as f:
                    results.append(_json.load(f))
    return {"challengers": results}


@app.get("/selective-retraining/band-gap/comparison")
def selective_retraining_bg_comparison():
    """Return comparison table."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/selective_retraining_band_gap", "comparison_table.json")
    if not _os.path.exists(path):
        return {"comparison": [], "note": "No comparison generated yet"}
    with open(path) as f:
        return {"comparison": _json.load(f)}


@app.get("/selective-retraining/band-gap/decision")
def selective_retraining_bg_decision():
    """Return promotion decision."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/selective_retraining_band_gap", "promotion_decision.json")
    if not _os.path.exists(path):
        return {"decision": "no_decision_yet"}
    with open(path) as f:
        return _json.load(f)


# --- Retraining Prep endpoints ---

@app.get("/retraining-prep/status")
def retraining_prep_status():
    """Return retraining preparation status."""
    import os as _os
    d = "artifacts/retraining_prep"
    has_hardcases = _os.path.exists(_os.path.join(d, "hardcase_summary.json"))
    has_datasets = _os.path.exists(_os.path.join(d, "selective_datasets.json"))
    has_priority = _os.path.exists(_os.path.join(d, "retraining_priority.json"))
    return {
        "phase": "IV.K",
        "hardcases_analyzed": has_hardcases,
        "datasets_built": has_datasets,
        "priority_ranked": has_priority,
        "models_retrained": False,
        "note": "Datasets prepared — training NOT executed yet",
    }


@app.get("/retraining-prep/hardcases")
def retraining_prep_hardcases(target: str = "band_gap"):
    """Get hard-case mining results for a target."""
    from ..retraining_prep.mining import mine_hard_cases
    db = _get_db()
    summary, cases = mine_hard_cases(db, target=target, limit=100)
    return {
        "summary": summary.to_dict(),
        "sample_hardcases": [c.to_dict() for c in cases[:20]],
    }


@app.get("/retraining-prep/tiers")
def retraining_prep_tiers():
    """Get difficulty tier distribution for both targets."""
    from ..retraining_prep.mining import mine_hard_cases
    db = _get_db()
    bg_summary, _ = mine_hard_cases(db, target="band_gap", limit=0)
    fe_summary, _ = mine_hard_cases(db, target="formation_energy", limit=0)
    return {
        "band_gap": bg_summary.to_dict(),
        "formation_energy": fe_summary.to_dict(),
    }


@app.post("/retraining-prep/datasets/build")
def retraining_prep_datasets_build():
    """Build selective retraining datasets and save artifacts."""
    from ..retraining_prep.report import generate_full_report, save_report
    db = _get_db()
    report = generate_full_report(db)
    save_report(report)
    return {
        "datasets": report.datasets,
        "priority_ranking": report.priority_ranking,
        "recommendation": report.recommendation,
        "next_action": report.next_action,
    }


@app.get("/retraining-prep/recommendation")
def retraining_prep_recommendation():
    """Get retraining recommendation."""
    import os as _os, json as _json
    path = _os.path.join("artifacts/retraining_prep", "retraining_priority.json")
    if not _os.path.exists(path):
        return {"recommendation": "no_analysis_run_yet", "note": "Run POST /retraining-prep/datasets/build first"}
    with open(path) as f:
        return _json.load(f)


# --- Analytics endpoints ---

class AnalyticsReportRequest(BaseModel):
    formula: str
    elements: List[str]
    cif: Optional[str] = None


@app.get("/analytics/material/{material_id}")
def analytics_material(material_id: str):
    """Compute physical descriptors for a corpus material."""
    from ..analytics.descriptors import compute_descriptors
    from ..normalization.structure import load_structure
    db = _get_db()
    m = db.get_material(material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    structure = load_structure(m.structure_data) if m.structure_data else None
    desc = compute_descriptors(structure=structure, formula=m.formula,
                               elements=m.elements)
    return {
        "material_id": material_id,
        "formula": m.formula,
        "structure_available": structure is not None,
        "descriptors": desc,
        "note": "Descriptors from structure geometry and composition. NOT DFT.",
    }


@app.post("/analytics/report")
def analytics_report(req: AnalyticsReportRequest):
    """Compute descriptors for any formula, optionally with CIF."""
    from ..analytics.descriptors import compute_descriptors
    from ..normalization.structure import load_structure
    structure = load_structure(req.cif) if req.cif else None
    desc = compute_descriptors(structure=structure, formula=req.formula,
                               elements=req.elements)
    return {
        "formula": req.formula,
        "structure_available": structure is not None,
        "descriptors": desc,
    }


# Health alias
@app.get("/health")
def health():
    return status()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
