# SOST video source project

The two films on the Watch chooser are built from the HTML in this directory.

This exists because of a specific failure. The original films were only ever
rendered — there was no project behind them. When a caption went out of date and
the logo changed shape, the only available repair was to paint over the finished
pixels, which left the old logo's rounded rectangle and its shadow visible
underneath the new mark. That defect shipped to production. A one-line factual
change should not cost a re-authoring, and a corrected logo should not leave a
ghost box behind it.

So: every card is HTML, every frame is a pure function of its timestamp, and any
claim can be corrected by editing a file and re-running a script.

## Layout

    lib/brand.css      colours, type, and the mark. Single source of truth.
    lib/sost-logo.png  the current superellipse mark (84.4% fill, clean alpha)
    mech-title.html    sost-mechanisms.mp4 title card
    mech-end.html      sost-mechanisms.mp4 end card
    intro.html         sost-intro.mp4, all nine scenes, selected by ?scene=
    render.js          headless Chromium frame renderer
    build-intro.sh     intro.html            -> sost-intro.mp4
    build-mechanisms.sh  replaces both cards -> sost-mechanisms.mp4
    archive/           superseded films, kept out of website/ on purpose

## Render commands

    W=/tmp/sostvid && mkdir -p $W

    # SOST in 2 Minutes — V15   (9 scenes, 91.4 s)
    cd video-src && ./build-intro.sh $W ../website/sost-intro.mp4

    # SOST Mechanisms           (cards rebuilt, middle untouched, 2:10.90)
    cd video-src && ./build-mechanisms.sh $W ../website/sost-mechanisms.mp4 \
                                             ../website/sost-mechanisms.mp4

    # posters, from the assembled film rather than from the HTML
    ffmpeg -y -ss 4.0 -i ../website/sost-intro.mp4      -frames:v 1 -q:v 2 \
              ../website/sost-intro-poster.jpg
    ffmpeg -y -ss 3.0 -i ../website/sost-mechanisms.mp4 -frames:v 1 -q:v 2 \
              ../website/sost-mechanisms-poster.jpg

A single frame, for checking a change quickly:

    node render.js still mech-title.html /tmp/t.png 1.2
    node render.js still "intro.html?scene=4" /tmp/s4.png 0

## Two rules that matter

**The glow is a `filter: drop-shadow` on the `<img>`, never a `box-shadow`.**
`drop-shadow` follows the PNG's alpha, so the halo takes the superellipse's
shape. `box-shadow` traces the element's rectangle and produces exactly the
ghost box this project was written to remove.

**Fonts are local.** `brand.css` binds DejaVu by `local()`. A render must never
depend on the network, and a missing face must never fall back silently — the
end card's globe was an emoji until it rendered as tofu, and it is inline SVG now.

## What the films may say

`docs/SOST_INTRO_V15_VIDEO_SPEC.md` marks every claim CURRENT, STALE or VERIFY.
`intro.html` uses only CURRENT ones. PoPC is deliberately absent: the site still
carries the superseded DEX framing in places. The BTC leg of the Atomic Swap is
absent for the same reason — there is no current public statement of its gate
state. Neither belongs in a film until the site settles.
