#!/usr/bin/env bash
# Rebuild sost-mechanisms.mp4: new title and end cards, a colour plate and the corner mark
# over the middle, and a score.
#
# The middle of this film is a finished render with no source project. It cannot be
# re-composed, and painting over it is what produced the ghost-box defect the first time. So
# the middle is left intact and two things are added ON TOP of it:
#
#   - an ambient colour plate, screen-blended in at 0.22. Screen lifts the near-black
#     background and leaves the bright captions alone. Half that opacity is invisible;
#     double it and the frame floods magenta and reads worse than the original.
#   - the corner mark, with the same pulsing glow the rest of the brand uses
#
# The two cards ARE rebuilt outright from mech-title.html / mech-end.html and cross-faded in.
#
#   Segment   Source                              Span
#   title     mech-title.html                     0.00 -> 10.00
#   middle    original film + plate + mark        9.40 -> 121.60
#   end       mech-end.html                       121.00 -> 130.90
#
# usage: ./build-mechanisms.sh <work-dir> <input.mp4> <output.mp4> [music.mp3]
set -euo pipefail
W="$1"; IN="$2"; OUT="$3"; MUSIC="${4:-}"
FF="$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
FPS=30; XF=0.6; LOOP=4.8

# Guard on the LAST artefact, not the first: guarding on $W/title meant an interrupted run
# left the directory behind and the next run skipped every render, corner included.
if [ ! -f "$W/corner/f_00071.png" ]; then
  ( node render.js frames mech-title.html "$W/title" 0 $LOOP $FPS >/dev/null 2>&1 && echo "    title rendered" ) &
  ( node render.js frames mech-end.html   "$W/end"   0 $LOOP $FPS >/dev/null 2>&1 && echo "    end rendered" ) &
  ( node render.js frames ambient-only.html "$W/plate" 0 $LOOP $FPS >/dev/null 2>&1 && echo "    plate rendered" ) &
  wait
  ( ALPHA=1 node render.js frames corner-overlay.html "$W/corner" 0 2.4 $FPS >/dev/null 2>&1 && echo "    corner rendered" )
fi

"$FF" -y -framerate $FPS -i "$W/title/f_%05d.png" -c:v libx264 -pix_fmt yuv420p -crf 15 "$W/cyc_title.mp4" -loglevel error
"$FF" -y -framerate $FPS -i "$W/end/f_%05d.png"   -c:v libx264 -pix_fmt yuv420p -crf 15 "$W/cyc_end.mp4"   -loglevel error
"$FF" -y -framerate $FPS -i "$W/plate/f_%05d.png" -c:v libx264 -pix_fmt yuv420p -crf 17 "$W/cyc_plate.mp4" -loglevel error
"$FF" -y -framerate $FPS -i "$W/corner/f_%05d.png" -c:v qtrle -pix_fmt argb "$W/cyc_corner.mov" -loglevel error

"$FF" -y -stream_loop 6  -i "$W/cyc_title.mp4" -t 10.0  -c:v libx264 -pix_fmt yuv420p -crf 15 "$W/seg_title.mp4" -loglevel error
"$FF" -y -stream_loop 6  -i "$W/cyc_end.mp4"   -t 9.9   -c:v libx264 -pix_fmt yuv420p -crf 15 "$W/seg_end.mp4"   -loglevel error
"$FF" -y -stream_loop 30 -i "$W/cyc_plate.mp4" -t 112.2 -c:v libx264 -pix_fmt yuv420p -crf 17 "$W/plate.mp4"     -loglevel error
"$FF" -y -stream_loop 60 -i "$W/cyc_corner.mov" -t 112.2 -c:v qtrle -pix_fmt argb "$W/corner.mov"                -loglevel error

# middle: original, lifted a little, colour plate screened in, mark on top
"$FF" -y -ss 9.4 -to 121.6 -i "$IN" -i "$W/plate.mp4" -i "$W/corner.mov" -an \
  -filter_complex "[0:v]eq=saturation=1.18:contrast=1.05[base];\
                   [base][1:v]blend=all_mode=screen:all_opacity=0.22[lit];\
                   [lit][2:v]overlay=0:0:format=auto[v]" \
  -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/seg_mid.mp4" -loglevel error

"$FF" -y -i "$W/seg_title.mp4" -i "$W/seg_mid.mp4" -i "$W/seg_end.mp4" \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=$XF:offset=9.4[a];\
                   [a][2:v]xfade=transition=fade:duration=$XF:offset=121.0[v]" \
  -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 17 "$W/silent.mp4" -loglevel error

# `ffmpeg -i` with no output exits 1, and under `set -o pipefail` that killed the script
# here on the first run -- after every frame had already been rendered. The bundled ffmpeg
# ships without ffprobe, so read the duration from ffmpeg's own banner with pipefail off.
set +o pipefail
TOT=$("$FF" -i "$W/silent.mp4" 2>&1 | grep -o 'Duration: [0-9:.]*' | head -1 | cut -d' ' -f2 \
      | awk -F: '{printf "%.2f", $1*3600+$2*60+$3}')
set -o pipefail
[ -n "$TOT" ] || { echo "  could not read duration of silent.mp4" >&2; exit 1; }
if [ -n "$MUSIC" ]; then
  "$FF" -y -i "$W/silent.mp4" -i "$MUSIC" \
    -filter_complex "[1:a]atrim=0:$TOT,loudnorm=I=-18:TP=-1.5:LRA=11,afade=t=in:st=0:d=2.5,afade=t=out:st=$(python3 -c "print(round($TOT-4,2))"):d=4[a]" \
    -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -c:a aac -b:a 160k -ar 44100 -shortest -movflags +faststart "$OUT" -loglevel error
else
  "$FF" -y -i "$W/silent.mp4" -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -movflags +faststart "$OUT" -loglevel error
fi
echo "  -> $OUT  (${TOT}s)"
