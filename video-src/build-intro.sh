#!/usr/bin/env bash
# Build sost-intro.mp4 ("SOST in 2 Minutes — V15") from intro.html.
#
# Nine scenes, cross-faded. Scenes that carry the pulsing mark are rendered as
# one full 2.4 s pulse cycle (72 frames) and looped; the rest are stills held
# for their duration. Editing a claim means editing intro.html and re-running
# this script -- which is the whole point: the previous film could not be
# corrected because only its render survived.
#
# usage: ./build-intro.sh <work-dir> <output.mp4>
set -euo pipefail
W="$1"; OUT="$2"
FF="$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
FPS=30; XF=0.7
DUR=(10 10 11 12 11 12 11 10 10)
PULSE=(1 0 0 0 0 0 0 0 1)

for i in "${!DUR[@]}"; do
  d=${DUR[$i]}
  if [ "${PULSE[$i]}" = "1" ]; then
    node render.js frames "intro.html?scene=$i" "$W/s$i" 0 2.4 $FPS >/dev/null
    "$FF" -y -framerate $FPS -i "$W/s$i/f_%05d.png" -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/cyc$i.mp4" -loglevel error
    "$FF" -y -stream_loop 8 -i "$W/cyc$i.mp4" -t $d -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/seg$i.mp4" -loglevel error
  else
    node render.js still "intro.html?scene=$i" "$W/s$i.png" 0 >/dev/null
    "$FF" -y -loop 1 -i "$W/s$i.png" -t $d -r $FPS -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/seg$i.mp4" -loglevel error
  fi
  echo "  scene $i  ${d}s"
done

# Chain the cross-fades: each offset is the running length minus one fade.
args=(); filt=""; off=0; prev="0:v"
for i in "${!DUR[@]}"; do args+=(-i "$W/seg$i.mp4"); done
for i in $(seq 1 $((${#DUR[@]}-1))); do
  off=$(python3 -c "print(round($off + ${DUR[$((i-1))]} - $XF, 3))")
  filt+="[$prev][$i:v]xfade=transition=fade:duration=$XF:offset=$off[v$i];"
  prev="v$i"
done
filt="${filt%;}"
"$FF" -y "${args[@]}" -filter_complex "$filt" -map "[$prev]" \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart "$OUT" -loglevel error
echo "  -> $OUT"
