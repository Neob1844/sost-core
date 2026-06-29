# BitcoinTalk reply draft — V14 att/s drop + APAC seed latency

> Reply to the two field reports (att/s drop after V14; single EU seed / APAC orphans).
> Honest, technical, no over-promising. Post under the [ANN] thread.

---

Thanks both — these are exactly the field reports that make the network better. Straight answers:

**On the att/s drop (113 → 31, same threads, since V14):**
This is **not** a change to the ConvergenceX PoW — V14 did not touch the hashing algorithm, so your hardware isn't the problem. What you're seeing is the **cASERT difficulty profile** moving into harder bands. Every attempt runs a stability test whose cost rises with the profile; when the profile sits around H16–H19 each attempt does several times more work, so your *attempts/sec* falls even though nothing on your machine changed. We've measured the profile swinging between ~H7 and ~H19 recently — that volatility is driven by bursty, concentrated hashrate, and it hits smaller miners' att/s (and block share) hardest. We're evaluating smoothing that profile volatility, but as a careful, height-gated change — we don't rush consensus.

**On the single EU seed / APAC latency / orphans:**
You're right, and our own logs back it up: the node shows a very high count of `LESS cumulative work` forks — exactly the propagation-race orphaning you describe at ~360 ms. A single Germany seed disadvantages everyone far from Europe.

**What we're doing about it:**
- **V14.5 adds multiple regional default seeds** (`seed-eu`, `seed-apac`, `seed-us`). The node now connects to several and tolerates any being down, instead of depending on one EU seed.
- We're bringing up regional seed nodes (Asia-Pacific + North America). **APAC miners with a solid public node can run the regional bootnode yourselves** — it directly fixes your own latency, and reliable community nodes can be added to the default list. (Koriaz98 — your New Caledonia node would make a great APAC seed.)
- How to run an official seed or a community bootnode is documented in the repo (`docs/SEED_NODES.md`).
- In the meantime, start your node with `--connect <closer-peer>:19333` to cut bootstrap latency.

Separately — note the **mandatory V14.5 upgrade before block 16,000** (it fixes an Atomic Swap CLAIM/REFUND bug; details in the website banner). The same binary carries this multi-seed improvement, so one rebuild covers both.

Thanks for mining SOST and for the detailed, actionable reports. 🙏

— NeoB
