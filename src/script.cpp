// script.cpp — Minimal script engine for SOST multisig
#include "sost/script.h"
#include <openssl/sha.h>
#include <openssl/ripemd.h>
#include <cstring>
#include <algorithm>
#include <stack>

namespace sost {

// ---------------------------------------------------------------------------
// Hash utilities
// ---------------------------------------------------------------------------
static PubKeyHash hash160(const uint8_t* data, size_t len) {
    uint8_t sha[32];
    SHA256(data, len, sha);
    PubKeyHash h;
    RIPEMD160(sha, 32, h.data());
    return h;
}

PubKeyHash hash_script(const Script& script) {
    return hash160(script.data(), script.size());
}

// ---------------------------------------------------------------------------
// Address encoding for sost3 (script hash)
// ---------------------------------------------------------------------------
static const char HEX_C[] = "0123456789abcdef";

std::string script_hash_to_address(const PubKeyHash& sh) {
    std::string addr = SOST3_PREFIX;
    addr.reserve(45);
    for (int i = 0; i < 20; ++i) {
        addr += HEX_C[sh[i] >> 4];
        addr += HEX_C[sh[i] & 0x0F];
    }
    return addr;
}

static int hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + c - 'a';
    if (c >= 'A' && c <= 'F') return 10 + c - 'A';
    return -1;
}

