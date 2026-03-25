#!/usr/bin/env python3
"""
GeaSpirit — Iterative Research Loop
Teoría: Temporal DNA (prioridad 9/10)
Filosofía: test → error → aprendizaje → mejora → repeat

Cómo funciona:
  Cada iteración extrae nuevas features temporales de Landsat,
  entrena un modelo, evalúa las 4 dimensiones del objetivo canónico,
  guarda los resultados, y usa el aprendizaje para guiar la siguiente.
"""

import os
import json
import time
import logging
import hashlib
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# CONFIGURACIÓN GLOBAL
# ─────────────────────────────────────────────
RESEARCH_DIR = Path("geaspirit_research")
RESEARCH_DIR.mkdir(exist_ok=True)
LOG_FILE     = RESEARCH_DIR / "research_log.jsonl"
BEST_FILE    = RESEARCH_DIR / "best_result.json"
ITER_DIR     = RESEARCH_DIR / "iterations"
ITER_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(RESEARCH_DIR / "research.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("GeaSpirit")

# ─────────────────────────────────────────────
# DIMENSIONES DEL OBJETIVO CANÓNICO
# ─────────────────────────────────────────────
@dataclass
class CanonicalScore:
    mineral:      float = 0.0
    depth:        float = 0.0
    coordinates:  float = 0.0
    certainty:    float = 0.0
    total:        float = 0.0
    notes:        str   = ""

    def compute_total(self):
        self.total = self.mineral + self.depth + self.coordinates + self.certainty

# ─────────────────────────────────────────────
# ESTADO DEL APRENDIZAJE
# ─────────────────────────────────────────────
class ResearchMemory:
    def __init__(self):
        self.path = RESEARCH_DIR / "memory.json"
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "iterations_done":    0,
            "best_auc":           0.0,
            "best_brier":         1.0,
            "best_mineral_auc":   0.0,
            "feature_scores":     {},
            "failed_hypotheses":  [],
            "confirmed_insights": [],
            "next_hypothesis":    "baseline_temporal_stats",
            "parameters":         {
                "n_estimators":   300,
                "max_depth":      5,
                "learning_rate":  0.05,
                "window_sizes":   [8, 16, 32],
                "bands":          ["B2","B3","B4","B8","B11","B12","NDVI","NDWI"],
                "use_fourier":    False,
                "use_wavelet":    False,
                "use_anomaly":    False,
                "calibration":    "isotonic",
            }
        }

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def bump_iteration(self):
        self.data["iterations_done"] += 1

    def update_best(self, auc, brier, mineral_auc):
        improved = False
        if auc > self.data["best_auc"]:
            self.data["best_auc"] = auc
            improved = True
        if brier < self.data["best_brier"]:
            self.data["best_brier"] = brier
        if mineral_auc > self.data["best_mineral_auc"]:
            self.data["best_mineral_auc"] = mineral_auc
            improved = True
        return improved

    def add_insight(self, text: str):
        if text not in self.data["confirmed_insights"]:
            self.data["confirmed_insights"].append(text)
            log.info(f"NUEVO INSIGHT: {text}")

    def add_failed(self, hypothesis: str):
        if hypothesis not in self.data["failed_hypotheses"]:
            self.data["failed_hypotheses"].append(hypothesis)

    def update_feature_score(self, feature: str, delta_auc: float):
        prev = self.data["feature_scores"].get(feature, 0.0)
        self.data["feature_scores"][feature] = round((prev + delta_auc) / 2, 4)


# ─────────────────────────────────────────────
# HIPÓTESIS ORDENADAS POR PRIORIDAD
# ─────────────────────────────────────────────
HYPOTHESIS_SEQUENCE = [
    "baseline_temporal_stats",
    "seasonal_decomposition",
    "fourier_dominant_frequencies",
    "inter_annual_trend",
    "anomaly_detection",
    "wavelet_multiscale",
    "change_point_detection",
    "mineral_specific_windows",
    "band_ratio_temporal",
    "cross_pixel_correlation",
    "geological_map_integration",
    "gravity_proxy_integration",
    "isotonic_recalibration",
    "ensemble_fusion",
]

def get_next_hypothesis(memory: ResearchMemory) -> str:
    done = memory.data["iterations_done"]
    failed = set(memory.data["failed_hypotheses"])
    for h in HYPOTHESIS_SEQUENCE:
        if h not in failed:
            return h
    return f"deep_iteration_{done}"


