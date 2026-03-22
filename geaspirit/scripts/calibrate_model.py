#!/usr/bin/env python3
"""Calibrate model probabilities using OOF predictions from spatial CV."""
import argparse, os, sys, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    p = argparse.ArgumentParser(description="Calibrate model probabilities")
    p.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/outputs"))
    args = p.parse_args()

    probs = np.load(os.path.join(args.output, "oof_probs.npy"))
    labels = np.load(os.path.join(args.output, "oof_labels.npy"))

    # Remove NaN (folds with no test data)
    valid = ~np.isnan(probs)
    probs, labels = probs[valid], labels[valid]
    print(f"Calibrating on {len(probs)} OOF predictions...")

    from sklearn.calibration import CalibratedClassifierCV, calibration_curve
    from sklearn.metrics import brier_score_loss

    # Brier score before calibration
    brier_before = brier_score_loss(labels, probs)

    # Isotonic calibration on OOF predictions
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds='clip')
    iso.fit(probs, labels)
    cal_probs = iso.predict(probs)

    brier_after = brier_score_loss(labels, cal_probs)

    # ECE (Expected Calibration Error)
    def ece(y_true, y_prob, n_bins=10):
        bins = np.linspace(0, 1, n_bins + 1)
        total = 0
        for i in range(n_bins):
            mask = (y_prob >= bins[i]) & (y_prob < bins[i+1])
            if mask.sum() > 0:
                total += mask.sum() * abs(y_true[mask].mean() - y_prob[mask].mean())
        return total / len(y_true)

    ece_before = ece(labels, probs)
    ece_after = ece(labels, cal_probs)

    # Reliability curve
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        frac_pos_before, mean_pred_before = calibration_curve(labels, probs, n_bins=10, strategy='uniform')
        frac_pos_after, mean_pred_after = calibration_curve(labels, cal_probs, n_bins=10, strategy='uniform')
        fig, ax = plt.subplots(1, 1, figsize=(8, 6))
        ax.plot([0, 1], [0, 1], 'k--', label='Perfect')
        ax.plot(mean_pred_before, frac_pos_before, 'r-o', label=f'Before (Brier={brier_before:.4f})')
        ax.plot(mean_pred_after, frac_pos_after, 'g-o', label=f'After (Brier={brier_after:.4f})')
        ax.set_xlabel('Mean predicted probability')
        ax.set_ylabel('Fraction of positives')
        ax.set_title('Reliability Curve — GeaSpirit Calibration')
        ax.legend()
        plt.savefig(os.path.join(args.output, "reliability_curve.png"), dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  ✓ reliability_curve.png")
    except Exception as e:
        print(f"  ⚠ Plot failed: {e}")

    # Save calibrator
    import joblib
    joblib.dump(iso, os.path.join(args.output, "calibrator_isotonic.joblib"))

    metrics = {
        "brier_before": round(brier_before, 6),
        "brier_after": round(brier_after, 6),
        "brier_improvement": round(brier_before - brier_after, 6),
        "ece_before": round(ece_before, 6),
        "ece_after": round(ece_after, 6),
        "calibration_method": "isotonic_regression",
        "n_samples": len(probs),
    }

    with open(os.path.join(args.output, "calibration_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\n{'='*50}")
    print(f"CALIBRATION RESULTS:")
    print(f"  Brier score: {brier_before:.4f} → {brier_after:.4f}")
    print(f"  ECE:         {ece_before:.4f} → {ece_after:.4f}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
