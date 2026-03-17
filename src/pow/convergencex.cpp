// convergencex.cpp - ConvergenceX v2.0 Proof of Irreversible Convergence
// Consensus-critical: integer-only, deterministic, sequential.
// v2.0: Persistent dataset cache + per-block program generation
#include "sost/pow/convergencex.h"
#include "sost/pow/scratchpad.h"
#include <cstring>
#include <algorithm>
#include <map>
namespace sost {

// ---- CXDataset v2: O(1) single-value access + bulk generation ----
// Each entry is independently computable from (prev_hash, index) via SplitMix64.
// Miner builds full 4GB for speed; verifier recomputes individual entries.
thread_local CXDataset g_cx_dataset;

// Compute a single dataset value at given index (O(1), no 4GB needed)
static uint64_t compute_dataset_seed(const Bytes32& prev_hash) {
    uint64_t seed = 0;
    for (int i = 0; i < 8; ++i)
        seed |= (uint64_t)prev_hash[i] << (i * 8);
    return seed;
}

uint64_t compute_single_dataset_value(const Bytes32& prev_hash, uint64_t index) {
    // SplitMix64 indexed: each entry derived independently from (seed, index)
    uint64_t seed = compute_dataset_seed(prev_hash);
    uint64_t state = seed + (index + 1) * 0x9E3779B97F4A7C15ULL; // golden ratio
    state ^= (state >> 33);
    state *= 0xff51afd7ed558ccdULL;
    state ^= (state >> 33);
    state *= 0xc4ceb9fe1a85ec53ULL;
    state ^= (state >> 33);
    return state;
}

void CXDataset::generate(const Bytes32& block_prev_hash) {
    seed_hash = block_prev_hash;
    memory.resize(512ULL * 1024 * 1024); // 4GB as uint64_t
    // Bulk generation: identical to compute_single_dataset_value for each index
    uint64_t seed = compute_dataset_seed(block_prev_hash);
    for (size_t i = 0; i < memory.size(); i++) {
        uint64_t state = seed + (i + 1) * 0x9E3779B97F4A7C15ULL;
        state ^= (state >> 33);
        state *= 0xff51afd7ed558ccdULL;
        state ^= (state >> 33);
        state *= 0xc4ceb9fe1a85ec53ULL;
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
    int32_t seg_len = CX_SEGMENT_LEN;
    int32_t nseg = (rounds + seg_len - 1) / seg_len;
    // Segment boundary tracking
    std::vector<SegmentLeaf> seg_leaves;
    seg_leaves.reserve(nseg);
    Bytes32 seg_state_start = state;
    uint8_t seg_xbuf[128];
    for (int i = 0; i < n; ++i) write_i32_le(seg_xbuf+i*4, x[i]);
    Bytes32 seg_x_start_hash = sha256(seg_xbuf, n*4);
    int32_t seg_Ax_start[32]; matvec_A(prob, x, seg_Ax_start, n);
    uint64_t seg_residual_start = (uint64_t)safe_residual_l1(seg_Ax_start, prob.b, n);
    int32_t cur_seg = 0;
    int32_t cur_seg_start = 1;

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

        uint64_t prog_state = program.execute(
            g_cx_dataset.memory[(size_t)r % dataset_size], (size_t)r);
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
        uint8_t mx_buf[16]; write_i32_le(mx_buf, m0); write_i32_le(mx_buf+4, m1);
        write_i32_le(mx_buf+8, m2); write_i32_le(mx_buf+12, m3); append(su, mx_buf, 16);
        uint8_t xj_buf[16]; write_i32_le(xj_buf, x[j0]); write_i32_le(xj_buf+4, x[j1]);
        write_i32_le(xj_buf+8, x[j2]); write_i32_le(xj_buf+12, x[j3]); append(su, xj_buf, 16);
        append_u32_le(su, (uint32_t)r);
        state = sha256(su);
        // Checkpoint (every cp_interval)
        if ((r % cp_interval) == 0 || r == rounds) {
            int32_t Axf[32]; matvec_A(prob, x, Axf, n);
            uint64_t residual = (uint64_t)safe_residual_l1(Axf, prob.b, n);
            uint8_t xbytes_cp[128]; for (int i = 0; i < n; ++i) write_i32_le(xbytes_cp+i*4, x[i]);
            Bytes32 xh = sha256(xbytes_cp, n*4);
            checkpoints.push_back({state, xh, (uint32_t)r, residual});
        }
        // Segment boundary: end of segment or end of rounds
        int32_t seg_end_round = cur_seg_start + seg_len - 1;
        if (seg_end_round > rounds) seg_end_round = rounds;
        if (r == seg_end_round) {
            uint8_t xb_end[128]; for (int i = 0; i < n; ++i) write_i32_le(xb_end+i*4, x[i]);
            Bytes32 x_end_hash = sha256(xb_end, n*4);
            int32_t Ax_end[32]; matvec_A(prob, x, Ax_end, n);
            uint64_t res_end = (uint64_t)safe_residual_l1(Ax_end, prob.b, n);
            SegmentLeaf sl;
            sl.segment_index = (uint32_t)cur_seg;
            sl.round_start = (uint32_t)cur_seg_start;
            sl.round_end = (uint32_t)r;
            sl.state_start = seg_state_start;
            sl.state_end = state;
            sl.x_start_hash = seg_x_start_hash;
            sl.x_end_hash = x_end_hash;
            sl.residual_start = seg_residual_start;
            sl.residual_end = res_end;
            seg_leaves.push_back(sl);
            // Prepare next segment start
            cur_seg++;
            cur_seg_start = r + 1;
            seg_state_start = state;
            seg_x_start_hash = x_end_hash;
            seg_residual_start = res_end;
        }
    }
    // x_bytes and final_state
    res.x_bytes.resize(n * 4);
    for (int i = 0; i < n; ++i) write_i32_le(res.x_bytes.data()+i*4, x[i]);
    res.final_state = state;
    // Checkpoint merkle
    std::vector<Bytes32> leaves;
    for (auto& cp : checkpoints)
        leaves.push_back(checkpoint_leaf(cp.state_hash, cp.x_hash, cp.round, cp.residual));
    res.checkpoints_root = merkle_root_16(leaves);
    res.checkpoint_leaves = leaves;
    // Segment merkle
    res.segment_leaves = seg_leaves;
    std::vector<Bytes32> seg_leaf_hashes;
    for (auto& sl : seg_leaves) {
        std::vector<uint8_t> lb;
        append(lb, "SEG", 3);
        append_u32_le(lb, sl.segment_index);
        append_u32_le(lb, sl.round_start);
        append_u32_le(lb, sl.round_end);
        append(lb, sl.state_start); append(lb, sl.state_end);
        append(lb, sl.x_start_hash); append(lb, sl.x_end_hash);
        append_u64_le(lb, sl.residual_start); append_u64_le(lb, sl.residual_end);
        seg_leaf_hashes.push_back(sha256(lb));
    }
    res.segments_root = merkle_root_16(seg_leaf_hashes);
    // Stability
    Bytes32 stctx = stability_ctx(header_core, seed, res.checkpoints_root);
    res.is_stable = verify_stability_basin(
        x, prob, n, lr_shift, stctx,
        params.stab_scale, params.stab_k, params.stab_margin, params.stab_steps,
        params.stab_lr_shift, res.stability_metric);
    // Commit V3: includes segments_root + profile_index (consensus-critical)
    // The profile_index binds the stability parameters to the commit,
    // preventing miners from using easier params than consensus requires.
    std::vector<uint8_t> cbuf;
    append_magic(cbuf); append(cbuf, "COMMIT", 6);
    append(cbuf, header_core, HEADER_CORE_LEN);
    append(cbuf, seed); append(cbuf, state);
    append(cbuf, res.x_bytes.data(), res.x_bytes.size());
    append(cbuf, res.checkpoints_root);
    append(cbuf, res.segments_root);
    append_u64_le(cbuf, res.stability_metric);
    // Profile index: i8 signed, committed to prevent profile downgrade attacks
    int8_t pi8 = (int8_t)params.stab_profile_index;
    cbuf.push_back((uint8_t)pi8);
    res.commit = sha256(cbuf);
    return res;
}

// ---- Segment leaf hash (consensus-critical serialization) ----
static Bytes32 hash_segment_leaf(const SegmentLeaf& sl) {
    std::vector<uint8_t> lb;
    append(lb, "SEG", 3);
    append_u32_le(lb, sl.segment_index);
    append_u32_le(lb, sl.round_start);
    append_u32_le(lb, sl.round_end);
    append(lb, sl.state_start); append(lb, sl.state_end);
    append(lb, sl.x_start_hash); append(lb, sl.x_end_hash);
    append_u64_le(lb, sl.residual_start); append_u64_le(lb, sl.residual_end);
    return sha256(lb);
}

// ---- Merkle proof verification ----
static bool verify_merkle_proof(const Bytes32& leaf_hash, const std::vector<Bytes32>& path,
                                 uint32_t index, const Bytes32& root) {
    Bytes32 current = leaf_hash;
    uint32_t idx = index;
    for (const auto& sibling : path) {
        std::vector<uint8_t> buf;
        if (idx & 1) { append(buf, sibling); append(buf, current); }
        else         { append(buf, current); append(buf, sibling); }
        current = sha256(buf);
        idx >>= 1;
    }
    return current == root;
}

// ---- Challenge derivation (deterministic from commit + segments_root) ----
// Phase 1: derive segment indices (only needs nseg count)
static Bytes32 compute_challenge_seed(const Bytes32& commit, const Bytes32& segments_root) {
    std::vector<uint8_t> cseed_buf;
    append_magic(cseed_buf); append(cseed_buf, "CHAL", 4);
    append(cseed_buf, commit); append(cseed_buf, segments_root);
    return sha256(cseed_buf);
}

static std::vector<uint32_t> derive_segment_indices(const Bytes32& challenge_seed,
                                                      int32_t nseg, int32_t num_chal_segs) {
    std::vector<uint32_t> indices;
    uint32_t attempt = 0;
    while ((int32_t)indices.size() < num_chal_segs && attempt < 1000) {
        std::vector<uint8_t> ibuf;
        append_magic(ibuf); append(ibuf, "CHIDX", 5);
        append(ibuf, challenge_seed); append_u32_le(ibuf, attempt);
        Bytes32 h = sha256(ibuf);
        uint32_t idx = read_u32_le(h.data()) % (uint32_t)nseg;
        bool dup = false;
        for (auto si : indices) if (si == idx) { dup = true; break; }
        if (!dup) indices.push_back(idx);
        attempt++;
    }
    return indices;
}

// Phase 2: derive round indices (uses round_start/round_end from challenged segments)
static std::vector<uint32_t> derive_round_indices(const Bytes32& challenge_seed,
                                                    uint32_t chal_idx, uint32_t round_start,
                                                    uint32_t round_end, int32_t steps_per_seg) {
    std::vector<uint32_t> rounds;
    uint32_t seg_actual_len = round_end - round_start + 1;
    for (int32_t j = 0; j < steps_per_seg; ++j) {
        std::vector<uint8_t> rbuf;
        append_magic(rbuf); append(rbuf, "CHRD", 4);
        append(rbuf, challenge_seed); append_u32_le(rbuf, chal_idx); append_u32_le(rbuf, (uint32_t)j);
        Bytes32 rh = sha256(rbuf);
        uint32_t round_off = read_u32_le(rh.data()) % seg_actual_len;
        rounds.push_back(round_start + round_off);
    }
    return rounds;
}

// Combined helper for miner (has all segment leaves)
static void derive_challenges(const Bytes32& commit, const Bytes32& segments_root,
                               int32_t nseg, int32_t num_chal_segs, int32_t steps_per_seg,
                               const std::vector<SegmentLeaf>& seg_leaves,
                               std::vector<uint32_t>& out_seg_indices,
                               std::vector<std::vector<uint32_t>>& out_round_indices) {
    Bytes32 challenge_seed = compute_challenge_seed(commit, segments_root);
    out_seg_indices = derive_segment_indices(challenge_seed, nseg, num_chal_segs);
    out_round_indices.resize(out_seg_indices.size());
    for (size_t i = 0; i < out_seg_indices.size(); ++i) {
        uint32_t si = out_seg_indices[i];
        out_round_indices[i] = derive_round_indices(challenge_seed, (uint32_t)i,
            seg_leaves[si].round_start, seg_leaves[si].round_end, steps_per_seg);
    }
}

// ---- Verify CX Proof V2 (Transcript V2) ----
// 11-phase verification: sanity, checkpoints, segments, seed, commit, challenges,
// boundaries, round witnesses, stability, metric, target
bool verify_cx_proof(
    const uint8_t* header_core,
    uint32_t nonce, uint32_t extra_nonce,
    const Bytes32& commit,
    const Bytes32& checkpoints_root,
    const Bytes32& segments_root,
    const Bytes32& final_state,
    const uint8_t* x_bytes, size_t x_bytes_len,
    uint64_t stability_metric,
    const std::vector<Bytes32>& checkpoint_leaves,
    const std::vector<SegmentProof>& segment_proofs,
    const std::vector<RoundWitness>& round_witnesses,
    const ConsensusParams& params)
{
    setbuf(stdout, NULL); // Disable buffering so all printf output appears immediately
    int32_t n = params.cx_n;
    printf("[CX-VERIFY] Phase 1: sanity (x_bytes_len=%zu, n*4=%d, cp_leaves=%zu)\n",
            x_bytes_len, n*4, checkpoint_leaves.size());
    // Phase 1: Sanity
    if ((int32_t)x_bytes_len != n * 4) { printf("[CX-VERIFY] Phase 1 FAILED: x_bytes_len=%zu != n*4=%d\n", x_bytes_len, n*4); return false; }
    if (checkpoint_leaves.empty()) { printf("[CX-VERIFY] Phase 1 FAILED: checkpoint_leaves empty\n"); return false; }

    // Phase 2: Checkpoint merkle root
    printf("[CX-VERIFY] Phase 2: checkpoint merkle (%zu leaves)\n", checkpoint_leaves.size());
    Bytes32 cp_root = merkle_root_16(checkpoint_leaves);
    if (cp_root != checkpoints_root) { printf("[CX-VERIFY] Phase 2 FAILED: checkpoints_root mismatch expected=%s got=%s\n", hex(checkpoints_root).c_str(), hex(cp_root).c_str()); return false; }

    // Phase 3: Segment proofs → segments_root
    printf("[CX-VERIFY] Phase 3: segment merkle proofs (%zu proofs)\n", segment_proofs.size());
    for (size_t spi = 0; spi < segment_proofs.size(); ++spi) {
        const auto& sp = segment_proofs[spi];
        Bytes32 lh = hash_segment_leaf(sp.leaf);
        if (!verify_merkle_proof(lh, sp.merkle_path, sp.leaf.segment_index, segments_root)) {
            printf("[CX-VERIFY] Phase 3 FAILED: segment proof %zu invalid (seg_idx=%u, path_len=%zu, leaf=%s, root=%s)\n",
                    spi, sp.leaf.segment_index, sp.merkle_path.size(), hex(lh).substr(0,16).c_str(), hex(segments_root).substr(0,16).c_str());
            return false;
        }
    }

    // Phase 4: Seed
    printf("[CX-VERIFY] Phase 4: seed recompute (nonce=%u extra=%u)\n", nonce, extra_nonce);
    Bytes32 prev_hash;
    std::memcpy(prev_hash.data(), header_core, 32);
    Bytes32 block_key = compute_block_key(prev_hash);
    std::vector<uint8_t> sbuf;
    append_magic(sbuf); append(sbuf, "SEED", 4);
    append(sbuf, header_core, 72); append(sbuf, block_key);
    append_u32_le(sbuf, nonce); append_u32_le(sbuf, extra_nonce);
    Bytes32 seed = sha256(sbuf);

    // Phase 5: Commit binding (V3 format: includes segments_root + profile_index)
    printf("[CX-VERIFY] Phase 5: commit binding (profile_index=%d)\n", params.stab_profile_index);
    std::vector<uint8_t> cbuf;
    append_magic(cbuf); append(cbuf, "COMMIT", 6);
    append(cbuf, header_core, 72); append(cbuf, seed); append(cbuf, final_state);
    append(cbuf, x_bytes, x_bytes_len);
    append(cbuf, checkpoints_root); append(cbuf, segments_root);
    append_u64_le(cbuf, stability_metric);
    int8_t pi8 = (int8_t)params.stab_profile_index;
    cbuf.push_back((uint8_t)pi8);
    Bytes32 computed_commit = sha256(cbuf);
    if (computed_commit != commit) {
        printf("[CX-VERIFY] Phase 5 FAILED: commit mismatch expected=%s got=%s (cbuf_len=%zu metric=%llu)\n",
                hex(commit).substr(0,16).c_str(), hex(computed_commit).substr(0,16).c_str(), cbuf.size(), (unsigned long long)stability_metric);
        return false;
    }

    // Phase 6: Challenge derivation — verify proofs correspond to correct challenges
    printf("[CX-VERIFY] Phase 6: challenge derivation (rounds=%d seg_len=%d)\n", params.cx_rounds, CX_SEGMENT_LEN);
    int32_t nseg = (params.cx_rounds + CX_SEGMENT_LEN - 1) / CX_SEGMENT_LEN;
    Bytes32 challenge_seed = compute_challenge_seed(commit, segments_root);
    int32_t actual_chal = std::min((int32_t)CX_CHAL_SEGMENTS, nseg);
    std::vector<uint32_t> expected_seg_idx = derive_segment_indices(challenge_seed, nseg, actual_chal);
    // Verify segment proofs match expected indices
    if ((int32_t)segment_proofs.size() != actual_chal) {
        printf("[CX-VERIFY] Phase 6 FAILED: segment_proofs.size()=%zu != actual_chal=%d (nseg=%d)\n",
                segment_proofs.size(), actual_chal, nseg);
        return false;
    }
    for (int i = 0; i < actual_chal; ++i) {
        if (segment_proofs[i].leaf.segment_index != expected_seg_idx[i]) {
            printf("[CX-VERIFY] Phase 6 FAILED: seg_proof[%d].segment_index=%u != expected=%u\n",
                    i, segment_proofs[i].leaf.segment_index, expected_seg_idx[i]);
            return false;
        }
    }
    // Derive expected round indices using round_start/end from verified proofs
    std::vector<std::vector<uint32_t>> expected_round_idx(expected_seg_idx.size());
    for (size_t i = 0; i < expected_seg_idx.size(); ++i) {
        expected_round_idx[i] = derive_round_indices(challenge_seed, (uint32_t)i,
            segment_proofs[i].leaf.round_start, segment_proofs[i].leaf.round_end, CX_CHAL_STEPS);
    }

    // Phase 7: Boundary coherence
    printf("[CX-VERIFY] Phase 7: boundary coherence\n");
    for (size_t spi = 0; spi < segment_proofs.size(); ++spi) {
        const auto& sp = segment_proofs[spi];
        if (sp.leaf.round_start > sp.leaf.round_end) { printf("[CX-VERIFY] Phase 7 FAILED: seg %zu start %u > end %u\n", spi, sp.leaf.round_start, sp.leaf.round_end); return false; }
        if (sp.leaf.round_end > (uint32_t)params.cx_rounds) { printf("[CX-VERIFY] Phase 7 FAILED: seg %zu end %u > rounds %d\n", spi, sp.leaf.round_end, params.cx_rounds); return false; }
    }

    // Phase 8: Round witness verification
    printf("[CX-VERIFY] Phase 8: round witnesses (%zu total, %d chal segs, %d steps each)\n",
            round_witnesses.size(), actual_chal, CX_CHAL_STEPS);
    CXProblem prob = derive_M_and_b(block_key, n, params.cx_lam);
    CXProgram program; program.generate(block_key);
    Bytes32 epoch_key = epoch_scratch_key(0, nullptr);
    size_t dataset_size = 512ULL * 1024 * 1024;
    int32_t lr_shift = params.cx_lr_shift;

    size_t rw_idx = 0;
    for (int seg_i = 0; seg_i < actual_chal && seg_i < (int)expected_round_idx.size(); ++seg_i) {
        for (int step_j = 0; step_j < CX_CHAL_STEPS && step_j < (int)expected_round_idx[seg_i].size(); ++step_j) {
            if (rw_idx >= round_witnesses.size()) { printf("[CX-VERIFY] Phase 8 FAILED: rw_idx=%zu >= rw.size=%zu\n", rw_idx, round_witnesses.size()); return false; }
            const auto& rw = round_witnesses[rw_idx++];
            uint32_t r = expected_round_idx[seg_i][step_j];
            if (rw.round_index != r) { printf("[CX-VERIFY] Phase 8 FAILED: rw[%zu].round=%u != expected=%u (seg=%d step=%d)\n", rw_idx-1, rw.round_index, r, seg_i, step_j); return false; }

            // Recompute scratch indices from state_before
            uint32_t scratch_mb = params.cx_scratch_mb;
            uint32_t scratch_words = (uint32_t)((uint64_t)scratch_mb * 1024 * 1024 / 4);
            if (scratch_words == 0) scratch_words = 1;
            uint32_t w0 = read_u32_le(rw.state_before.data());
            uint32_t w1 = read_u32_le(rw.state_before.data() + 4);
            uint32_t exp_idx0 = (w0 ^ u32((uint64_t)r * 0x9E3779B1u)) % scratch_words;
            uint32_t exp_idx1 = (w1 ^ u32((uint64_t)r * 0x85EBCA77u)) % scratch_words;
            uint32_t exp_idx2 = (u32(w0+w1) ^ u32((uint64_t)r * 0x27D4EB2Du)) % scratch_words;
            uint32_t exp_idx3 = (u32(w0-w1) ^ u32((uint64_t)r * 0x165667B1u)) % scratch_words;
            if (rw.scratch_indices[0] != exp_idx0 || rw.scratch_indices[1] != exp_idx1 ||
                rw.scratch_indices[2] != exp_idx2 || rw.scratch_indices[3] != exp_idx3) {
                printf("[CX-VERIFY] Phase 8 FAILED: scratch_indices mismatch at round %u (got [%u,%u,%u,%u] expected [%u,%u,%u,%u])\n",
                        r, rw.scratch_indices[0],rw.scratch_indices[1],rw.scratch_indices[2],rw.scratch_indices[3],
                        exp_idx0,exp_idx1,exp_idx2,exp_idx3);
                return false;
            }

            // Verify scratch values by recomputing from scratchpad (O(1) per value)
            for (int vi = 0; vi < 4; ++vi) {
                uint32_t byte_off = (rw.scratch_indices[vi] * 4) % ((uint32_t)scratch_mb * 1024 * 1024 - 4);
                uint32_t block_idx = byte_off / 32;
                uint32_t byte_within = byte_off % 32;
                Bytes32 block = compute_single_scratch_block(epoch_key, block_idx);
                int32_t expected_val = read_i32_le(block.data() + byte_within);
                if (rw.scratch_values[vi] != expected_val) {
                    printf("[CX-VERIFY] Phase 8 FAILED: scratch_value[%d] mismatch at round %u idx=%u (got %d expected %d, byte_off=%u blk=%u within=%u)\n",
                            vi, r, rw.scratch_indices[vi], rw.scratch_values[vi], expected_val, byte_off, block_idx, byte_within);
                    return false;
                }
            }

            // Verify dataset value
            uint64_t exp_ds = compute_single_dataset_value(prev_hash, (uint64_t)r % dataset_size);
            if (rw.dataset_value != exp_ds) {
                printf("[CX-VERIFY] Phase 8 FAILED: dataset_value mismatch at round %u (got %llu expected %llu, idx=%llu)\n",
                        r, (unsigned long long)rw.dataset_value, (unsigned long long)exp_ds, (unsigned long long)((uint64_t)r % dataset_size));
                return false;
            }

            // Verify program output
            uint64_t exp_prog = program.execute(rw.dataset_value, (size_t)r);
            if (rw.program_output != exp_prog) {
                printf("[CX-VERIFY] Phase 8 FAILED: program_output mismatch at round %u (got %llu expected %llu)\n",
                        r, (unsigned long long)rw.program_output, (unsigned long long)exp_prog);
                return false;
            }

            // Verify round transition: x_before → x_after
            int32_t Ax[32]; matvec_A(prob, rw.x_before.data(), Ax, n);
            int32_t m0 = rw.scratch_values[0], m1 = rw.scratch_values[1];
            int32_t m2 = rw.scratch_values[2], m3 = rw.scratch_values[3];
            m0 ^= (int32_t)(rw.program_output & 0xFFFFFFFF);
            m1 ^= (int32_t)(rw.program_output >> 32);
            int32_t x_exp[32];
            for (int i = 0; i < n; ++i)
                x_exp[i] = clamp_i32((int64_t)rw.x_before[i] - (int64_t)asr_i32(clamp_i32((int64_t)Ax[i]-(int64_t)prob.b[i]), lr_shift));
            uint32_t j0 = w0 % n, j1 = w1 % n, j2 = (w0^w1) % n, j3 = (w0+u32(r)) % n;
            x_exp[j0] = clamp_i32((int64_t)(x_exp[j0] ^ asr_i32(m0, 5)));
            x_exp[j1] = clamp_i32((int64_t)x_exp[j1] + (int64_t)asr_i32(m1, 7));
            x_exp[j2] = clamp_i32((int64_t)(x_exp[j2] ^ asr_i32(m2, 6)));
            x_exp[j3] = clamp_i32((int64_t)x_exp[j3] + (int64_t)asr_i32(m3, 8));
            for (int i = 0; i < n; ++i) {
                if (x_exp[i] != rw.x_after[i]) {
                    printf("[CX-VERIFY] Phase 8 FAILED: x_after[%d] mismatch at round %u (got %d expected %d)\n", i, r, rw.x_after[i], x_exp[i]);
                    return false;
                }
            }

            // Verify state transition
            std::vector<uint8_t> su;
            su.insert(su.end(), rw.state_before.begin(), rw.state_before.end());
            uint8_t mx_v[16]; write_i32_le(mx_v, m0); write_i32_le(mx_v+4, m1);
            write_i32_le(mx_v+8, m2); write_i32_le(mx_v+12, m3); append(su, mx_v, 16);
            uint8_t xj_v[16]; write_i32_le(xj_v, x_exp[j0]); write_i32_le(xj_v+4, x_exp[j1]);
            write_i32_le(xj_v+8, x_exp[j2]); write_i32_le(xj_v+12, x_exp[j3]); append(su, xj_v, 16);
            append_u32_le(su, r);
            Bytes32 exp_state = sha256(su);
            if (exp_state != rw.state_after) {
                printf("[CX-VERIFY] Phase 8 FAILED: state_after mismatch at round %u (got=%s exp=%s)\n",
                        r, hex(rw.state_after).substr(0,16).c_str(), hex(exp_state).substr(0,16).c_str());
                return false;
            }
            printf("[CX-VERIFY] Phase 8: round %u OK (seg=%d step=%d)\n", r, seg_i, step_j);
        }
    }

    // Phase 9: Stability basin
    printf("[CX-VERIFY] Phase 9: stability basin (scale=%d k=%d margin=%d steps=%d)\n",
            params.stab_scale, params.stab_k, params.stab_margin, params.stab_steps);
    int32_t x[32];
    for (int i = 0; i < n; ++i) x[i] = read_i32_le(x_bytes + i * 4);
    Bytes32 stctx = stability_ctx(header_core, seed, checkpoints_root);
    uint64_t metric_out = 0;
    if (!verify_stability_basin(x, prob, n, lr_shift, stctx,
            params.stab_scale, params.stab_k, params.stab_margin, params.stab_steps,
            params.stab_lr_shift, metric_out)) {
        printf("[CX-VERIFY] Phase 9 FAILED: stability basin test failed (metric_out=%llu)\n", (unsigned long long)metric_out);
        return false;
    }

    // Phase 10: Metric
    printf("[CX-VERIFY] Phase 10: metric check (got=%llu expected=%llu)\n", (unsigned long long)metric_out, (unsigned long long)stability_metric);
    if (metric_out != stability_metric) {
        printf("[CX-VERIFY] Phase 10 FAILED: metric mismatch got=%llu expected=%llu\n", (unsigned long long)metric_out, (unsigned long long)stability_metric);
        return false;
    }

    printf("[CX-VERIFY] ALL PHASES PASSED\n");
    return true;
}

// ---- Build merkle path for leaf at index ----
std::vector<Bytes32> build_merkle_path(const std::vector<Bytes32>& leaf_hashes, uint32_t index) {
    std::vector<Bytes32> path;
    if (leaf_hashes.empty()) return path;
    std::vector<Bytes32> tree = leaf_hashes;
    uint32_t idx = index;
    while (tree.size() > 1) {
        if (tree.size() % 2 == 1) tree.push_back(tree.back());
        std::vector<Bytes32> next;
        for (size_t i = 0; i < tree.size(); i += 2) {
            uint32_t pair_idx = idx & ~1u;
            if (i == pair_idx) {
                path.push_back(tree[(idx & 1) ? i : i + 1]);
            }
            std::vector<uint8_t> buf;
            append(buf, tree[i]); append(buf, tree[i + 1]);
            next.push_back(sha256(buf));
        }
        idx >>= 1;
        tree = next;
    }
    return path;
}

// ---- Generate Transcript V2 witnesses by replaying challenged rounds ----
void generate_transcript_witnesses(
    CXAttemptResult& res,
    const uint8_t* scratch, size_t scratch_len,
    const Bytes32& block_key,
    uint32_t nonce, uint32_t extra_nonce,
    const ConsensusParams& params,
    const uint8_t* header_core,
    int32_t epoch)
{
    int32_t n = params.cx_n;
    int32_t rounds = params.cx_rounds;
    int32_t lr_shift = params.cx_lr_shift;
    int32_t seg_len = CX_SEGMENT_LEN;
    int32_t nseg = (rounds + seg_len - 1) / seg_len;

    // Derive challenges from commit + segments_root
    std::vector<uint32_t> chal_seg_idx;
    std::vector<std::vector<uint32_t>> chal_round_idx;
    int32_t actual_chal = std::min((int32_t)CX_CHAL_SEGMENTS, nseg);
    derive_challenges(res.commit, res.segments_root, nseg,
                      actual_chal, CX_CHAL_STEPS,
                      res.segment_leaves, chal_seg_idx, chal_round_idx);

    // Build segment leaf hashes for merkle paths
    std::vector<Bytes32> seg_leaf_hashes;
    for (auto& sl : res.segment_leaves)
        seg_leaf_hashes.push_back(hash_segment_leaf(sl));

    // Generate SegmentProofs
    res.segment_proofs.clear();
    for (auto si : chal_seg_idx) {
        SegmentProof sp;
        sp.leaf = res.segment_leaves[si];
        sp.merkle_path = build_merkle_path(seg_leaf_hashes, si);
        res.segment_proofs.push_back(sp);
    }

    // Collect all challenged rounds (sorted for efficient replay)
    struct ChalRound { uint32_t round; size_t proof_idx; size_t step_idx; };
    std::vector<ChalRound> all_rounds;
    for (size_t i = 0; i < chal_seg_idx.size(); ++i)
        for (size_t j = 0; j < chal_round_idx[i].size(); ++j)
            all_rounds.push_back({chal_round_idx[i][j], i, j});
    std::sort(all_rounds.begin(), all_rounds.end(),
              [](const ChalRound& a, const ChalRound& b){ return a.round < b.round; });

    // Replay the full loop, only capturing witnesses for challenged rounds
    Bytes32 prev_hash;
    std::memcpy(prev_hash.data(), header_core, 32);
    if (!g_cx_dataset.is_valid_for(prev_hash)) g_cx_dataset.generate(prev_hash);
    CXProgram program; program.generate(block_key);

    std::vector<uint8_t> sbuf;
    append_magic(sbuf); append(sbuf, "SEED", 4);
    append(sbuf, header_core, HEADER_CORE_LEN); append(sbuf, block_key);
    append_u32_le(sbuf, nonce); append_u32_le(sbuf, extra_nonce);
    Bytes32 seed = sha256(sbuf);

    std::vector<uint8_t> x0seed;
    append_magic(x0seed); append(x0seed, "X0", 2); append(x0seed, seed);
    auto rawx = prng_bytes(sha256(x0seed), n * 4);
    int32_t x[32];
    for (int i = 0; i < n; ++i) x[i] = asr_i32(read_i32_le(rawx.data() + i*4), 4);

    CXProblem prob = derive_M_and_b(block_key, n, params.cx_lam);
    std::vector<uint8_t> stbuf;
    append_magic(stbuf); append(stbuf, "ST", 2); append(stbuf, seed);
    Bytes32 state = sha256(stbuf);

    uint32_t scratch_words = (uint32_t)(scratch_len / 4);
    if (scratch_words == 0) scratch_words = 1;
    size_t dataset_size = g_cx_dataset.memory.size();

    // Map round → witness slots
    std::map<uint32_t, std::vector<size_t>> round_to_slots;
    for (size_t ri = 0; ri < all_rounds.size(); ++ri)
        round_to_slots[all_rounds[ri].round].push_back(ri);

    std::vector<RoundWitness> witnesses(all_rounds.size());

    for (int32_t r = 1; r <= rounds; ++r) {
        // Check if this round is challenged
        auto it = round_to_slots.find((uint32_t)r);
        bool is_challenged = (it != round_to_slots.end());

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

        uint64_t ds_val = g_cx_dataset.memory[(size_t)r % dataset_size];
        uint64_t prog_out = program.execute(ds_val, (size_t)r);

        // Capture BEFORE program mixing (raw scratch values)
        if (is_challenged) {
            for (auto slot : it->second) {
                auto& rw = witnesses[slot];
                rw.round_index = (uint32_t)r;
                std::copy(x, x + 32, rw.x_before.begin());
                rw.state_before = state;
                rw.scratch_indices = {idx0, idx1, idx2, idx3};
                rw.scratch_values = {m0, m1, m2, m3}; // RAW, before program mixing
                rw.dataset_value = ds_val;
                rw.program_output = prog_out;
            }
        }

        // Apply program mixing
        m0 ^= (int32_t)(prog_out & 0xFFFFFFFF);
        m1 ^= (int32_t)(prog_out >> 32);

        // Apply round transition
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
        uint8_t mx_b[16]; write_i32_le(mx_b, m0); write_i32_le(mx_b+4, m1);
        write_i32_le(mx_b+8, m2); write_i32_le(mx_b+12, m3); append(su, mx_b, 16);
        uint8_t xj_b[16]; write_i32_le(xj_b, x[j0]); write_i32_le(xj_b+4, x[j1]);
        write_i32_le(xj_b+8, x[j2]); write_i32_le(xj_b+12, x[j3]); append(su, xj_b, 16);
        append_u32_le(su, (uint32_t)r);
        state = sha256(su);

        // Capture x_after and state_after if challenged
        if (is_challenged) {
            for (auto slot : it->second) {
                auto& rw = witnesses[slot];
                std::copy(x, x + 32, rw.x_after.begin());
                rw.state_after = state;
            }
        }
    }

    // Reorder witnesses to match challenge order (seg_i, step_j)
    res.round_witnesses.clear();
    for (size_t i = 0; i < chal_seg_idx.size(); ++i) {
        for (size_t j = 0; j < chal_round_idx[i].size(); ++j) {
            uint32_t target_round = chal_round_idx[i][j];
            for (auto& cr : all_rounds) {
                if (cr.round == target_round && cr.proof_idx == i && cr.step_idx == j) {
                    size_t slot = &cr - all_rounds.data();
                    res.round_witnesses.push_back(witnesses[slot]);
                    break;
                }
            }
        }
    }
}

} // namespace sost
