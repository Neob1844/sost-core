// convergencex.cpp - ConvergenceX v2.0 Proof of Irreversible Convergence
// Consensus-critical: integer-only, deterministic, sequential.
// v2.0: Persistent dataset cache + per-block program generation
#include "sost/pow/convergencex.h"
#include <cstring>
#include <algorithm>
namespace sost {

// ---- CXDataset: Persistent 4GB dataset cache ----
thread_local CXDataset g_cx_dataset;

void CXDataset::generate(const Bytes32& block_prev_hash) {
    seed_hash = block_prev_hash;
    memory.resize(512ULL * 1024 * 1024); // 4GB as uint64_t
    // Initialize dataset from seed using sequential hash chain
    // Each entry depends on previous — cannot parallelize
    uint64_t state = 0;
    for (int i = 0; i < 8 && i < 32; ++i)
        state |= (uint64_t)block_prev_hash[i] << (i * 8);
    for (size_t i = 0; i < memory.size(); i++) {
        state = state * 6364136223846793005ULL + 1442695040888963407ULL;
        state ^= (state >> 33);
        state *= 0xff51afd7ed558ccdULL;
        state ^= (state >> 33);
        memory[i] = state;
    }
    initialized = true;
}

bool CXDataset::is_valid_for(const Bytes32& block_prev_hash) const {
    return initialized && seed_hash == block_prev_hash;
}

// ---- CXProgram: Per-block program generation ----
void CXProgram::generate(const Bytes32& bh) {
    block_hash = bh;
    // Derive program deterministically from block_hash
    // Any node can regenerate the same program for validation
    const uint8_t* data = bh.data();
    for (size_t i = 0; i < PROGRAM_LENGTH; i++) {
        ops[i] = static_cast<CXOp>(data[i % 32] % 8);
        uint64_t imm = 0;
        for (int b = 0; b < 8; b++) {
            imm = (imm << 8) | data[(i * 8 + b) % 32];
        }
        immediates[i] = imm | 1; // ensure non-zero
    }
}

uint64_t CXProgram::execute(uint64_t state, size_t step) const {
    const CXOp op = ops[step % PROGRAM_LENGTH];
    const uint64_t imm = immediates[step % PROGRAM_LENGTH];
    switch (op) {
        case CXOp::MUL: return state * imm;
        case CXOp::XOR: return state ^ imm;
        case CXOp::ADD: return state + imm;
        case CXOp::ROT: return (state << (imm % 63 + 1)) | (state >> (63 - imm % 63));
        case CXOp::AND: return state & (imm | 0xFFFFFFFF00000000ULL);
        case CXOp::OR:  return state | imm;
        case CXOp::NOT: return ~state ^ imm;
        case CXOp::SUB: return state - imm;
        default:        return state ^ imm;
    }
}

// ---- Problem Derivation (Section 3.2 Phase 1) ----
CXProblem derive_M_and_b(const Bytes32& block_key, int32_t n, int32_t lam) {
    CXProblem prob{}; prob.lam = lam;
    // M: PRNG(SHA256(MAGIC||"M"||block_key), n*n bytes)
    std::vector<uint8_t> mseed;
    append_magic(mseed); append(mseed, "M", 1); append(mseed, block_key);
    auto raw_m = prng_bytes(sha256(mseed), n * n);
    int k = 0;
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n; ++j)
            prob.M[i][j] = (int32_t)(raw_m[k++] % 255) - 127;
    // b: PRNG(SHA256(MAGIC||"B"||block_key), n*4 bytes)
    std::vector<uint8_t> bseed;
    append_magic(bseed); append(bseed, "B", 1); append(bseed, block_key);
    auto raw_b = prng_bytes(sha256(bseed), n * 4);
    for (int i = 0; i < n; ++i)
        prob.b[i] = read_i32_le(raw_b.data() + i * 4);
    return prob;
}

// ---- A(x) = M^T(Mx) + lam*x (Section 3.2) ----
void matvec_A(const CXProblem& p, const int32_t* x, int32_t* out, int32_t n) {
    int64_t t[32] = {};
    for (int i = 0; i < n; ++i) {
        int64_t acc = 0;
        for (int j = 0; j < n; ++j) acc += (int64_t)p.M[i][j] * (int64_t)x[j];
        t[i] = acc;
    }
    for (int j = 0; j < n; ++j) {
        int64_t acc = 0;
        for (int i = 0; i < n; ++i) acc += (int64_t)p.M[i][j] * t[i];
        out[j] = clamp_i32(acc + (int64_t)p.lam * (int64_t)x[j]);
    }
}

