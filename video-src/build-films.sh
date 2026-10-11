#!/usr/bin/env bash
# Build the two Watch films from their HTML sources (2026-10 rebuild).
#   ./build-films.sh <work-dir> <intro|mech|both>
# Each scene is a continuous timeline rendered by render2.js (page loaded once, window.frame(t) per
# frame), cross-faded with ffmpeg xfade, scored with a CC-BY track (credited on the end card),
# loudness-normalised to -18 LUFS like the previous films, faded in and out.
set -euo pipefail
W="$1"; WHICH="${2:-both}"
FF="$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
FPS=30; XF=0.8; WORKERS=${WORKERS:-4}
build() {
  local name="$1" page="$2" out="$3" music="$4"; shift 4; local DUR=("$@")
  local D="$W/$name"; mkdir -p "$D"
  echo "== $name: ${#DUR[@]} scenes"
  for i in "${!DUR[@]}"; do
    if [ ! -f "$D/seg$i.mp4" ]; then
      rm -rf "$D/s$i"
      node render2.js "$page?scene=$i" "$D/s$i" "${DUR[$i]}" $FPS $WORKERS >/dev/null
      "$FF" -y -framerate $FPS -i "$D/s$i/f_%05d.png" -c:v libx264 -preset medium -crf 14 -pix_fmt yuv420p "$D/seg$i.mp4" -loglevel error
      rm -rf "$D/s$i"
    fi
    echo "   scene $i ok (${DUR[$i]}s)"
  done
  local args=() filt="" off=0 prev="0:v"
  for i in "${!DUR[@]}"; do args+=(-i "$D/seg$i.mp4"); done
  for i in $(seq 1 $((${#DUR[@]}-1))); do
    off=$(python3 -c "print(round($off + ${DUR[$((i-1))]} - $XF, 3))")
    filt+="[$prev][$i:v]xfade=transition=fade:duration=$XF:offset=$off[v$i];"; prev="v$i"
  done
  "$FF" -y "${args[@]}" -filter_complex "${filt%;}" -map "[$prev]" -c:v libx264 -preset medium -crf 15 -pix_fmt yuv420p "$D/silent.mp4" -loglevel error
  local TOT
  TOT=$(python3 -c "print(round(sum([$(echo ${DUR[*]} | tr ' ' ',')])-$XF*(${#DUR[@]}-1),2))")
  "$FF" -y -i "$D/silent.mp4" -i "$music" \
    -filter_complex "[1:a]atrim=0:$TOT,asetpts=PTS-STARTPTS,loudnorm=I=-18:TP=-1.5:LRA=11,afade=t=in:st=0:d=1.5,afade=t=out:st=$(python3 -c "print(round($TOT-4,2))"):d=4[a]" \
    -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 22 -pix_fmt yuv420p -c:a aac -b:a 160k -ar 44100 -shortest -movflags +faststart "$out" -loglevel error
  echo "   -> $out (${TOT}s)"
}
if [ "$WHICH" = intro ] || [ "$WHICH" = both ]; then
  # Convergence + Starfire (10 s crossfade): the film outlasts one track
  [ -f assets/music/intro-score.mp3 ] || "$FF" -loglevel error -y -i assets/music/Convergence.mp3 -i assets/music/Starfire.mp3 \
    -filter_complex "[0:a][1:a]acrossfade=d=10:c1=tri:c2=tri[a]" -map "[a]" -b:a 320k assets/music/intro-score.mp3
  build intro film-intro.html "$W/sost-intro.mp4" assets/music/intro-score.mp3 $(python3 -c "import re;print(' '.join(re.findall(r'dur:(\\d+)',open('film-intro.html').read())))")
fi
if [ "$WHICH" = mech ] || [ "$WHICH" = both ]; then
  build mech film-mech.html "$W/sost-mechanisms.mp4" assets/music/VictorLux.mp3 8 9 13 10 12 13 12 13 12 13 13 14 9
fi
