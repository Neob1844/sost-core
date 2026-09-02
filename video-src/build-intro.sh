#!/usr/bin/env bash
# Build sost-intro.mp4 ("SOST in 2 Minutes — V15") from intro.html.
#
# Nine scenes, cross-faded, over a scored soundtrack. Each scene is rendered as ONE
# GeaAmbient.LOOP cycle (4.8 s = 144 frames) and repeated for its duration: every motion in
# the film -- aurora, particles, grid drift, the corner mark's pulse -- is a closed path with
# that period, so the repeat is seamless and the film costs 1,296 rendered frames instead of
# 2,742. Scenes render in parallel because each is an independent browser.
#
# usage: ./build-intro.sh <work-dir> <output.mp4> [music.mp3]
set -euo pipefail
W="$1"; OUT="$2"; MUSIC="${3:-}"
FF="$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
FPS=30; XF=0.7; LOOP=4.8; JOBS=3
DUR=(10 10 11 12 11 12 11 10 10)

echo "  rendering ${#DUR[@]} scenes, ${JOBS} at a time"
pids=()
for i in "${!DUR[@]}"; do
  ( node render.js frames "intro.html?scene=$i" "$W/s$i" 0 $LOOP $FPS >/dev/null 2>&1 \
      && echo "    scene $i rendered" ) &
  pids+=($!)
  if (( ${#pids[@]} >= JOBS )); then wait "${pids[0]}"; pids=("${pids[@]:1}"); fi
done
wait

for i in "${!DUR[@]}"; do
  "$FF" -y -framerate $FPS -i "$W/s$i/f_%05d.png" -c:v libx264 -pix_fmt yuv420p -crf 15 "$W/cyc$i.mp4" -loglevel error
  "$FF" -y -stream_loop 6 -i "$W/cyc$i.mp4" -t "${DUR[$i]}" -c:v libx264 -pix_fmt yuv420p -crf 15 "$W/seg$i.mp4" -loglevel error
done

args=(); filt=""; off=0; prev="0:v"
for i in "${!DUR[@]}"; do args+=(-i "$W/seg$i.mp4"); done
for i in $(seq 1 $((${#DUR[@]}-1))); do
  off=$(python3 -c "print(round($off + ${DUR[$((i-1))]} - $XF, 3))")
  filt+="[$prev][$i:v]xfade=transition=fade:duration=$XF:offset=$off[v$i];"
  prev="v$i"
done
filt="${filt%;}"
"$FF" -y "${args[@]}" -filter_complex "$filt" -map "[$prev]" \
  -c:v libx264 -pix_fmt yuv420p -crf 17 "$W/silent.mp4" -loglevel error

# `ffmpeg -i` with no output exits 1, and under `set -o pipefail` that killed the script
# here on the first run -- after every frame had already been rendered. The bundled ffmpeg
# ships without ffprobe, so read the duration from ffmpeg's own banner with pipefail off.
set +o pipefail
TOT=$("$FF" -i "$W/silent.mp4" 2>&1 | grep -o 'Duration: [0-9:.]*' | head -1 | cut -d' ' -f2 \
      | awk -F: '{printf "%.2f", $1*3600+$2*60+$3}')
set -o pipefail
[ -n "$TOT" ] || { echo "  could not read duration of silent.mp4" >&2; exit 1; }
if [ -n "$MUSIC" ]; then
  # Fade the last 3 s so the film ends rather than stops.
  "$FF" -y -i "$W/silent.mp4" -i "$MUSIC" \
    -filter_complex "[1:a]atrim=0:$TOT,loudnorm=I=-18:TP=-1.5:LRA=11,afade=t=in:st=0:d=2,afade=t=out:st=$(python3 -c "print(round($TOT-3,2))"):d=3[a]" \
    -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -c:a aac -b:a 160k -ar 44100 -shortest -movflags +faststart "$OUT" -loglevel error
else
  "$FF" -y -i "$W/silent.mp4" -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -movflags +faststart "$OUT" -loglevel error
fi
echo "  -> $OUT  (${TOT}s)"
