"""Heavy task handlers for the useful-compute worker.

Each handler module exposes a `run(payload, formula_pool)` function that
takes a deterministic task payload + the in-memory formula pool, and
returns a dict containing `top_candidates`, `score_histogram`,
`summary_stats`, and `result_hash`.
"""
