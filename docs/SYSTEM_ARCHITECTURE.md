# SOST Protocol — Arquitectura del Sistema

## Diagrama General

```
┌─────────────────────────────────────────────────────────────────┐
│                        VPS (212.132.108.244)                     │
│  Ubuntu 24.04 · 4 vCPU · 8GB RAM · 80GB SSD                    │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  sost-node   │  │    nginx     │  │  sost-auth   │          │
│  │  :18232 RPC  │  │  :443 HTTPS  │  │  :8200 HTTP  │          │
│  │  :19333 P2P  │  │  :80 → 443   │  │  JWT tokens  │          │
│  │  chain.json  │  │  proxy_pass  │  │  auth.env    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘          │
│         │                  │                                     │
│         │    ┌─────────────┴─────────────┐                      │
│         │    │    /opt/sost/website/      │                      │
│         │    │    index.html              │                      │
│         │    │    sost-explorer.html      │                      │
│         │    │    sost-wallet.html        │                      │
│         │    │    sost-geaspirit.html     │                      │
│         │    │    sost-app/index.html     │                      │
│         │    │    ... (30+ HTML files)    │                      │
│         │    └───────────────────────────┘                      │
│         │                                                        │
│  ┌──────┴───────┐  ┌──────────────┐                             │
│  │  certbot     │  │  cron jobs   │                             │
│  │  SSL renewal │  │  health_check│                             │
│  │  auto-renew  │  │  auto_backup │                             │
│  └──────────────┘  │  log_rotate  │                             │
│                     │  node-status │                             │
│                     └──────────────┘                             │
└──────────────────────────────────────┬──────────────────────────┘
                                       │ SSH tunnel (autossh)
                                       │ Port 18232 forwarded
                                       │
┌──────────────────────────────────────┴──────────────────────────┐
│                     WSL (Windows local)                          │
│  Ubuntu 22.04 · 12GB RAM · 8 cores                              │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  sost-miner  │  │   autossh    │  │  sost-core   │          │
│  │  ConvergenceX│  │  tunnel mgr  │  │  git repo    │          │
│  │  8GB RAM     │  │  :18232 fwd  │  │  build/      │          │
│  │  CPU mining  │  │  auto-reconn │  │  22/22 tests │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │  GeaSpirit   │  │  Materials   │                             │
│  │  Python ML   │  │  Engine      │                             │
│  │  geaspirit/  │  │  materials/  │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## Puertos

| Puerto | Servicio | Acceso |
|--------|---------|--------|
| 443 | nginx HTTPS | Público (web) |
| 80 | nginx HTTP → redirect 443 | Público |
| 19333 | sost-node P2P | Público (blockchain peers) |
| 18232 | sost-node RPC | Localhost only (via SSH tunnel) |
| 8200 | sost-auth | Localhost only |

## Dominios

| Dominio | Destino | Contenido |
|---------|---------|-----------|
| sostcore.com | VPS nginx | Web principal, explorer, wallet, app |
| sostprotocol.com | VPS nginx (alias) | Mismo contenido que sostcore.com |
| seed.sostcore.com | VPS :19333 | P2P seed node (no web) |

## Flujo de datos

```
Miner (WSL) → SSH tunnel → Node (VPS) → P2P network
                                ↓
                           chain.json
                                ↓
                    Explorer (nginx static)
                                ↓
                         User browser
```

## Archivos críticos

| Archivo | Ubicación (VPS) | Función |
|---------|-----------------|---------|
| chain.json | /opt/sost/build/ | Estado completo de la blockchain |
| auth.env | /etc/sost/ | Credenciales del auth gateway |
| sost-node | /opt/sost/build/ | Binario del nodo |
| nginx config | /etc/nginx/sites-enabled/ | Config web |
| SSL certs | /etc/letsencrypt/live/ | Certificados HTTPS |

## Servicios systemd

| Servicio | Función | Restart policy |
|----------|---------|---------------|
| sost-node | Full node blockchain | Restart=always (verificar) |
| nginx | Web server | Restart=always (default) |
| sost-auth | Auth gateway | Restart=always (verificar) |

## Cron jobs (a instalar)

| Frecuencia | Script | Función |
|-----------|--------|---------|
| */5 * * * * | health_check.sh | Detectar y reparar caídas |
| * * * * * | node-status.sh | JSON status para explorer |
| 0 3 * * * | auto_backup.sh | Backup diario |
| 0 4 * * 0 | log_rotate.sh | Rotación de logs semanal |
