// test_native_assets_activation.cpp — V30000 activation gate for native assets.
// Asset tx types + asset output types are INERT before NATIVE_ASSETS_ACTIVATION_HEIGHT
// and ACTIVE at/after it. Mirrors the HTLC gate regression guard. Passes identically
// in devnet (gate 42) and mainnet (gate 30000) builds since all heights derive from
// the constant.
#include "sost/params.h"
#include "sost/transaction.h"
#include "sost/tx_validation.h"
#include "sost/native_assets.h"
#include "sost/consensus_constants.h"
#include <array>
#include <cstdio>
#include <optional>
using namespace sost;
static int g_pass=0,g_fail=0;
#define TEST(m,c) do{ if(c){std::printf("  PASS: %s\n",m);++g_pass;} else {std::printf("  *** FAIL: %s [%d]\n",m,__LINE__);++g_fail;} }while(0)
static constexpr int64_t A = NATIVE_ASSETS_ACTIVATION_HEIGHT;

struct EmptyView: IUtxoView{ std::optional<UTXOEntry> GetUTXO(const OutPoint&) const override{ return std::nullopt; } };
static TxValidationContext Ctx(int64_t h){ TxValidationContext c; c.genesis_hash.fill(0); c.spend_height=h;
  c.capsule_activation_height=CAPSULE_ACTIVATION_HEIGHT_MAINNET; c.bond_activation_height=BOND_ACTIVATION_HEIGHT_MAINNET; return c; }
static Hash256 HH(uint8_t s){ Hash256 h{}; h[0]=s; h[31]=s; return h; }

// GENESIS tx (type ASSET_GENESIS) with a GENESIS_DEF + mint output.
static Transaction MakeGenesis(){
  AssetDef d; d.symbol="AU"; d.name="Gold"; d.decimals=8; d.supply_policy=ASSET_POLICY_FIXED; d.max_supply=1000;
  Transaction tx; tx.version=1; tx.tx_type=TX_TYPE_ASSET_GENESIS;
  TxInput in; in.prev_txid=HH(7); in.prev_index=0; in.signature.fill(0x01); in.pubkey.fill(0x02); tx.inputs.push_back(in);
  TxOutput g; g.type=OUT_ASSET_GENESIS_DEF; g.amount=1; g.payload=serialize_asset_def(d); tx.outputs.push_back(g);
  Bytes32 id=compute_asset_id(HH(7),0);
  TxOutput m; m.type=OUT_ASSET_TRANSFER; m.amount=1; m.payload=serialize_asset_amount(id,1000); tx.outputs.push_back(m);
  return tx;
}
// a STANDARD tx that carries an asset output type (to probe R11 output-type gating).
static Transaction MakeStdWithAssetOutput(){
  Transaction tx; tx.version=1; tx.tx_type=TX_TYPE_STANDARD;
  TxInput in; in.prev_txid=HH(8); in.prev_index=0; in.signature.fill(0x01); in.pubkey.fill(0x02); tx.inputs.push_back(in);
  Bytes32 id=compute_asset_id(HH(8),0);
  TxOutput m; m.type=OUT_ASSET_TRANSFER; m.amount=1; m.payload=serialize_asset_amount(id,10); tx.outputs.push_back(m);
  return tx;
}

int main(){
  std::printf("\n== NATIVE ASSETS activation gate (height %lld) ==\n\n",(long long)A);
  TEST("gate finite (feature activates)", A!=INT64_MAX);
  TEST("native_assets_active_at(A) == true", native_assets_active_at(A));
  TEST("native_assets_active_at(A-1) == false", !native_assets_active_at(A-1));
  TEST("native_assets_active_at(0) == false", !native_assets_active_at(0));

  EmptyView v;
  // PRE-activation: ASSET_GENESIS tx_type rejected at R2.
  {
    auto r=ValidateTransactionConsensus(MakeGenesis(),v,Ctx(A-1));
    TEST("PRE: ASSET_GENESIS rejected (R2_BAD_TX_TYPE)", !r.ok && r.code==TxValCode::R2_BAD_TX_TYPE);
  }
  // PRE-activation: asset OUTPUT type in a standard tx rejected at R11.
  {
    auto r=ValidateTransactionConsensus(MakeStdWithAssetOutput(),v,Ctx(A-1));
    TEST("PRE: OUT_ASSET_TRANSFER rejected (R11_INACTIVE_TYPE)", !r.ok && r.code==TxValCode::R11_INACTIVE_TYPE);
  }
  // POST-activation: ASSET_GENESIS tx_type ACCEPTED past R2 (fails later on missing input UTXO, not on the gate).
  {
    auto r=ValidateTransactionConsensus(MakeGenesis(),v,Ctx(A));
    TEST("POST: ASSET_GENESIS passes R2 (type active)", r.code!=TxValCode::R2_BAD_TX_TYPE);
    TEST("POST: ASSET_GENESIS not rejected as inactive output (R11)", r.code!=TxValCode::R11_INACTIVE_TYPE);
    // NOTE: with RESTRICTED DEVELOPER MODE active at/after activation, an asset tx that
    // passed R2/R11 is next caught by the admin gate (S14) when no admin authority is
    // present in the context (fail-closed). That is the correct post-activation behavior.
    TEST("POST: ASSET_GENESIS past activation gate -> admin gate (S14_RESTRICTED_DEV_MODE)", !r.ok && r.code==TxValCode::S14_RESTRICTED_DEV_MODE);
  }
  // POST-activation: asset OUTPUT type accepted past R11.
  {
    auto r=ValidateTransactionConsensus(MakeStdWithAssetOutput(),v,Ctx(A));
    TEST("POST: OUT_ASSET_TRANSFER passes R11 (type active)", r.code!=TxValCode::R11_INACTIVE_TYPE);
  }
  // boundary: exactly at A-1 inert, at A active (both tx and output gates).
  {
    auto pre=ValidateTransactionConsensus(MakeGenesis(),v,Ctx(A-1));
    auto at =ValidateTransactionConsensus(MakeGenesis(),v,Ctx(A));
    TEST("BOUNDARY: inert at A-1, active at A", pre.code==TxValCode::R2_BAD_TX_TYPE && at.code!=TxValCode::R2_BAD_TX_TYPE);
  }
  std::printf("\n== Summary: %d passed, %d failed ==\n",g_pass,g_fail);
  return g_fail?1:0;
}
