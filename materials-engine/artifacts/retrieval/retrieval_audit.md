# Retrieval Audit

**Indexed:** 75,993
**Vector dim:** 104
**Build time:** 4.1s
**Method:** cosine similarity via dot product on L2-normalized vectors
**Backend:** numpy vectorized (CPU)

## Limitations

- Brute-force O(N) per query — fine for <100K, add ANN index for >100K
- Fingerprint captures composition + basic structure, not atomic positions
