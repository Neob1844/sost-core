# Matrix Legacy — original red splash (historical asset)

- Source: `website/index.html` lines 703–869 at `b94013cf` (origin/main), copied **unchanged** to
  `matrix-splash-v392.fragment.html` (sha256 `43cdbc28ec2b6d165ff8b2661505746a7f828b735c3e628213d82edefbf3ec53`). Check: `cmp <(git show b94013cf:website/index.html | sed -n 703,869p) matrix-splash-v392.fragment.html`.
- `matrix-legacy.html` plays it in isolation: `<base href="../../">` so the fragment's relative paths
  (`sost-logo.png?v=v392`, `js/retro-sounds.js`, `js/sost-pwa-install.js`) resolve, and `sessionStorage.splashShown`
  is cleared so it always plays. The keyframes `sostLogoPulse` (defined elsewhere in index.html) are restated in the wrapper.
- Behaviour of the original: full-screen overlay `#sost-splash` (z-index 99999), once per session
  (`sessionStorage.splashShown`); red Matrix rain on canvas (katakana/latin glyphs, white head, #fb010d / #cc0000 /
  #880000 trail); WebAudio drone + ticks; logo fades in 2.2–4 s; "SOST" typed from 5 s in JetBrains Mono (not the
  wordmark font); four terminal lines from 6.5 s; fade-out at 12 s. **It blocks the page for 12 s.**
- `playRandomMelody` / `nesToggleMute` belong to scripts not loaded here; the original guards the melody call,
  the mute button's `onclick` would throw if clicked (as on any page without sost-music.js).
