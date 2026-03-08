// SOST Protocol — Copyright (c) 2026 SOST Foundation
// Licensed under the Business Source License 1.1. See LICENSE file.
#pragma once
// ConvergenceX v2.0: Persistent dataset cache + per-block program generation
// ASIC-resistance: O(4GB) memory required, no fixed pattern to optimize
#define CONVERGENCEX_VERSION "2.0"
#include "sost/types.h"
#include "sost/params.h"
#include "sost/serialize.h"
#include "sost/crypto.h"
#include <vector>
#include <array>
namespace sost {

// ConvergenceX v2 — Persistent Dataset Cache
// Dataset is computed once per block_prev_hash and reused
// across all nonce attempts. Eliminates redundant 4GB generation.
struct CXDataset {
    std::vector<uint64_t> memory;   // 4GB dataset (512M uint64_t entries)
    Bytes32 seed_hash;              // block_prev_hash that generated this dataset
    bool initialized = false;

    void generate(const Bytes32& block_prev_hash);
    bool is_valid_for(const Bytes32& block_prev_hash) const;
};

// Global dataset — reused across mining attempts for same block
extern thread_local CXDataset g_cx_dataset;

// ConvergenceX v2 — Per-Block Program Generation
// Each block_hash generates a unique sequence of operations.
// Makes ASIC optimization impossible — no fixed pattern to hardcode.
enum class CXOp : uint8_t {
    MUL   = 0,   // multiply
    XOR   = 1,   // xor
    ADD   = 2,   // add
    ROT   = 3,   // rotate left
    AND   = 4,   // bitwise and
    OR    = 5,   // bitwise or
    NOT   = 6,   // bitwise not
    SUB   = 7    // subtract
};

struct CXProgram {
    static constexpr size_t PROGRAM_LENGTH = 256;  // operations per round
    std::array<CXOp, PROGRAM_LENGTH> ops;
    std::array<uint64_t, PROGRAM_LENGTH> immediates;
    Bytes32 block_hash;

    void generate(const Bytes32& block_hash);
    uint64_t execute(uint64_t state, size_t step) const;
};

struct CXProblem {
    int32_t M[32][32];
    int32_t b[32];
    int32_t lam;
};

// Problem derivation
CXProblem derive_M_and_b(const Bytes32& block_key, int32_t n, int32_t lam);

// Math kernels
void matvec_A(const CXProblem& p, const int32_t* x, int32_t* out, int32_t n);
int64_t safe_residual_l1(const int32_t* Ax, const int32_t* b, int32_t n);
uint64_t l1_dist_sat_u64(const int32_t* a, const int32_t* b, int32_t n);
void one_gradient_step(const int32_t* x, const CXProblem& p, int32_t n, int32_t lr_shift, int32_t* out);

// Stability basin
std::vector<int32_t> derive_perturbation(const Bytes32& stctx, int32_t n, int32_t k_idx, int32_t scale);
Bytes32 stability_ctx(const uint8_t* hc72, const Bytes32& seed, const Bytes32& cp_root);
bool verify_stability_basin(
    const int32_t* x_final, const CXProblem& prob, int32_t n,
    int32_t lr_shift, const Bytes32& stctx,
    int32_t scale, int32_t k, int32_t margin, int32_t steps,
    int32_t stab_lr_shift, uint64_t& metric_out);

// Checkpoints
Bytes32 checkpoint_leaf(const Bytes32& state_h, const Bytes32& x_h, uint32_t round, uint64_t residual);
Bytes32 merkle_root_16(const std::vector<Bytes32>& leaves);

// Block construction
Bytes32 compute_block_key(const Bytes32& prev_hash);
Bytes32 compute_block_id(const uint8_t* full_header, size_t hdr_len, const Bytes32& commit);

// Full attempt
CXAttemptResult convergencex_attempt(
    const uint8_t* scratch, size_t scratch_len,
    const Bytes32& block_key, uint32_t nonce, uint32_t extra_nonce,
    const ConsensusParams& params, const uint8_t* header_core,
    int32_t epoch);

} // namespace sost
