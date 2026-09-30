// STEP 3-8: native-asset consensus validator — happy paths + adversarial rejects.
#include "sost/native_assets_validation.h"
#include <cstdio>
#include <map>
using namespace sost;
static int fails=0;
#define EXPECT(call,want,msg) do{ std::string e; auto r=(call); if(r!=(want)){ printf("  FAIL: %s -> got %s (want %s)\n", msg, asset_tx_result_str(r), asset_tx_result_str(want)); ++fails; } }while(0)

struct MapUtxo : IUtxoView {
  std::map<OutPoint,UTXOEntry> m;
  std::optional<UTXOEntry> GetUTXO(const OutPoint& op) const override { auto it=m.find(op); if(it==m.end())return std::nullopt; return it->second; }
};
struct MapAssets : IAssetView {
  std::map<Bytes32,AssetState> m;
  const AssetState* GetAsset(const Bytes32& id) const override { auto it=m.find(id); return it==m.end()?nullptr:&it->second; }
};
static TxOutput mkout(uint8_t type,std::vector<uint8_t> payload,int64_t sost=1){ TxOutput o; o.type=type; o.payload=std::move(payload); o.amount=sost; return o; }
static TxInput mkin(Hash256 txid,uint32_t idx){ TxInput i; i.prev_txid=txid; i.prev_index=idx; return i; }
static Hash256 H(uint8_t seed){ Hash256 h{}; h[0]=seed; h[31]=seed; return h; }

