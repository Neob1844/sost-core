// STEP 4/11/12: asset index apply/undo (reorg-safety: undo restores state byte-for-byte).
#include "sost/native_assets_index.h"
#include <cstdio>
using namespace sost;
static int fails=0;
#define CK(c,m) do{ if(!(c)){ printf("  FAIL: %s\n", m); ++fails; } }while(0)
static TxOutput mkout(uint8_t t,std::vector<uint8_t> p,int64_t s=1){ TxOutput o; o.type=t; o.payload=std::move(p); o.amount=s; return o; }
static Hash256 H(uint8_t s){ Hash256 h{}; h[0]=s; h[31]=s; return h; }
int main(){
  NativeAssetIndex idx;
  Hash256 gtx=H(1);
  // genesis CAPPED, mint 400, cap 1000
  AssetDef d; d.symbol="RC"; d.decimals=2; d.supply_policy=ASSET_POLICY_CAPPED_REISSUABLE; d.max_supply=1000;
  Bytes32 id=compute_asset_id(gtx,0);
  Transaction g; g.tx_type=TX_TYPE_ASSET_GENESIS;
  g.outputs.push_back(mkout(OUT_ASSET_GENESIS_DEF, serialize_asset_def(d)));
  g.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,400)));
  g.outputs.push_back(mkout(OUT_ASSET_ISSUE_AUTH, serialize_asset_auth(id)));
  auto dg = idx.apply(g, gtx);
  CK(idx.size()==1, "genesis created 1 asset");
  const AssetState* s = idx.GetAsset(id);
  CK(s && s->issued==400 && s->burned==0 && s->def.max_supply==1000, "genesis issued=400");

  // issue +500 -> 900
  Transaction is; is.tx_type=TX_TYPE_ASSET_ISSUE;
  is.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,500)));
  is.outputs.push_back(mkout(OUT_ASSET_ISSUE_AUTH, serialize_asset_auth(id)));
  auto di = idx.apply(is, H(2));
  CK(idx.GetAsset(id)->issued==900, "after issue issued=900");

  // burn 300 -> burned=300 (circulating 900-300=600)
  Transaction bn; bn.tx_type=TX_TYPE_ASSET_BURN;
  bn.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,600)));
  bn.outputs.push_back(mkout(OUT_ASSET_BURN, serialize_asset_amount(id,300)));
  auto db = idx.apply(bn, H(3));
  CK(idx.GetAsset(id)->burned==300 && idx.GetAsset(id)->issued==900, "after burn burned=300 issued=900");

  // ---- reorg disconnect: undo in REVERSE order -> state restored exactly ----
  idx.undo(db); CK(idx.GetAsset(id)->burned==0 && idx.GetAsset(id)->issued==900, "undo burn -> burned=0");
  idx.undo(di); CK(idx.GetAsset(id)->issued==400, "undo issue -> issued=400");
  idx.undo(dg); CK(idx.size()==0 && idx.GetAsset(id)==nullptr, "undo genesis -> index empty (restored)");

  // transfer = no index change
  Transaction tr; tr.tx_type=TX_TYPE_ASSET_TRANSFER;
  tr.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,100)));
  auto dt = idx.apply(tr, H(4));
  CK(dt.kind==0 && idx.size()==0, "transfer leaves index unchanged");

  printf(fails? "test_native_assets_index: %d FAILED\n":"test_native_assets_index: ALL PASS\n", fails);
  return fails?1:0;
}