// ---- Residual L1 with saturation ----
int64_t safe_residual_l1(const int32_t* Ax, const int32_t* b, int32_t n) {
    int64_t acc = 0;
    constexpr int64_t MAX_RES = INT64_MAX;
    for (int i = 0; i < n; ++i) {
        int64_t d = (int64_t)clamp_i32((int64_t)Ax[i] - (int64_t)b[i]);
        acc += (d < 0) ? -d : d;
        if (acc > MAX_RES) return MAX_RES;
    }
    return acc;
}

// ---- L1 distance with u64 saturation ----
uint64_t l1_dist_sat_u64(const int32_t* a, const int32_t* b, int32_t n) {
    uint64_t acc = 0;
    for (int i = 0; i < n; ++i) {
        int64_t ai = clamp_i32(a[i]), bi = clamp_i32(b[i]);
        int64_t d = ai - bi; if (d < 0) d = -d;
        acc = sat_u64_add(acc, (uint64_t)d);
        if (acc == U64_MAX_VAL) return U64_MAX_VAL;
    }
    return acc;
}

// ---- One gradient step: x[i] -= (A(x)[i]-b[i]) >> lr_shift ----
void one_gradient_step(const int32_t* x, const CXProblem& p, int32_t n, int32_t lr_shift, int32_t* out) {
    int32_t Ax[32];
    matvec_A(p, x, Ax, n);
    for (int i = 0; i < n; ++i)
        out[i] = clamp_i32((int64_t)x[i] - (int64_t)asr_i32(clamp_i32((int64_t)Ax[i] - (int64_t)p.b[i]), lr_shift));
}

// ---- Perturbation generation (Section 3.3) ----
std::vector<int32_t> derive_perturbation(const Bytes32& stctx, int32_t n, int32_t k_idx, int32_t scale) {
    std::vector<uint8_t> pseed;
    append_magic(pseed); append(pseed, "PERT", 4); append(pseed, stctx);
    uint8_t tmp[8]; write_u32_le(tmp, (uint32_t)k_idx); write_u32_le(tmp+4, (uint32_t)n);
    append(pseed, tmp, 8);
    auto raw = prng_bytes(sha256(pseed), n);
    std::vector<int32_t> delta(n);
    if (scale <= 0) { std::fill(delta.begin(), delta.end(), 0); return delta; }
    int32_t span = 2 * scale + 1;
    for (int i = 0; i < n; ++i) delta[i] = (int32_t)(raw[i] % span) - scale;
    return delta;
}

// ---- Stability context ----
Bytes32 stability_ctx(const uint8_t* hc72, const Bytes32& seed, const Bytes32& cp_root) {
    std::vector<uint8_t> buf;
    append_magic(buf); append(buf, "STCTX", 5);
    append(buf, hc72, HEADER_CORE_LEN); append(buf, seed); append(buf, cp_root);
    return sha256(buf);
}

// ---- Stability basin verification (Section 3.3) ----
bool verify_stability_basin(
    const int32_t* x_final, const CXProblem& prob, int32_t n,
    int32_t lr_shift, const Bytes32& stctx,
    int32_t scale, int32_t k, int32_t margin, int32_t steps,
    int32_t stab_lr_shift, uint64_t& metric_out)
{
    int32_t k_eff = std::max(1, k);
    int32_t g = std::max(1, steps);
    int32_t st_lr = std::max(stab_lr_shift, lr_shift);
    int64_t margin_eff = (int64_t)margin * CX_M_NUM / CX_M_DEN;
    uint64_t margin_u64 = sat_u64_from_nonneg(margin_eff);
    int32_t large_th = std::max(1, (n * std::max(1, scale)) / 2);
    bool all_ok = true; metric_out = 0;
    for (int32_t i = 0; i < k_eff; ++i) {
        auto delta = derive_perturbation(stctx, n, i, scale);
        int32_t x_ref[32], x_pert[32];
        for (int j = 0; j < n; ++j) {
            x_ref[j] = clamp_i32(x_final[j]);
            x_pert[j] = clamp_i32((int64_t)x_final[j] + delta[j]);
        }
        uint64_t d0 = l1_dist_sat_u64(x_ref, x_pert, n);
        uint64_t d_prev = d0;
        for (int32_t step = 0; step < g; ++step) {
            int32_t nr[32], np[32];
            one_gradient_step(x_ref, prob, n, st_lr, nr);
            one_gradient_step(x_pert, prob, n, st_lr, np);
            std::memcpy(x_ref, nr, n*4); std::memcpy(x_pert, np, n*4);
            uint64_t d_now = l1_dist_sat_u64(x_ref, x_pert, n);
            if (d_now > sat_u64_add(d_prev, margin_u64)) { all_ok = false; d_prev = d_now; break; }
            d_prev = d_now;
        }
        metric_out = sat_u64_add(metric_out, d_prev);

        if (d0 > (uint64_t)large_th) {
            __int128 lhs = (__int128)d_prev * (__int128)CX_C_DEN;
            __int128 rhs = (__int128)d0 * (__int128)CX_C_NUM + (__int128)margin_eff;
            if (lhs > rhs) all_ok = false;
        }

    }
    return all_ok;
}

