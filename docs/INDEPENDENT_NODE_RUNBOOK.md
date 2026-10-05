# Independent SOST Full Node — Runbook
Goal: run a full validating node that is NOT operated by the SOST team, on independent
infrastructure (different provider / ASN / region). An independent node strengthens the
network's survival: existing connected nodes keep validating/relaying even if sostcore.com
goes down. Works with the **current v30000 release** (no new binary needed).

## 1. Get + verify the binaries
    # from the release tag (source) OR the published binaries:
    git clone https://github.com/Neob1844/sost-core.git && cd sost-core
    git fetch --tags && git checkout v30000
    mkdir build && cd build && cmake .. -DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF && make -j$(nproc)
    sha256sum sost-node sost-cli    # MUST match docs/v30000/SHA256SUMS.txt (node 78fefb67… / cli c8ae00b9…)

## 2. RPC password (your own; never shared)
    mkdir -p ~/.sost && umask 077
    openssl rand -base64 30 > ~/.sost/rpc.pass && chmod 600 ~/.sost/rpc.pass

## 3. Run the node
    cp ../genesis_block.json .
    ./sost-node --genesis genesis_block.json --chain ~/.sost/chain.json \
      --rpc-user youruser --rpc-pass-file ~/.sost/rpc.pass --profile mainnet --p2p-enc on \
      --connect seed-eu.sostcore.com:19333
    # It syncs, validates every block independently, and relays to peers. Leave it running.

## 4. Make it reachable (so OTHERS can bootstrap from YOU → real decentralization)
    # open inbound P2P 19333 (see firewall.example). Publish your node's host:port so other
    # operators can add it to their --connect / seeds.txt / peers.txt.

## 5. systemd (see systemd-node.example) — auto-restart, survives reboot.

## Verify it is helping the network
    curl -s -u youruser:$(cat ~/.sost/rpc.pass) -d '{"method":"getpeerinfo","id":1}' http://127.0.0.1:18232 | grep -c addr
    # >0 inbound peers = other nodes are bootstrapping through you.

Losing the primary VPS does NOT stop your node or the peers connected to it.