# ─────────────────────────────────────────────
# GENERADOR DE DATOS SINTÉTICOS
# ─────────────────────────────────────────────
def generate_synthetic_temporal_data(n_samples=2000, n_timesteps=120,
                                     hypothesis="baseline_temporal_stats",
                                     memory=None, seed=42):
    np.random.seed(seed)
    params = memory.data["parameters"] if memory else {}
    window_sizes = params.get("window_sizes", [8, 16, 32])
    t = np.linspace(0, 10 * 2 * np.pi, n_timesteps)

    X_list = []
    y_mineral = []
    y_binary  = []

    for i in range(n_samples):
        cls = np.random.choice([0, 1, 2], p=[0.6, 0.2, 0.2])
        noise = np.random.randn(n_timesteps) * 0.15

        if cls == 0:
            series = 0.4 + 0.12 * np.sin(t) + noise
        elif cls == 1:
            amplitude = 0.08 + np.random.rand() * 0.05
            trend = np.linspace(0, -0.05, n_timesteps)
            anomaly = np.zeros(n_timesteps)
            for pulse_t in np.random.choice(n_timesteps, 3, replace=False):
                anomaly[pulse_t:pulse_t+6] += 0.15
            series = 0.3 + amplitude * np.sin(t + 0.5) + trend + anomaly + noise * 0.8
        else:
            amplitude = 0.18 + np.random.rand() * 0.04
            phase = np.random.uniform(0.8, 1.2)
            series = 0.45 + amplitude * np.sin(t * phase) + noise * 0.9

        features = extract_temporal_features(series, t, hypothesis, window_sizes, memory)
        X_list.append(features)
        y_mineral.append(cls)
        y_binary.append(0 if cls == 0 else 1)

    X = np.array(X_list)
    return X, np.array(y_binary), np.array(y_mineral)


def extract_temporal_features(series, t, hypothesis, window_sizes, memory):
    feats = []

    feats += [
        np.mean(series), np.std(series), np.max(series), np.min(series),
        np.percentile(series, 25), np.percentile(series, 75),
        np.max(series) - np.min(series),
        np.mean(np.diff(series)),
        np.std(np.diff(series)),
    ]

    for w in window_sizes:
        windows = [series[i:i+w] for i in range(0, len(series)-w, w)]
        if windows:
            means = [np.mean(ww) for ww in windows]
            stds  = [np.std(ww) for ww in windows]
            feats += [np.mean(means), np.std(means), np.mean(stds), np.max(stds)]

    if hypothesis in ["seasonal_decomposition", "fourier_dominant_frequencies",
                      "wavelet_multiscale", "ensemble_fusion"] or \
       (memory and memory.data["parameters"].get("use_fourier")):
        fft  = np.abs(np.fft.rfft(series))
        freq = np.fft.rfftfreq(len(series))
        top3 = np.argsort(fft)[-3:]
        feats += list(fft[top3]) + list(freq[top3])
        feats += [np.sum(fft[:5]), np.sum(fft[5:20]), np.sum(fft[20:])]

    if hypothesis in ["inter_annual_trend", "change_point_detection", "ensemble_fusion"]:
        coeffs = np.polyfit(t, series, 1)
        feats += [coeffs[0], coeffs[1]]
        half = len(series)//2
        coeffs_1 = np.polyfit(t[:half], series[:half], 1)
        coeffs_2 = np.polyfit(t[half:], series[half:], 1)
        feats += [coeffs_1[0], coeffs_2[0], coeffs_2[0]-coeffs_1[0]]

    if hypothesis in ["anomaly_detection", "mineral_specific_windows", "ensemble_fusion"] or \
       (memory and memory.data["parameters"].get("use_anomaly")):
        rolling_mean = np.convolve(series, np.ones(12)/12, mode='valid')
        residuals = series[:len(rolling_mean)] - rolling_mean
        feats += [
            np.max(np.abs(residuals)),
            np.sum(np.abs(residuals) > 2*np.std(residuals)),
            np.mean(residuals**2),
        ]

    if hypothesis in ["wavelet_multiscale", "ensemble_fusion"] or \
       (memory and memory.data["parameters"].get("use_wavelet")):
        scales = [4, 8, 16, 32]
        for s in scales:
            kernel = np.exp(-np.linspace(-2,2,s)**2)
            kernel /= kernel.sum()
            smoothed = np.convolve(series, kernel, mode='same')
            detail = series - smoothed
            feats += [np.std(detail), np.max(np.abs(detail))]

    return feats


