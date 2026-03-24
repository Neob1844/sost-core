# SOST Domain Matrix

## Source of Truth: `sostcore.com`

All website files live in `/website/` within the sost-core repository.
Both domains serve the SAME files from the SAME deployment directory.

## Domain Configuration

| Domain | Role | Webroot | Source |
|--------|------|---------|--------|
| **sostcore.com** | PRIMARY | /var/www/sostcore.com/ | git pull from sost-core/website/ |
| **sostprotocol.com** | MIRROR | /var/www/sostcore.com/ (symlink or same root) | Same files as sostcore |

## How to Keep Them Identical

On VPS, both nginx server blocks should point to the same webroot:
```nginx
# /etc/nginx/sites-enabled/sostcore
server {
    server_name sostcore.com www.sostcore.com;
    root /var/www/sostcore.com;
    # ...
}

# /etc/nginx/sites-enabled/sostprotocol
server {
    server_name sostprotocol.com www.sostprotocol.com;
    root /var/www/sostcore.com;  # SAME root — not a separate copy
    # ...
}
```

## Splash Configuration (unified)

| Property | Value | File |
|----------|-------|------|
| Type | Red Matrix Rain (canvas) | index.html + sost-app/index.html |
| Logo size | 180×180px, border-radius:20% | Same |
| Duration | **12 seconds** | Same |
| Logo emerge | 2.2s → 4.0s | Same |
| Title typing | 5.0s (120ms/char) | Same |
| Terminal lines | 6.5s (2.5s animation each) | Same |
| Music | playRandomMelody() + playRetroSplashMusic(12) | Same |
| Ambient | 55Hz drone + bandpass noise (12s) | Same |

## What Must NOT Diverge

- Splash screen (sizing, duration, animations)
- CRT effects and retro sounds
- Explorer and wallet functionality
- Materials Engine demo page
- API proxy configuration
- Security headers

## Deploy

```bash
cd /opt/sost && git pull origin main
cp -r website/* /var/www/sostcore.com/
# Both domains now serve identical content
```
