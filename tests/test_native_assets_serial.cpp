// STEP 2 unit test: native asset model + canonical serialization (round-trip + adversarial rejects).
#include "sost/native_assets.h"
#include <cassert>
#include <cstdio>
using namespace sost;
static int fails=0;
#define CHECK(c,m) do{ if(!(c)){ printf("  FAIL: %s\n", m); ++fails; } }while(0)
int main(){
  // asset_id determinism + outpoint-uniqueness
  Hash256 tx{}; tx[0]=0xAB; tx[31]=0x01;
  Bytes32 id0 = compute_asset_id(tx,0), id0b = compute_asset_id(tx,0), id1 = compute_asset_id(tx,1);
  CHECK(id0==id0b, "asset_id deterministic");
  CHECK(!(id0==id1), "asset_id differs by vout (outpoint-unique)");

  // AssetDef round-trip
  AssetDef d; d.symbol="GOLD"; d.name="Gold Reserve Token"; d.decimals=8;
  d.supply_policy=ASSET_POLICY_CAPPED_REISSUABLE; d.max_supply=21000000ULL; d.manifest_hash=id0;
  auto p = serialize_asset_def(d); AssetDef d2; std::string e;
  CHECK(parse_asset_def(p,d2,&e), "assetdef round-trip parses");
  CHECK(d2.symbol=="GOLD"&&d2.name=="Gold Reserve Token"&&d2.decimals==8&&
        d2.supply_policy==1&&d2.max_supply==21000000ULL&&d2.manifest_hash==id0, "assetdef fields match");

  // adversarial rejects
  auto bad=p; bad[0]=9;          CHECK(!parse_asset_def(bad,d2), "reject bad version");
  bad=p; bad.push_back(0);       CHECK(!parse_asset_def(bad,d2), "reject trailing bytes (non-canonical)");
  { AssetDef x=d; x.decimals=19; auto q=serialize_asset_def(x); CHECK(!parse_asset_def(q,d2), "reject decimals>18"); }
  { AssetDef x=d; x.supply_policy=7; auto q=serialize_asset_def(x); CHECK(!parse_asset_def(q,d2), "reject bad policy"); }
  { AssetDef x=d; x.max_supply=0; auto q=serialize_asset_def(x); CHECK(!parse_asset_def(q,d2), "reject max_supply=0"); }
  { AssetDef x=d; x.max_supply=ASSET_MAX_SUPPLY_CEILING+1; auto q=serialize_asset_def(x); CHECK(!parse_asset_def(q,d2), "reject max_supply>ceiling"); }
  { std::string big(13,'X'); AssetDef x=d; x.symbol=big; auto q=serialize_asset_def(x); CHECK(!parse_asset_def(q,d2), "reject symbol>12"); }
  CHECK(!parse_asset_def({}, d2), "reject empty");

  // asset amount payload round-trip + rejects
  auto pa = serialize_asset_amount(id0, 123456789ULL); Bytes32 aid; uint64_t amt;
  CHECK(parse_asset_amount(pa,aid,amt,&e)&&aid==id0&&amt==123456789ULL, "asset amount round-trip");
  { auto q=pa; q.pop_back(); CHECK(!parse_asset_amount(q,aid,amt), "reject amount payload bad length"); }
  { auto q=serialize_asset_amount(id0,0); CHECK(!parse_asset_amount(q,aid,amt), "reject amount=0"); }

  // auth payload round-trip
  auto au = serialize_asset_auth(id0); Bytes32 aid2;
  CHECK(parse_asset_auth(au,aid2,&e)&&aid2==id0, "asset auth round-trip");
  { auto q=au; q.pop_back(); CHECK(!parse_asset_auth(q,aid2), "reject auth bad length"); }

  // classifiers
  CHECK(is_asset_amount_output(OUT_ASSET_TRANSFER)&&is_asset_amount_output(OUT_ASSET_BURN), "amount-output classifier");
  CHECK(!is_asset_amount_output(OUT_ASSET_ISSUE_AUTH), "auth is not amount-output");
  CHECK(is_spendable_asset_output(OUT_ASSET_TRANSFER)&&is_spendable_asset_output(OUT_ASSET_ISSUE_AUTH), "spendable classifier");

  printf(fails? "test_native_assets_serial: %d FAILED\n" : "test_native_assets_serial: ALL PASS\n", fails);
  return fails?1:0;
}