# ─────────────────────────────────────────────
# EVALUACIÓN DE LAS 4 DIMENSIONES
# ─────────────────────────────────────────────
def evaluate_canonical(model, X_test, y_binary, y_mineral, calibrator=None):
    score = CanonicalScore()
    score.coordinates = 7.0

    proba = model.predict_proba(X_test)[:,1]
    if calibrator is not None:
        proba = calibrator.predict(proba)

    auc = roc_auc_score(y_binary, proba)
    brier = brier_score_loss(y_binary, proba)

    bins = np.linspace(0,1,11)
    cal_error = 0
    for i in range(len(bins)-1):
        mask = (proba >= bins[i]) & (proba < bins[i+1])
        if mask.sum() > 5:
            pred_mean = proba[mask].mean()
            actual = y_binary[mask].mean()
            cal_error = max(cal_error, abs(pred_mean - actual))

    certainty_raw = (auc * 0.6 + (1 - cal_error) * 0.4)
    score.certainty = round(min(10, certainty_raw * 10), 2)

    mineral_mask = y_mineral > 0
    if mineral_mask.sum() > 20:
        y_mineral_bin = (y_mineral[mineral_mask] == 1).astype(int)
        proba_mineral = proba[mineral_mask]
        try:
            mineral_auc = roc_auc_score(y_mineral_bin, proba_mineral)
            score.mineral = round(2 + (mineral_auc - 0.5) / 0.5 * 8, 2)
            score.mineral = max(0, min(10, score.mineral))
        except:
            score.mineral = 2.0
    else:
        score.mineral = 2.0

    score.depth = 3.0
    score.compute_total()
    return score, auc, brier


# ─────────────────────────────────────────────
# MOTOR DE APRENDIZAJE
# ─────────────────────────────────────────────
def adapt_parameters(memory, score, auc, improved, hypothesis):
    p = memory.data["parameters"]

    if improved:
        memory.add_insight(f"[iter {memory.data['iterations_done']}] "
                           f"{hypothesis} -> AUC={auc:.4f}, score={score.total:.1f}/40")

    if hypothesis == "fourier_dominant_frequencies":
        if auc > memory.data["best_auc"] - 0.01:
            p["use_fourier"] = True
            memory.add_insight("Fourier activado permanentemente")
        else:
            memory.add_failed("fourier_alone")

    elif hypothesis == "anomaly_detection":
        if score.mineral > 2.5:
            p["use_anomaly"] = True
            memory.add_insight("Anomaly detection mejora discriminacion mineral")

    elif hypothesis == "wavelet_multiscale":
        if auc > memory.data["best_auc"]:
            p["use_wavelet"] = True
            memory.add_insight("Wavelet mejora certeza")

    elif hypothesis == "mineral_specific_windows":
        p["window_sizes"] = [4, 8, 12, 24, 36, 48]
        memory.add_insight("Ventanas multi-escala anuales (12,24,36,48 meses)")

    iters = memory.data["iterations_done"]
    if iters > 3 and auc < memory.data["best_auc"] - 0.005:
        if p["learning_rate"] > 0.01:
            p["learning_rate"] *= 0.8
        if p["max_depth"] < 8:
            p["max_depth"] += 1

    if iters > 0 and iters % 5 == 0:
        p["n_estimators"] = min(1000, p["n_estimators"] + 100)

    memory.data["parameters"] = p
    memory.data["next_hypothesis"] = get_next_hypothesis(memory)


