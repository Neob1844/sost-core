# GitHub Organization Setup — sostcore

Instructions for setting up the `sostcore` GitHub organization and migrating the repository.

## 1. Create the Organization

1. Go to https://github.com/organizations/plan
2. Choose **Free** plan
3. Organization name: `sostcore`
4. Contact: use GitHub Issues for all communication (no email)
5. This organization belongs to: **My personal account**

## 2. Transfer the Repository

1. Go to https://github.com/Neob1844/sost-core/settings
2. Scroll to **Danger Zone** > **Transfer ownership**
3. New owner: `sostcore`
4. Type `Neob1844/sost-core` to confirm
5. GitHub will automatically create a redirect from the old URL

After transfer, the repo URL becomes: `https://github.com/sostcore/sost-core`

## 3. Repository Settings

### Branch Protection (Settings > Branches > Add rule)

- Branch name pattern: `main`
- [x] Require pull request reviews before merging (1 reviewer)
- [x] Require status checks to pass (add CI when ready)
- [x] Require branches to be up to date before merging
- [x] Do not allow force pushes
- [x] Do not allow deletions

### Security (Settings > Code security and analysis)

- [x] Dependency graph
- [x] Dependabot alerts
- [x] Secret scanning

### General

- Default branch: `main`
- Features: [x] Issues, [x] Discussions (optional), [ ] Wiki (use docs/ instead)
- Merge button: Allow squash merging, allow merge commits, disable rebase

## 4. Teams (optional for solo, recommended for growth)

| Team | Permission | Members |
|------|-----------|---------|
| core-dev | Admin | Neob1844 |
| contributors | Write | (future contributors) |
| auditors | Read | (security reviewers) |

## 5. Repository Topics

Add these topics in Settings > General > Topics:
```
cryptocurrency blockchain cpu-mining proof-of-work gold-backed cpp17 utxo
```

## 6. Releases

After genesis (2026-03-13), create the first release:

```bash
git tag -a v0.4.0 -m "Mainnet genesis release"
git push origin v0.4.0
```

Then on GitHub: Releases > Draft a new release > Choose tag `v0.4.0`

Attach pre-built binaries:
- `sost-v0.4.0-linux-x86_64.tar.gz` (sost-node, sost-miner, sost-cli, sost-rpc, genesis_block.json, explorer.html)

## 7. Update All References

After transfer, update these files:
- `README.md` — git clone URL
- `MINING.md` — git clone URL
- `explorer.html` — any GitHub links
- `docs/convergencex_whitepaper.txt` — repository references

Search and replace:
```
OLD: github.com/Neob1844/sost-core
NEW: github.com/sostcore/sost-core
```

## 8. DNS Verification (optional)

Verify the `sostcore.com` domain with GitHub:
1. Organization Settings > Verified domains
2. Add `sostcore.com`
3. Add the TXT record GitHub provides to your DNS
4. Click Verify

This shows a verified badge next to your organization name.
