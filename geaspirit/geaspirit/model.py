"""ML training and evaluation for mineral prospectivity."""
import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score, confusion_matrix
from sklearn.model_selection import train_test_split


def train_and_evaluate(X, y, feature_names, test_size=0.3, seed=42):
    """Train Random Forest + XGBoost, return comparison."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y)

    results = {}

    # Random Forest
    rf = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=seed, n_jobs=-1)
    rf.fit(X_train, y_train)
    rf_probs = rf.predict_proba(X_test)[:, 1]
    rf_preds = (rf_probs >= 0.5).astype(int)
    results["random_forest"] = {
        "auc": round(roc_auc_score(y_test, rf_probs), 4),
        "precision": round(precision_score(y_test, rf_preds, zero_division=0), 4),
        "recall": round(recall_score(y_test, rf_preds, zero_division=0), 4),
        "feature_importance": {fn: round(float(imp), 4) for fn, imp in
                               zip(feature_names, rf.feature_importances_)},
    }

    # XGBoost (optional)
    try:
        from xgboost import XGBClassifier
        xgb = XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1,
                            random_state=seed, use_label_encoder=False, eval_metric='logloss')
        xgb.fit(X_train, y_train)
        xgb_probs = xgb.predict_proba(X_test)[:, 1]
        xgb_preds = (xgb_probs >= 0.5).astype(int)
        results["xgboost"] = {
            "auc": round(roc_auc_score(y_test, xgb_probs), 4),
            "precision": round(precision_score(y_test, xgb_preds, zero_division=0), 4),
            "recall": round(recall_score(y_test, xgb_preds, zero_division=0), 4),
        }
    except ImportError:
        results["xgboost"] = {"error": "xgboost not installed"}

    return results, rf
