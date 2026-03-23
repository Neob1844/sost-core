"""Direct GNN forward pass for autonomous discovery candidates.

Loads CGCNN/ALIGNN-Lite models and runs inference on lifted CIF structures.
Bypasses the package-level relative import issue by importing directly.
"""
import sys, os, logging
import numpy as np

log = logging.getLogger(__name__)

# Add src to path for direct imports
_SRC = os.path.join(os.path.dirname(__file__), "..")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

_ARTIFACTS = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts")
_MODELS_LOADED = {}

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    log.warning("torch not available — GNN inference disabled")

try:
    from models.cgcnn import CGCNN
    from models.alignn_lite import ALIGNNLite
    from features.crystal_graph import structure_to_graph
    from normalization.structure import load_structure
    HAS_MODELS = True
except ImportError as e:
    HAS_MODELS = False
    log.warning(f"Model imports failed: {e}")


def _find_best_model(target, model_type="cgcnn"):
    """Find the best model checkpoint for a target property."""
    search_dirs = [
        os.path.join(_ARTIFACTS, f"training_ladder_{target}"),
        os.path.join(_ARTIFACTS, f"training_ladder"),
        os.path.join(_ARTIFACTS, "training"),
        os.path.join(_ARTIFACTS, f"training_{target}"),
    ]
    best = None
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".pt") and model_type in f:
                    path = os.path.join(root, f)
                    # Prefer "full" rung, then largest rung
                    if "full" in root:
                        return path
                    if best is None or "40k" in root:
                        best = path
    return best


def _load_model(target, model_type="cgcnn"):
    """Load a model, caching it for reuse."""
    key = f"{model_type}_{target}"
    if key in _MODELS_LOADED:
        return _MODELS_LOADED[key]

    if not HAS_TORCH or not HAS_MODELS:
        return None

    path = _find_best_model(target, model_type)
    if not path or not os.path.exists(path):
        return None

    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        # Handle both formats: direct state_dict or wrapped with config
        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
            state_dict = checkpoint["model_state_dict"]
            config = checkpoint.get("config", {})
        else:
            state_dict = checkpoint  # direct state_dict
            config = {}

        if model_type == "cgcnn":
            # Infer config from checkpoint shapes
            n_elem = state_dict.get("embedding.weight", torch.zeros(64, 94)).shape[1]
            atom_dim = state_dict.get("embedding.weight", torch.zeros(64, 94)).shape[0]
            bond_dim = state_dict.get("gaussian.centers", torch.zeros(40)).shape[0]
            n_conv = sum(1 for k in state_dict if k.startswith("convs.") and k.endswith(".fc_full.weight"))
            fc_dim = state_dict.get("fc1.weight", torch.zeros(128, 64)).shape[0]
            model = CGCNN(n_elem=n_elem, atom_dim=atom_dim, bond_dim=bond_dim,
                          n_conv=n_conv, fc_dim=fc_dim)
        elif model_type == "alignn_lite":
            model = ALIGNNLite(
                n_features=config.get("n_features", 92),
                n_layers=config.get("n_layers", 4),
                n_hidden=config.get("n_hidden", 64),
            )
        else:
            return None

        model.load_state_dict(state_dict)
        model.eval()
        _MODELS_LOADED[key] = model
        log.info(f"Loaded {model_type} for {target}: {path}")
        return model
    except Exception as e:
        log.error(f"Failed to load {model_type} for {target}: {e}")
        return None


def predict_from_lifted_cif(cif_text, target="formation_energy", model_type="cgcnn"):
    """Run real GNN forward pass on a lifted CIF structure.

    Args:
        cif_text: CIF string of the lifted candidate structure
        target: "formation_energy" or "band_gap"
        model_type: "cgcnn" or "alignn_lite"

    Returns:
        dict with prediction, model info, and confidence
    """
    result = {
        "prediction": None,
        "model_type": model_type,
        "target": target,
        "status": "unavailable",
        "confidence": "none",
        "error": None,
    }

    if not HAS_TORCH or not HAS_MODELS:
        result["status"] = "dependencies_missing"
        result["error"] = "torch or model classes not available"
        return result

    # Load structure
    try:
        struct = load_structure(cif_text)
        if struct is None:
            result["status"] = "invalid_structure"
            result["error"] = "Could not parse CIF"
            return result
    except Exception as e:
        result["status"] = "structure_error"
        result["error"] = str(e)[:100]
        return result

    # Convert to graph
    try:
        graph_data = structure_to_graph(struct)
        if graph_data is None:
            result["status"] = "graph_conversion_failed"
            return result
    except Exception as e:
        result["status"] = "graph_error"
        result["error"] = str(e)[:100]
        return result

    # Load model
    model = _load_model(target, model_type)
    if model is None:
        result["status"] = "model_not_found"
        result["error"] = f"No {model_type} model for {target}"
        return result

    # Forward pass
    try:
        with torch.no_grad():
            # Graph data keys: atom_features, bond_distances, neighbor_indices, n_atoms
            atom_fea = torch.FloatTensor(graph_data["atom_features"])
            nbr_fea = torch.FloatTensor(graph_data["bond_distances"])
            nbr_idx = torch.LongTensor(graph_data["neighbor_indices"])

            pred = model(atom_fea, nbr_fea, nbr_idx)
            value = float(pred.squeeze().item())

            result["prediction"] = round(value, 4)
            result["status"] = "direct_gnn_success"
            result["confidence"] = "medium"  # lifted structure, not relaxed
            return result

    except Exception as e:
        result["status"] = "inference_error"
        result["error"] = str(e)[:100]
        return result