int main(){
  const int64_t HT=100; // >= devnet activation 42
  Hash256 gtxid=H(9);

  // ---------- GENESIS (FIXED) happy ----------
  {
    MapUtxo u; MapAssets a;
    AssetDef d; d.symbol="AU"; d.name="Gold"; d.decimals=8; d.supply_policy=ASSET_POLICY_FIXED; d.max_supply=1000;
    Transaction tx; tx.tx_type=TX_TYPE_ASSET_GENESIS;
    tx.outputs.push_back(mkout(OUT_ASSET_GENESIS_DEF, serialize_asset_def(d))); // vout 0
    Bytes32 id=compute_asset_id(gtxid,0);
    tx.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,1000))); // mint == cap
    EXPECT(validate_asset_tx(tx,gtxid,u,a,HT,&e), AssetTxResult::OK, "genesis FIXED mint==cap OK");
    // FIXED but mint != cap -> reject
    { Transaction t2=tx; t2.outputs[1]=mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,999));
      EXPECT(validate_asset_tx(t2,gtxid,u,a,HT,&e), AssetTxResult::GENESIS_SUPPLY, "FIXED mint<cap reject"); }
    // FIXED with an authority -> reject
    { Transaction t2=tx; t2.outputs.push_back(mkout(OUT_ASSET_ISSUE_AUTH, serialize_asset_auth(id)));
      EXPECT(validate_asset_tx(t2,gtxid,u,a,HT,&e), AssetTxResult::GENESIS_SHAPE, "FIXED with authority reject"); }
    // duplicate genesis -> reject
    { MapAssets a2; AssetState st; st.def=d; st.issued=1000; a2.m[id]=st;
      EXPECT(validate_asset_tx(tx,gtxid,u,a2,HT,&e), AssetTxResult::GENESIS_DUP, "duplicate genesis reject"); }
    // below activation -> reject
    EXPECT(validate_asset_tx(tx,gtxid,u,a,41,&e), AssetTxResult::NOT_ACTIVE, "below activation reject");
    // mint references a DIFFERENT asset id -> reject
    { Transaction t2=tx; t2.outputs[1]=mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(H(7),1000));
      EXPECT(validate_asset_tx(t2,gtxid,u,a,HT,&e), AssetTxResult::GENESIS_SHAPE, "genesis foreign asset reject"); }
  }

  // ---------- GENESIS (CAPPED) + ISSUE ----------
  {
    MapUtxo u; MapAssets a;
    AssetDef d; d.symbol="RC"; d.name="Reissuable"; d.decimals=2; d.supply_policy=ASSET_POLICY_CAPPED_REISSUABLE; d.max_supply=1000;
    Bytes32 id=compute_asset_id(gtxid,0);
    Transaction g; g.tx_type=TX_TYPE_ASSET_GENESIS;
    g.outputs.push_back(mkout(OUT_ASSET_GENESIS_DEF, serialize_asset_def(d)));
    g.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,400)));
    g.outputs.push_back(mkout(OUT_ASSET_ISSUE_AUTH, serialize_asset_auth(id)));
    EXPECT(validate_asset_tx(g,gtxid,u,a,HT,&e), AssetTxResult::OK, "genesis CAPPED mint<cap +auth OK");
    // CAPPED without authority -> reject
    { Transaction t2=g; t2.outputs.pop_back();
      EXPECT(validate_asset_tx(t2,gtxid,u,a,HT,&e), AssetTxResult::GENESIS_SHAPE, "CAPPED no authority reject"); }

    // now ISSUE 500 more (issued 400 -> 900 <= cap 1000)
    AssetState st; st.def=d; st.issued=400; a.m[id]=st;
    Hash256 authtx=H(5); UTXOEntry ae; ae.type=OUT_ASSET_ISSUE_AUTH; ae.payload=serialize_asset_auth(id); ae.amount=1;
    OutPoint aop; aop.txid=authtx; aop.index=0; u.m[aop]=ae;
    Transaction is; is.tx_type=TX_TYPE_ASSET_ISSUE; is.inputs.push_back(mkin(authtx,0));
    is.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,500)));
    is.outputs.push_back(mkout(OUT_ASSET_ISSUE_AUTH, serialize_asset_auth(id))); // recreate
    EXPECT(validate_asset_tx(is,H(2),u,a,HT,&e), AssetTxResult::OK, "issue within cap OK");
    // issue exceeding cap (400+700>1000) -> reject
    { Transaction t2=is; t2.outputs[0]=mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,700));
      EXPECT(validate_asset_tx(t2,H(2),u,a,HT,&e), AssetTxResult::CAP_EXCEEDED, "issue over cap reject"); }
    // issue without spending authority -> reject
    { Transaction t2=is; t2.inputs.clear();
      EXPECT(validate_asset_tx(t2,H(2),u,a,HT,&e), AssetTxResult::NO_AUTHORITY, "issue no authority reject"); }
    // issue on a FIXED asset -> reject
    { MapAssets a2=a; a2.m[id].def.supply_policy=ASSET_POLICY_FIXED;
      EXPECT(validate_asset_tx(is,H(2),u,a2,HT,&e), AssetTxResult::NOT_REISSUABLE, "issue FIXED reject"); }
  }

  // ---------- TRANSFER conservation ----------
  {
    MapUtxo u; MapAssets a; Bytes32 id=H(3);
    Hash256 src=H(4); UTXOEntry e1; e1.type=OUT_ASSET_TRANSFER; e1.payload=serialize_asset_amount(id,100); e1.amount=1;
    OutPoint op; op.txid=src; op.index=0; u.m[op]=e1;
    Transaction t; t.tx_type=TX_TYPE_ASSET_TRANSFER; t.inputs.push_back(mkin(src,0));
    t.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,60)));
    t.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,40)));
    EXPECT(validate_asset_tx(t,H(6),u,a,HT,&e), AssetTxResult::OK, "transfer 100->60+40 OK");
    // conservation violated (out>in) -> reject
    { Transaction t2=t; t2.outputs[1]=mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,41));
      EXPECT(validate_asset_tx(t2,H(6),u,a,HT,&e), AssetTxResult::CONSERVATION, "transfer inflate reject"); }
    // create a NEW asset id out of thin air in transfer -> reject
    { Transaction t2=t; t2.outputs[1]=mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(H(8),40));
      EXPECT(validate_asset_tx(t2,H(6),u,a,HT,&e), AssetTxResult::CONSERVATION, "transfer mint-from-air reject"); }
    // asset output with SOST dust below minimum -> confusion reject
    { Transaction t2=t; t2.outputs[0].amount=0;
      EXPECT(validate_asset_tx(t2,H(6),u,a,HT,&e), AssetTxResult::ASSET_SOST_CONFUSION, "asset dust<min reject"); }
  }

  // ---------- BURN ----------
  {
    MapUtxo u; MapAssets a; Bytes32 id=H(3); AssetState st; st.def.max_supply=1000; st.issued=100; a.m[id]=st;
    Hash256 src=H(4); UTXOEntry e1; e1.type=OUT_ASSET_TRANSFER; e1.payload=serialize_asset_amount(id,100); e1.amount=1;
    OutPoint op; op.txid=src; op.index=0; u.m[op]=e1;
    Transaction t; t.tx_type=TX_TYPE_ASSET_BURN; t.inputs.push_back(mkin(src,0));
    t.outputs.push_back(mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,30))); // keep 30
    t.outputs.push_back(mkout(OUT_ASSET_BURN, serialize_asset_amount(id,70)));      // burn 70
    EXPECT(validate_asset_tx(t,H(6),u,a,HT,&e), AssetTxResult::OK, "burn 100->keep30+burn70 OK");
    // burn conservation off -> reject
    { Transaction t2=t; t2.outputs[1]=mkout(OUT_ASSET_BURN, serialize_asset_amount(id,71));
      EXPECT(validate_asset_tx(t2,H(6),u,a,HT,&e), AssetTxResult::CONSERVATION, "burn miscount reject"); }
    // burn tx with no burn output -> shape reject
    { Transaction t2=t; t2.outputs[1]=mkout(OUT_ASSET_TRANSFER, serialize_asset_amount(id,70));
      EXPECT(validate_asset_tx(t2,H(6),u,a,HT,&e), AssetTxResult::BURN_SHAPE, "burn without burn-output reject"); }
  }

  printf(fails? "test_native_assets_consensus: %d FAILED\n":"test_native_assets_consensus: ALL PASS\n", fails);
  return fails?1:0;
}
