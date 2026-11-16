# Sovereign Stock Token — SOST · Brand Guide

Version 3.2 · 14 November 2026 · https://sostcore.com/brand/

## 1. Identity

| | |
|---|---|
| Name | **Sovereign Stock Token** |
| Ticker | **SOST** |
| How to write it | **Sovereign Stock Token — SOST** (name, dash, ticker); **SOST** alone where only the ticker fits |
| Asset | Native coin of the SOST proof-of-work blockchain (8 decimals) |
| Official website | https://sostcore.com |
| Source code | https://github.com/Neob1844/sost-core |

## 2. Logo hierarchy

**Current official logo:** a gold **Σ** in its multicolour orbit, with no outer ring.
It is the only logo to use for exchanges, listings, wallets, media and partners.

**Legacy logo:** historical use only — the plain red **Σ** on black.
It identified SOST before the current logo was adopted. It is shown for reference only and must not be presented as the current logo.

No other emblem, variant or symbol is an official SOST logo.

## 3. Primary official logo — files

| File | Size | Use |
|---|---|---|
| `primary/sost-logo-2048-transparent.png` | 2048 × 2048 | Large formats · upscaled ×4 (see note) |
| `primary/sost-logo-1024-transparent.png` | 1024 × 1024 | General use · upscaled (see note) |
| `primary/sost-logo-512-transparent.png` | 512 × 512 | Web, documents |
| `primary/sost-logo-{256,128,64,32}-transparent.png` | 256 – 32 | Small formats (64 and 32 px lightly sharpened) |
| `primary/sost-logo-{2048 … 32}-dark.png` | | Same artwork on black (#000000) |
| `primary/sost-logo-native.png` | 552 × 413 | The logo at the native resolution of the approved artwork |
| `primary/sost-logo-master-hd.png` | 2206 × 1651 | HD master: ×4 super-resolution upscale of the approved artwork |
| `icons/sost-icon-{1024 … 32}.png` | 1024 – 32 | Square token icon, transparent, **circle-safe** (fits a round crop) — for exchange listings, wallets, token lists |
| `icons/sost-avatar-{1024,512}-dark.png` | 1024, 512 | Square avatar on black, circle-safe — social profiles, app stores |
| `icons/favicon/` | 16 – 512 | favicon.ico, PNG favicons, Apple touch icon, Android / PWA icons (incl. maskable) |
| `icons/social/og-sost-1200x630.png` | 1200 × 630 | Social / Open Graph card |

**Resolution, stated plainly:** the approved artwork carries about 552 px of logo width (`sost-logo-native.png`). The HD master and the 1024 / 2048 px files are ×4 super-resolution upscales of that same artwork: nothing was redrawn, but they are not native high-resolution originals. 512 px and smaller are downscales.

All transparent files have a real, clean alpha channel: since v3.2 the orbit edge carries no dark matte, outline or specks, so the logo looks the same on white as on black. The logo is a luminous illustration; PNG is the canonical format (no vector version is provided, because tracing would change the artwork).

## 4. Legacy logo — files (historical use only)

| File | Size |
|---|---|
| `legacy/sost-legacy-logo-1024.png`, `-512.png` | Rounded icon, transparent corners |
| `legacy/sost-legacy-square-1024.png`, `-512.png` | Square icon |

## 5. Colours

Measured on the official logo (median of the saturated pixels of each colour band).

| Role | Hex |
|---|---|
| Sigma gold | `#FAC950` |
| Gold light | `#FFE475` |
| Gold deep | `#E1A62E` |
| Gold highlight | `#FEFAD1` |
| Orbit red | `#FC1819` |
| Orbit orange | `#FF7900` |
| Orbit yellow | `#FFF100` |
| Orbit green | `#40DF28` |
| Orbit cyan | `#00C1FA` |
| Orbit blue | `#0067F1` |
| Orbit violet | `#8100F5` |
| Orbit magenta | `#E300C0` |
| Background black | `#000000` |
| SOST red (website accent; colour of the legacy Σ) | `#FB010D` |

Typefaces on sostcore.com: Space Grotesk (headings), Inter (text), IBM Plex Mono (data).

## 6. Clear space and minimum size

- **Clear space:** keep free space of at least **10 % of the logo width** on every side of the visible artwork (`preview/sost-clear-space.png`).
- **Minimum size:** 24 px on screen; **32 px or more recommended**. In print, 10 mm minimum (`preview/sost-minimum-size.png`).

## 7. Backgrounds

- **Dark backgrounds** (black or very dark) are preferred, as on sostcore.com: `preview/sost-logo-on-dark.png`.
- **Light backgrounds:** use the transparent files; their edge is clean on white: `preview/sost-logo-on-light.png`.
- **Round crops (exchanges, wallets):** the icons are circle-safe: `preview/sost-exchange-circle-crop.png`.

## 8. Correct use

- Use the files of this kit as supplied.
- Scale uniformly.
- Use the circle-safe icons where the platform crops to a circle.
- Write the name as **Sovereign Stock Token — SOST**, or **SOST** where only the ticker fits.

## 9. Incorrect use

- Stretching, skewing, rotating or cropping the logo; changing the proportions of the orbit or the Σ.
- Recolouring (the Σ is always gold), adding outlines, shadows, filters or effects.
- Redrawing the logo, tracing it to vector, or recreating it with generative tools.
- Adding a ring, circle, frame or badge around the logo.
- Placing the logo on busy backgrounds that reduce its legibility, or inside the clear space of other marks.
- Presenting the legacy logo as the current logo, or using any other emblem as a SOST logo.
- Any other name or variant of the name: the project is **Sovereign Stock Token — SOST**.
- Suggesting endorsements, partnerships or returns that SOST has not announced.

## 10. Contents of the kit

```
SOST_Brand_Kit_v3.2/
  primary/   official logo: native-resolution file, HD master (upscaled), 2048–32 px transparent and on black
  icons/     circle-safe token icons 1024–32, dark avatars, favicon set, social card
  legacy/    legacy red Σ (historical use only)
  guide/     this guide (PDF and Markdown)
  preview/   logo on dark and light, circle crop, clear space, minimum size, legacy preview
  README.txt
  SHA256SUMS.txt
```

Every file is listed with its SHA-256 in `SHA256SUMS.txt`.
