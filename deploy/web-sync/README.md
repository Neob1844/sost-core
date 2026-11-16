# sostcore.com ↔ GitHub synchronisation

The source of the public website is `website/` on branch `main` of `Neob1844/sost-core`.
The production web root (`/var/www/sost-website/website`) must be a copy of that directory,
except for the paths listed in `EXCLUDE.txt` (server-generated data, large audio, internal pages).

## Check for drift (read-only)

```bash
deploy/web-sync/web-drift-check.sh            # exit 0 = in sync, 1 = drift, 2 = error
```

It hashes every file on the server and in `website/` (git-tracked files) and lists
CHANGED / ONLY IN PROD / ONLY IN REPO, then every path skipped by `EXCLUDE.txt`
(grouped), so an exclusion never hides a new file silently. It fails if an excluded
path is tracked in git. It never writes to the server.

## Rules for every web change

1. **Before a deploy**, run the drift check against `origin/main`. If it reports anything,
   production has changes that are not in GitHub: bring them into `website/` and commit
   them first. Never deploy over unreported production changes.
2. Commit the change to `website/` (author/committer `Neob`) and push it to `main`
   **before** deploying. Deploy only from a committed tree, never from a working copy.
3. Back up the files you replace in `/opt/sost/web-backups/<UTC timestamp>-<label>/`.
4. Copy the files to the server, then run the drift check again; it must exit 0.
5. Record the deploy on the server (outside the web root):
   `echo "$(date -u +%FT%TZ) <commit> <label>" >> /opt/sost/web-deploys.log`
6. Changes made directly on the server (emergency fixes) are pulled into `website/`
   and committed the same day, using the drift check to find them.

## Never in GitHub

Secrets, tokens, `.env` files, RPC passwords, wallet files or keys, nginx/TLS private
configuration, server logs, backups, `*.bak`, and the generated paths in `EXCLUDE.txt`.
nginx routing that the site depends on is kept as sanitised snippets in `deploy/*.conf`.

## Not published automatically

Nothing deploys on push. Development branches (V17, Universal Assets, wSOST, Galaxy
experiments) stay out of `main`'s `website/` until their publication is authorised.