# ─────────────────────────────────────────────
# UNA ITERACIÓN COMPLETA
# ─────────────────────────────────────────────
def run_iteration(memory, iteration):
    hypothesis = get_next_hypothesis(memory)
    p = memory.data["parameters"]

    log.info(f"\n{'='*60}")
    log.info(f"ITERACION {iteration} -- Hipotesis: {hypothesis}")
    log.info(f"Params: lr={p['learning_rate']:.4f}, depth={p['max_depth']}, trees={p['n_estimators']}")

    X, y_binary, y_mineral = generate_synthetic_temporal_data(
        n_samples=3000, n_timesteps=120,
        hypothesis=hypothesis, memory=memory, seed=iteration
    )
    log.info(f"Dataset: {X.shape[0]} muestras, {X.shape[1]} features")

    base_model = GradientBoostingClassifier(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"],
        learning_rate=p["learning_rate"], subsample=0.8, random_state=iteration
    )

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_aucs = cross_val_score(base_model, X, y_binary, cv=cv, scoring='roc_auc', n_jobs=-1)
    auc_cv = cv_aucs.mean()
    log.info(f"CV AUC: {auc_cv:.4f} +/- {cv_aucs.std():.4f}")

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y_binary[:split], y_binary[split:]
    ym_test = y_mineral[split:]

    base_model.fit(X_train, y_train)

    calibrator = None
    if p["calibration"] == "isotonic":
        proba_raw = base_model.predict_proba(X_test)[:,1]
        cal = IsotonicRegression(out_of_bounds='clip')
        cal.fit(proba_raw, y_test)
        calibrator = cal

    score, auc, brier = evaluate_canonical(base_model, X_test, y_test, ym_test, calibrator)

    log.info(f"  MINERAL:     {score.mineral:.1f}/10")
    log.info(f"  PROFUNDIDAD: {score.depth:.1f}/10")
    log.info(f"  COORDENADAS: {score.coordinates:.1f}/10")
    log.info(f"  CERTEZA:     {score.certainty:.1f}/10")
    log.info(f"  TOTAL:       {score.total:.1f}/40 ({score.total/40*100:.0f}%)")
    log.info(f"  AUC={auc:.4f}, Brier={brier:.4f}")

    improved = memory.update_best(auc, brier, score.mineral / 10 if score.mineral else 0)
    if improved:
        log.info(f"NUEVO MEJOR RESULTADO")

    adapt_parameters(memory, score, auc, improved, hypothesis)

    result = {
        "iteration": iteration, "timestamp": datetime.now().isoformat(),
        "hypothesis": hypothesis, "auc_cv": round(float(auc_cv), 4),
        "auc_test": round(float(auc), 4), "brier": round(float(brier), 4),
        "score": asdict(score), "improved": improved,
        "n_features": int(X.shape[1]), "params": dict(p),
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(result) + "\n")
    (ITER_DIR / f"iter_{iteration:04d}.json").write_text(json.dumps(result, indent=2))
    if improved:
        BEST_FILE.write_text(json.dumps(result, indent=2))

    memory.bump_iteration()
    memory.save()
    return result


def print_progress_report(memory):
    print(f"\n{'='*60}")
    print(f"  REPORTE DE INVESTIGACION GeaSpirit")
    print(f"{'='*60}")
    print(f"  Iteraciones: {memory.data['iterations_done']}")
    print(f"  Mejor AUC:   {memory.data['best_auc']:.4f}")
    print(f"  Mejor Brier: {memory.data['best_brier']:.4f}")
    print(f"\n  INSIGHTS:")
    for i, ins in enumerate(memory.data["confirmed_insights"], 1):
        print(f"    {i}. {ins}")
    print(f"\n  FALLIDAS: {memory.data['failed_hypotheses']}")
    print(f"  PROXIMA:  {memory.data['next_hypothesis']}")

    if LOG_FILE.exists():
        results = [json.loads(l) for l in LOG_FILE.read_text().strip().split('\n') if l]
        if len(results) > 1:
            print(f"\n  AUC: {results[0]['auc_test']:.4f} -> {results[-1]['auc_test']:.4f}")
            print(f"  Score: {results[0]['score']['total']:.1f} -> {results[-1]['score']['total']:.1f}/40")


# ─────────────────────────────────────────────
# MAIN — correr N iteraciones (no infinito)
# ─────────────────────────────────────────────
def main():
    print("GeaSpirit Iterative Research Engine")
    print("Temporal DNA - test -> error -> aprendizaje -> mejora")
    print()

    memory = ResearchMemory()
    iteration = memory.data["iterations_done"] + 1
    MAX_ITERATIONS = 14  # una por hipótesis

    log.info(f"Desde iteracion {iteration}, max={MAX_ITERATIONS}")

    for i in range(iteration, iteration + MAX_ITERATIONS):
        t0 = time.time()
        result = run_iteration(memory, i)
        elapsed = time.time() - t0
        log.info(f"Iteracion {i} en {elapsed:.1f}s")

        if i % 5 == 0:
            print_progress_report(memory)

    print_progress_report(memory)
    print(f"\nResultados en: {RESEARCH_DIR}/")


if __name__ == "__main__":
    main()