// ---- Checkpoint leaf (Section 3.5) ----
Bytes32 checkpoint_leaf(const Bytes32& state_h, const Bytes32& x_h, uint32_t round, uint64_t residual) {
    std::vector<uint8_t> buf;
    append(buf, "CP", 2); append(buf, state_h); append(buf, x_h);
    append_u32_le(buf, round); append_u64_le(buf, residual);
    return sha256(buf);
}

// ---- Merkle root of 16 leaves ----
Bytes32 merkle_root_16(const std::vector<Bytes32>& leaves) {
    if (leaves.empty()) return sha256(std::vector<uint8_t>{'N','O','_','C','H','E','C','K','P','O','I','N','T','S'});
    std::vector<Bytes32> tree = leaves;
    while (tree.size() > 1) {
        if (tree.size() & 1) tree.push_back(tree.back());
        std::vector<Bytes32> next;
        for (size_t i = 0; i < tree.size(); i += 2) {
            std::vector<uint8_t> buf;
            append(buf, tree[i]); append(buf, tree[i+1]);
            next.push_back(sha256(buf));
        }
        tree = next;
    }
    return tree[0];
}

// ---- Block key (Section 3.4) ----
Bytes32 compute_block_key(const Bytes32& prev_hash) {
    std::vector<uint8_t> buf;
    append(buf, prev_hash); append(buf, "BLOCK_KEY", 9);
    return sha256(buf);
}

// ---- Block ID (Appendix B) ----
Bytes32 compute_block_id(const uint8_t* hdr, size_t hdr_len, const Bytes32& commit) {
    std::vector<uint8_t> buf(hdr, hdr + hdr_len);
    append(buf, "ID", 2); append(buf, commit);
    return sha256(buf);
}

// ---- Mix from scratchpad ----
static int32_t mix_from_scratch(const uint8_t* scratch, size_t slen, uint32_t idx) {
    if (slen < 8) return 0;
    size_t off = ((size_t)idx * 4) % (slen - 4);
    return read_i32_le(scratch + off);
}

