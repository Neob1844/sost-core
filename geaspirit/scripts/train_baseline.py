#!/usr/bin/env python3
"""Train baseline mineral prospectivity model.

Usage: python3 scripts/train_baseline.py --indices data/indices/ --mrds data/mrds/mrds_deposits.csv --zone chuquicamata
"""
import argparse
import json
import os
import sys
import glob
import numpy as np

def main():
    parser = argparse.ArgumentParser(description="Train baseline mineral prospectivity model")
    parser.add_argument("--indices", default=os.path.expanduser("~/SOST/geaspirit/data/indices"))
    parser.add_argument("--mrds", default=os.path.expanduser("~/SOST/geaspirit/data/mrds/mrds_deposits.csv"))
    parser.add_argument("--zone", default="chuquicamata")
    parser.add_argument("--output", default=os.path.expanduser("~/SOST/geaspirit/models"))
    args = parser.parse_args()

    try:
        import rasterio
    except ImportError:
        print("Install rasterio: pip install rasterio")
        sys.exit(1)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from geaspirit.dataset import load_mrds_deposits, create_training_samples
    from geaspirit.model import train_and_evaluate

    # Load index rasters
    pattern = os.path.join(args.indices, f"{args.zone}*.tif")
    tif_files = sorted(glob.glob(pattern))
    if not tif_files:
        print(f"No index TIFFs found matching {pattern}")
        sys.exit(1)

    print(f"Loading {len(tif_files)} index rasters...")
    index_arrays = {}
    transform = None
    for f in tif_files:
        name = os.path.basename(f).replace(f"{args.zone}_s2_", "").replace(".tif", "")
        with rasterio.open(f) as src:
            index_arrays[name] = src.read(1)
            if transform is None:
                transform = src.transform

    # Load MRDS deposits
    config_path = os.path.expanduser("~/SOST/geaspirit/config.json")
    with open(config_path) as f:
        config = json.load(f)
    bbox = config["pilot_zones"][args.zone]["bbox"]

    print(f"Loading MRDS deposits for {args.zone}...")
    deposits = load_mrds_deposits(args.mrds, min_lat=bbox[0], max_lat=bbox[2],
                                   min_lon=bbox[1], max_lon=bbox[3])
    print(f"  Found {len(deposits)} deposits in zone")

    if len(deposits) < 5:
        print("Too few deposits for training. Need at least 5.")
        sys.exit(1)

    # Create training data
    print("Creating training samples...")
    X, y, feature_names = create_training_samples(index_arrays, transform, deposits)
    print(f"  Positive: {np.sum(y==1)}, Negative: {np.sum(y==0)}")

    # Train and evaluate
    print("Training models...")
    results, best_model = train_and_evaluate(X, y, feature_names)

    # Save results
    os.makedirs(args.output, exist_ok=True)
    results_path = os.path.join(args.output, f"{args.zone}_baseline_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n{'='*50}")
    print(f"RESULTS for {args.zone}:")
    for model_name, metrics in results.items():
        if "error" in metrics:
            print(f"  {model_name}: {metrics['error']}")
        else:
            print(f"  {model_name}: AUC={metrics['auc']}, Precision={metrics['precision']}, Recall={metrics['recall']}")
    print(f"{'='*50}")
    print(f"Saved to: {results_path}")

    # Save model
    try:
        import joblib
        model_path = os.path.join(args.output, f"{args.zone}_rf_model.joblib")
        joblib.dump(best_model, model_path)
        print(f"Model saved: {model_path}")
    except Exception as e:
        print(f"Model save failed: {e}")

if __name__ == "__main__":
    main()
