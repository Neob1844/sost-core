// test_admin_gate.cpp — V30000 RESTRICTED DEVELOPER MODE protocol gate (S14).
// A native-asset tx is valid under restricted mode ONLY if it carries an input
// whose pubkey hashes to the admin authority pkh; otherwise consensus rejects it.
// Fail-closed when no authority is configured. Proven on ValidateTransactionConsensus
// (the same validator the node runs on the block path).
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/tx_signer.h"
#include "sost/native_assets.h"
#include "sost/consensus_constants.h"
#include <array>
#include <cstdio>
#include <optional>
using namespace sost;
static int g_pass=0,g_fail=0;
#define TEST(m,c) do{ if(c){std::printf("  PASS: %s\n",m);++g_pass;} else {std::printf("  *** FAIL: %s [%d]\n",m,__LINE__);++g_fail;} }while(0)

struct EmptyView: IUtxoView{ std::optional<UTXOEntry> GetUTXO(const OutPoint&) const override{ return std::nullopt; } };

static PubKey mkpub(uint8_t seed){ PubKey k{}; k[0]=0x02; for(int i=1;i<33;++i)k[i]=(uint8_t)(seed*31+i); return k; }

static Transaction assetTx(const PubKey& inputPub){
  AssetDef d; d.symbol="AU"; d.name="Gold"; d.decimals=8; d.supply_policy=ASSET_POLICY_FIXED; d.max_supply=1000;
  Transaction tx; tx.version=1; tx.tx_type=TX_TYPE_ASSET_TRANSFER;
  TxInput in; in.prev_txid.fill(0x7); in.prev_index=0; in.signature.fill(0x01); in.pubkey=inputPub; tx.inputs.push_back(in);
  Bytes32 id=compute_asset_id(in.prev_txid,0);
  TxOutput m; m.type=OUT_ASSET_TRANSFER; m.amount=10000; m.payload=serialize_asset_amount(id,10); tx.outputs.push_back(m);
  return tx;
}
static TxValidationContext ctxAt(int64_t h, const std::array<uint8_t,20>& admin){
  TxValidationContext c; c.genesis_hash.fill(0); c.spend_height=h;
  c.capsule_activation_height=CAPSULE_ACTIVATION_HEIGHT_MAINNET; c.bond_activation_height=BOND_ACTIVATION_HEIGHT_MAINNET;
  c.admin_authority_pkh=admin; return c;
}

int main(){
  std::printf("\n== V30000 RESTRICTED DEVELOPER MODE — admin consensus gate (S14) ==\n\n");
  const int64_t H = NATIVE_ASSETS_ACTIVATION_HEIGHT; // restricted mode active at/after this
  TEST("restricted mode active at activation height", restricted_dev_mode_active_at(H));
  TEST("restricted mode inactive below activation", !restricted_dev_mode_active_at(H-1));

  PubKey adminPub = mkpub(5), otherPub = mkpub(9);
  PubKeyHash adminPkh = ComputePubKeyHash(adminPub);
  std::array<uint8_t,20> zero{};
  EmptyView v;

  // 1) authority set + tx carries an admin-signed input -> passes S14 (fails later S1, not S14)
  {
    auto r=ValidateTransactionConsensus(assetTx(adminPub), v, ctxAt(H, adminPkh));
    TEST("admin-authorised asset tx PASSES the gate (code != S14)", r.code!=TxValCode::S14_RESTRICTED_DEV_MODE);
    TEST("admin-authorised asset tx reaches input resolution (S1)", r.code==TxValCode::S1_UTXO_NOT_FOUND);
  }
  // 2) authority set + tx has NO admin input -> REJECTED S14
  {
    auto r=ValidateTransactionConsensus(assetTx(otherPub), v, ctxAt(H, adminPkh));
    TEST("non-admin asset tx REJECTED by the gate (S14)", !r.ok && r.code==TxValCode::S14_RESTRICTED_DEV_MODE);
  }
  // 3) fail-closed: NO authority configured (all-zero) -> even an otherwise-fine asset tx rejected S14
  {
    auto r=ValidateTransactionConsensus(assetTx(adminPub), v, ctxAt(H, zero));
    TEST("fail-closed: no authority set -> asset op REJECTED (S14)", !r.ok && r.code==TxValCode::S14_RESTRICTED_DEV_MODE);
  }
  // 4) below activation the gate is not the reason (R2 handles it); restricted mode off
  {
    auto r=ValidateTransactionConsensus(assetTx(otherPub), v, ctxAt(H-1, adminPkh));
    TEST("below activation: rejected by R2, NOT S14", r.code==TxValCode::R2_BAD_TX_TYPE);
  }
  // 5) a NON-asset standard tx is NOT gated by S14 (only asset ops are restricted)
  {
    Transaction tx; tx.version=1; tx.tx_type=TX_TYPE_STANDARD;
    TxInput in; in.prev_txid.fill(0xEE); in.prev_index=0; in.signature.fill(1); in.pubkey=otherPub; tx.inputs.push_back(in);
    TxOutput o; o.amount=50000; o.type=OUT_TRANSFER; o.pubkey_hash.fill(0xAB); tx.outputs.push_back(o);
    auto r=ValidateTransactionConsensus(tx, v, ctxAt(H, adminPkh));
    TEST("standard (non-asset) tx is NOT gated by S14", r.code!=TxValCode::S14_RESTRICTED_DEV_MODE);
  }
  std::printf("\n== Summary: %d passed, %d failed ==\n",g_pass,g_fail);
  return g_fail?1:0;
}
