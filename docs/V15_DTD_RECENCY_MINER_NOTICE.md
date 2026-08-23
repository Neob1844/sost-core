# ⛏️ Miner notice — mandatory upgrade before block #25,000

SOST V15 (block **#25,000**) adds a **DTD recency eligibility rule**:

- To win the **normal DTD draw**, your mining address must have mined **≥1 block in the last 5,000 blocks**.
- To win the **DTD Jackpot**, your address must have mined **≥1 block in the last 2,016 blocks** (~2 weeks).

Everything else is unchanged (block reward, SbPoW, cooldown, anti-dominance). Dormant addresses simply stop
being eligible until they mine again — nothing is lost, no supply change.

**Action:** upgrade your node and miner to the V15 build (which includes this rule) **before block #25,000**.
Build with the mandatory flags: `-DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF`.
Running an older binary past #25,000 will fork you off the network.

Questions: t.me/SOSTProtocolOfficial · sost@sostcore.com