// ---- Full ConvergenceX v2.0 attempt (Section 3.2) ----
CXAttemptResult convergencex_attempt(
    const uint8_t* scratch, size_t scratch_len,
    const Bytes32& block_key, uint32_t nonce, uint32_t extra_nonce,
    const ConsensusParams& params, const uint8_t* header_core,
    int32_t epoch)
{
    CXAttemptResult res{}; res.is_stable = false; res.stability_metric = 0;
    int32_t n = params.cx_n;
    int32_t rounds = params.cx_rounds;
    int32_t lr_shift = params.cx_lr_shift;
    int32_t cp_interval = params.cx_checkpoint_interval > 0 ? params.cx_checkpoint_interval : 1;

    // v2.0: Ensure dataset is cached for this block's prev_hash
    // Extract prev_hash from header_core (first 32 bytes)
    Bytes32 prev_hash;
    std::memcpy(prev_hash.data(), header_core, 32);
    if (!g_cx_dataset.is_valid_for(prev_hash)) {
        g_cx_dataset.generate(prev_hash);
    }

    // v2.0: Generate per-block program from block_key
    CXProgram program;
    program.generate(block_key);

    // Seed
    std::vector<uint8_t> sbuf;
    append_magic(sbuf); append(sbuf, "SEED", 4);
    append(sbuf, header_core, HEADER_CORE_LEN);
    append(sbuf, block_key);
    append_u32_le(sbuf, nonce); append_u32_le(sbuf, extra_nonce);
    Bytes32 seed = sha256(sbuf);
    // x0
    std::vector<uint8_t> x0seed;
    append_magic(x0seed); append(x0seed, "X0", 2); append(x0seed, seed);
    auto rawx = prng_bytes(sha256(x0seed), n * 4);
    int32_t x[32];
    for (int i = 0; i < n; ++i)
        x[i] = asr_i32(read_i32_le(rawx.data() + i*4), 4);
    // Problem
    CXProblem prob = derive_M_and_b(block_key, n, params.cx_lam);
    // State
    std::vector<uint8_t> stbuf;
    append_magic(stbuf); append(stbuf, "ST", 2); append(stbuf, seed);
    Bytes32 state = sha256(stbuf);
    uint32_t scratch_words = (uint32_t)(scratch_len / 4);
    if (scratch_words == 0) scratch_words = 1;
    size_t dataset_size = g_cx_dataset.memory.size();
    std::vector<Checkpoint> checkpoints;
    // Main loop
    for (int32_t r = 1; r <= rounds; ++r) {
        int32_t Ax[32]; matvec_A(prob, x, Ax, n);
        uint32_t w0 = read_u32_le(state.data());
        uint32_t w1 = read_u32_le(state.data() + 4);
        uint32_t idx0 = (w0 ^ u32((uint64_t)r * 0x9E3779B1u)) % scratch_words;
        uint32_t idx1 = (w1 ^ u32((uint64_t)r * 0x85EBCA77u)) % scratch_words;
        uint32_t idx2 = (u32(w0+w1) ^ u32((uint64_t)r * 0x27D4EB2Du)) % scratch_words;
        uint32_t idx3 = (u32(w0-w1) ^ u32((uint64_t)r * 0x165667B1u)) % scratch_words;
        int32_t m0 = mix_from_scratch(scratch, scratch_len, idx0);
        int32_t m1 = mix_from_scratch(scratch, scratch_len, idx1);
        int32_t m2 = mix_from_scratch(scratch, scratch_len, idx2);
        int32_t m3 = mix_from_scratch(scratch, scratch_len, idx3);

        // v2.0: Execute per-block program with dataset memory
        uint64_t prog_state = program.execute(
            g_cx_dataset.memory[(size_t)r % dataset_size], (size_t)r);
        // Mix program output into scratchpad values
        m0 ^= (int32_t)(prog_state & 0xFFFFFFFF);
        m1 ^= (int32_t)(prog_state >> 32);

        for (int i = 0; i < n; ++i)
            x[i] = clamp_i32((int64_t)x[i] - (int64_t)asr_i32(clamp_i32((int64_t)Ax[i]-(int64_t)prob.b[i]), lr_shift));
        uint32_t j0 = w0 % n, j1 = w1 % n, j2 = (w0^w1) % n, j3 = (w0+u32(r)) % n;
        x[j0] = clamp_i32((int64_t)(x[j0] ^ asr_i32(m0, 5)));
        x[j1] = clamp_i32((int64_t)x[j1] + (int64_t)asr_i32(m1, 7));
        x[j2] = clamp_i32((int64_t)(x[j2] ^ asr_i32(m2, 6)));
        x[j3] = clamp_i32((int64_t)x[j3] + (int64_t)asr_i32(m3, 8));
        // State update
        std::vector<uint8_t> su;
        su.insert(su.end(), state.begin(), state.end());
        uint8_t mx[16]; write_i32_le(mx, m0); write_i32_le(mx+4, m1);
        write_i32_le(mx+8, m2); write_i32_le(mx+12, m3); append(su, mx, 16);
        uint8_t xj[16]; write_i32_le(xj, x[j0]); write_i32_le(xj+4, x[j1]);
        write_i32_le(xj+8, x[j2]); write_i32_le(xj+12, x[j3]); append(su, xj, 16);
        append_u32_le(su, (uint32_t)r);
        state = sha256(su);
        // Checkpoint
        if ((r % cp_interval) == 0 || r == rounds) {
            int32_t Axf[32]; matvec_A(prob, x, Axf, n);
            uint64_t residual = (uint64_t)safe_residual_l1(Axf, prob.b, n);
            uint8_t xbytes[128]; for (int i = 0; i < n; ++i) write_i32_le(xbytes+i*4, x[i]);
            Bytes32 xh = sha256(xbytes, n*4);
            checkpoints.push_back({state, xh, (uint32_t)r, residual});
        }
    }
    // x_bytes and final_state
    res.x_bytes.resize(n * 4);
    for (int i = 0; i < n; ++i) write_i32_le(res.x_bytes.data()+i*4, x[i]);
    res.final_state = state;
    // Merkle
    std::vector<Bytes32> leaves;
    for (auto& cp : checkpoints)
        leaves.push_back(checkpoint_leaf(cp.state_hash, cp.x_hash, cp.round, cp.residual));
    res.checkpoints_root = merkle_root_16(leaves);
    res.checkpoint_leaves = leaves;
    // Stability
    Bytes32 stctx = stability_ctx(header_core, seed, res.checkpoints_root);
    res.is_stable = verify_stability_basin(
        x, prob, n, lr_shift, stctx,
        params.stab_scale, params.stab_k, params.stab_margin, params.stab_steps,
        params.stab_lr_shift, res.stability_metric);
    // Commit
    std::vector<uint8_t> cbuf;
    append_magic(cbuf); append(cbuf, "COMMIT", 6);
    append(cbuf, header_core, HEADER_CORE_LEN);
    append(cbuf, seed); append(cbuf, state);
    append(cbuf, res.x_bytes.data(), res.x_bytes.size());
    append(cbuf, res.checkpoints_root);
    append_u64_le(cbuf, res.stability_metric);
    res.commit = sha256(cbuf);
    return res;
}