bool address_to_script_hash(const std::string& addr, PubKeyHash& out) {
    if (addr.size() != 45) return false;
    if (addr.substr(0, 5) != SOST3_PREFIX) return false;
    for (int i = 0; i < 20; ++i) {
        int hi = hex_val(addr[5 + i * 2]);
        int lo = hex_val(addr[5 + i * 2 + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return true;
}

bool is_script_hash_address(const std::string& addr) {
    if (addr.size() != 45) return false;
    return addr.substr(0, 5) == SOST3_PREFIX;
}

// ---------------------------------------------------------------------------
// Script construction
// ---------------------------------------------------------------------------

// OP_PUSHDATA1 = 0x4C: next byte is length, then data
constexpr uint8_t OP_PUSHDATA1 = 0x4C;

static void push_data(Script& s, const uint8_t* data, size_t len) {
    if (len <= 75) {
        s.push_back((uint8_t)len);
    } else if (len <= 255) {
        s.push_back(OP_PUSHDATA1);
        s.push_back((uint8_t)len);
    } else {
        // OP_PUSHDATA2 (0x4D): 2-byte length LE. Unlikely needed but safe.
        s.push_back(0x4D);
        s.push_back((uint8_t)(len & 0xFF));
        s.push_back((uint8_t)((len >> 8) & 0xFF));
    }
    s.insert(s.end(), data, data + len);
}

Script make_p2sh_script_pubkey(const PubKeyHash& script_hash) {
    Script s;
    s.push_back(OP_HASH160);
    push_data(s, script_hash.data(), 20);
    s.push_back(OP_EQUAL);
    return s;
}

Script make_multisig_redeem_script(uint32_t m, const std::vector<PubKey>& pubkeys) {
    Script s;
    uint32_t n = (uint32_t)pubkeys.size();
    s.push_back(OP_1 + (uint8_t)(m - 1)); // OP_M
    for (const auto& pk : pubkeys) {
        push_data(s, pk.data(), 33);
    }
    s.push_back(OP_1 + (uint8_t)(n - 1)); // OP_N
    s.push_back(OP_CHECKMULTISIG);
    return s;
}

Script make_p2sh_script_sig(const std::vector<Sig64>& sigs, const Script& redeem_script) {
    Script s;
    s.push_back(OP_0); // dummy for CHECKMULTISIG off-by-one
    for (const auto& sig : sigs) {
        push_data(s, sig.data(), 64);
    }
    push_data(s, redeem_script.data(), redeem_script.size());
    return s;
}

// ---------------------------------------------------------------------------
// Stack-based script evaluator
// ---------------------------------------------------------------------------
using StackItem = std::vector<uint8_t>;

static bool stack_top_truthy(const std::vector<StackItem>& stack) {
    if (stack.empty()) return false;
    const auto& top = stack.back();
    for (auto b : top) if (b != 0) return true;
    return false;
}

static bool eval_ops(
    const Script& script,
    std::vector<StackItem>& stack,
    const ScriptEvalContext& ctx,
    std::string* err)
{
    size_t pc = 0;
    while (pc < script.size()) {
        uint8_t op = script[pc++];

        // OP_0: push empty
        if (op == OP_0) {
            stack.push_back({});
            continue;
        }

        // OP_1 .. OP_16: push number
        if (op >= OP_1 && op <= OP_16) {
            uint8_t val = op - OP_1 + 1;
            stack.push_back({val});
            continue;
        }

        // Push data (1-75 bytes)
        if (op >= OP_PUSHDATA_MIN && op <= OP_PUSHDATA_MAX) {
            size_t len = op;
            if (pc + len > script.size()) {
                if (err) *err = "push: not enough data";
                return false;
            }
            stack.push_back(StackItem(script.begin() + pc, script.begin() + pc + len));
            pc += len;
            continue;
        }

        // OP_PUSHDATA1 (0x4C): next byte = length, then data
        if (op == 0x4C) {
            if (pc >= script.size()) { if (err) *err = "PUSHDATA1: missing length"; return false; }
            size_t len = script[pc++];
            if (pc + len > script.size()) {
                if (err) *err = "PUSHDATA1: not enough data";
                return false;
            }
            stack.push_back(StackItem(script.begin() + pc, script.begin() + pc + len));
            pc += len;
            continue;
        }

        // OP_PUSHDATA2 (0x4D): next 2 bytes LE = length, then data
        if (op == 0x4D) {
            if (pc + 2 > script.size()) { if (err) *err = "PUSHDATA2: missing length"; return false; }
            size_t len = script[pc] | ((size_t)script[pc + 1] << 8);
            pc += 2;
            if (pc + len > script.size()) {
                if (err) *err = "PUSHDATA2: not enough data";
                return false;
            }
            stack.push_back(StackItem(script.begin() + pc, script.begin() + pc + len));
            pc += len;
            continue;
        }

        // OP_DUP
        if (op == OP_DUP) {
            if (stack.empty()) { if (err) *err = "DUP: empty stack"; return false; }
            stack.push_back(stack.back());
            continue;
        }

        // OP_HASH160
        if (op == OP_HASH160) {
            if (stack.empty()) { if (err) *err = "HASH160: empty stack"; return false; }
            auto data = stack.back(); stack.pop_back();
            auto h = hash160(data.data(), data.size());
            stack.push_back(StackItem(h.begin(), h.end()));
            continue;
        }

        // OP_EQUAL
        if (op == OP_EQUAL) {
            if (stack.size() < 2) { if (err) *err = "EQUAL: need 2 items"; return false; }
            auto b = stack.back(); stack.pop_back();
            auto a = stack.back(); stack.pop_back();
            stack.push_back(a == b ? StackItem{1} : StackItem{0});
            continue;
        }

        // OP_EQUALVERIFY
        if (op == OP_EQUALVERIFY) {
            if (stack.size() < 2) { if (err) *err = "EQUALVERIFY: need 2 items"; return false; }
            auto b = stack.back(); stack.pop_back();
            auto a = stack.back(); stack.pop_back();
            if (a != b) { if (err) *err = "EQUALVERIFY: not equal"; return false; }
            continue;
        }

        // OP_CHECKSIG
        if (op == OP_CHECKSIG) {
            if (stack.size() < 2) { if (err) *err = "CHECKSIG: need 2 items"; return false; }
            auto pk_item = stack.back(); stack.pop_back();
            auto sig_item = stack.back(); stack.pop_back();

            if (pk_item.size() != 33 || sig_item.size() != 64) {
                stack.push_back({0}); // invalid sig/pubkey = false
                continue;
            }

            PubKey pk; std::memcpy(pk.data(), pk_item.data(), 33);
            Sig64 sig; std::memcpy(sig.data(), sig_item.data(), 64);

            std::string verr;
            bool ok = VerifySighash(pk, ctx.sighash, sig, &verr);
            stack.push_back(ok ? StackItem{1} : StackItem{0});
            continue;
        }

        // OP_CHECKMULTISIG
        if (op == OP_CHECKMULTISIG) {
            if (stack.size() < 1) { if (err) *err = "CHECKMULTISIG: empty stack"; return false; }

            // Pop N (number of pubkeys)
            auto n_item = stack.back(); stack.pop_back();
            int n = (n_item.size() == 1) ? n_item[0] : 0;
            if (n < 1 || n > (int)MAX_MULTISIG_KEYS) {
                if (err) *err = "CHECKMULTISIG: invalid N=" + std::to_string(n);
                return false;
            }

            if ((int)stack.size() < n) {
                if (err) *err = "CHECKMULTISIG: not enough pubkeys";
                return false;
            }

            // Pop N pubkeys
            std::vector<PubKey> pubkeys(n);
            for (int i = n - 1; i >= 0; --i) {
                auto pk_item = stack.back(); stack.pop_back();
                if (pk_item.size() != 33) {
                    if (err) *err = "CHECKMULTISIG: invalid pubkey size";
                    return false;
                }
                std::memcpy(pubkeys[i].data(), pk_item.data(), 33);
            }

            // Pop M (required signatures)
            if (stack.empty()) { if (err) *err = "CHECKMULTISIG: missing M"; return false; }
            auto m_item = stack.back(); stack.pop_back();
            int m = (m_item.size() == 1) ? m_item[0] : 0;
            if (m < 1 || m > n) {
                if (err) *err = "CHECKMULTISIG: invalid M=" + std::to_string(m) + " N=" + std::to_string(n);
                return false;
            }

            // Pop M signatures
            if ((int)stack.size() < m) {
                if (err) *err = "CHECKMULTISIG: not enough signatures";
                return false;
            }

            std::vector<Sig64> sigs(m);
            for (int i = m - 1; i >= 0; --i) {
                auto sig_item = stack.back(); stack.pop_back();
                if (sig_item.size() != 64) {
                    if (err) *err = "CHECKMULTISIG: invalid signature size";
                    return false;
                }
                std::memcpy(sigs[i].data(), sig_item.data(), 64);
            }

            // Pop dummy OP_0 (historical off-by-one)
            if (!stack.empty()) {
                stack.pop_back();
            }

            // Verify: each sig must match a pubkey, in order, no backtracking
            int pk_idx = 0;
            int sigs_valid = 0;
            for (int si = 0; si < m && pk_idx < n; ++si) {
                bool found = false;
                while (pk_idx < n) {
                    std::string verr;
                    if (VerifySighash(pubkeys[pk_idx], ctx.sighash, sigs[si], &verr)) {
                        pk_idx++;
                        found = true;
                        sigs_valid++;
                        break;
                    }
                    pk_idx++;
                }
                if (!found) break;
            }

            stack.push_back(sigs_valid >= m ? StackItem{1} : StackItem{0});
            continue;
        }

        // Unknown opcode
        if (err) *err = "unknown opcode: 0x" + std::to_string(op);
        return false;
    }

    return true;
}

// ---------------------------------------------------------------------------
// High-level evaluation
// ---------------------------------------------------------------------------

bool eval_script(
    const Script& script_sig,
    const Script& script_pubkey,
    const ScriptEvalContext& ctx,
    std::string* err)
{
    std::vector<StackItem> stack;

    // Execute scriptSig
    if (!eval_ops(script_sig, stack, ctx, err)) return false;

    // Execute scriptPubKey
    if (!eval_ops(script_pubkey, stack, ctx, err)) return false;

    // Result: top of stack must be truthy
    if (!stack_top_truthy(stack)) {
        if (err) *err = "script result: false";
        return false;
    }
    return true;
}

bool eval_p2sh(
    const Script& script_sig,
    const PubKeyHash& expected_hash,
    const ScriptEvalContext& ctx,
    std::string* err)
{
    // Step 1: Parse script_sig to extract the redeemScript (last push)
    // The last data push in scriptSig is the serialized redeemScript
    std::vector<StackItem> sig_stack;
    if (!eval_ops(script_sig, sig_stack, ctx, err)) return false;

    if (sig_stack.empty()) {
        if (err) *err = "P2SH: empty scriptSig stack";
        return false;
    }

    // Last item on stack = redeemScript
    StackItem redeem_data = sig_stack.back();
    Script redeem_script(redeem_data.begin(), redeem_data.end());

    // Step 2: Verify hash matches
    PubKeyHash actual_hash = hash_script(redeem_script);
    if (actual_hash != expected_hash) {
        if (err) *err = "P2SH: redeemScript hash mismatch";
        return false;
    }

    // Step 3: Execute redeemScript with the remaining stack items
    sig_stack.pop_back(); // remove redeemScript from stack
    if (!eval_ops(redeem_script, sig_stack, ctx, err)) return false;

    if (!stack_top_truthy(sig_stack)) {
        if (err) *err = "P2SH: redeemScript evaluation failed";
        return false;
    }

    return true;
}

} // namespace sost
