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
| Logo size | 240×240px | index.html + sost-app/index.html |
| Title size | 23px, 4px spacing | Same |
| Lines size | 15px | Same |
| Duration | **7 seconds** | Same |
| Line timing | 2500 + i×900ms | Same |
| Music | playRetroSplashMusic(7) | Same |

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