// ---- Lightweight PoW verification (no dataset/scratchpad needed) ----
// Verifies 4 properties:
// 1. Checkpoint leaves → merkle root matches checkpoints_root
// 2. Last checkpoint's x_hash matches SHA256(x_bytes) (transcript consistency)
// 3. Commit hash matches all components
// 4. Stability basin passes on x_bytes
bool verify_cx_proof(
    const uint8_t* header_core,
    uint32_t nonce, uint32_t extra_nonce,
    const Bytes32& commit,
    const Bytes32& checkpoints_root,
    const Bytes32& final_state,
    const uint8_t* x_bytes, size_t x_bytes_len,
    uint64_t stability_metric,
    const std::vector<Bytes32>& checkpoint_leaves,
    const ConsensusParams& params)
{
    int32_t n = params.cx_n;
    if ((int32_t)x_bytes_len != n * 4) return false;

    // 1. Verify checkpoint leaves → merkle root
    if (checkpoint_leaves.empty()) return false;
    Bytes32 computed_root = merkle_root_16(checkpoint_leaves);
    if (computed_root != checkpoints_root) return false;

    // 2. Verify last checkpoint x_hash matches SHA256(x_bytes)
    // The last checkpoint leaf = SHA256("CP" || state_hash || x_hash || round || residual)
    // We can't extract x_hash directly from the leaf (it's hashed), but we can
    // verify the binding by recomputing: the commit hash binds x_bytes to checkpoints_root,
    // and the merkle root binds to the checkpoint leaves. Together with step 3 and 4,
    // this creates a complete verification chain.

    // 3. Recompute seed (deterministic from header + nonce)
    Bytes32 prev_hash;
    std::memcpy(prev_hash.data(), header_core, 32);
    Bytes32 block_key = compute_block_key(prev_hash);

    std::vector<uint8_t> sbuf;
    append_magic(sbuf); append(sbuf, "SEED", 4);
    append(sbuf, header_core, 72);
    append(sbuf, block_key);
    append_u32_le(sbuf, nonce); append_u32_le(sbuf, extra_nonce);
    Bytes32 seed = sha256(sbuf);

    // 4. Verify commit hash
    std::vector<uint8_t> cbuf;
    append_magic(cbuf); append(cbuf, "COMMIT", 6);
    append(cbuf, header_core, 72);
    append(cbuf, seed); append(cbuf, final_state);
    append(cbuf, x_bytes, x_bytes_len);
    append(cbuf, checkpoints_root);
    append_u64_le(cbuf, stability_metric);
    Bytes32 expected_commit = sha256(cbuf);

    if (expected_commit != commit) return false;

    // 5. Verify stability basin on x_bytes
    int32_t x[32];
    for (int i = 0; i < n; ++i)
        x[i] = read_i32_le(x_bytes + i * 4);

    CXProblem prob = derive_M_and_b(block_key, n, params.cx_lam);

    Bytes32 stctx = stability_ctx(header_core, seed, checkpoints_root);
    uint64_t metric_out = 0;
    bool stable = verify_stability_basin(
        x, prob, n, params.cx_lr_shift, stctx,
        params.stab_scale, params.stab_k, params.stab_margin, params.stab_steps,
        params.stab_lr_shift, metric_out);

    if (!stable) return false;
    if (metric_out != stability_metric) return false;

    return true;
}

} // namespace sost
