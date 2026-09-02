#!/usr/bin/env bash
# Rebuild sost-mechanisms.mp4's title and end cards from the HTML source.
#
# The original film only ever existed as a render, so its title/end cards had a
# logo baked into the pixels. Overlaying a new mark on top left the old tile's
# rounded rectangle and shadow visible underneath. This script does not overlay:
# it REPLACES both card segments outright and cross-fades them into the
# untouched middle of the film.
#
#   Segment      Source                       Span
#   title        mech-title.html (rendered)    0.00 -> 10.00
#   middle       original film, untouched      9.40 -> 121.60
#   end          mech-end.html (rendered)      121.00 -> 130.90
#
# usage: ./build-mechanisms.sh <work-dir> <input.mp4> <output.mp4>
set -euo pipefail
W="$1"; IN="$2"; OUT="$3"
FF="$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
FPS=30; XF=0.6

# One rendered pulse cycle (2.4 s) looped to fill each card's span.
"$FF" -y -framerate $FPS -i "$W/title/f_%05d.png" -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/cyc_title.mp4" -loglevel error
"$FF" -y -framerate $FPS -i "$W/end/f_%05d.png"   -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/cyc_end.mp4"   -loglevel error
"$FF" -y -stream_loop 6 -i "$W/cyc_title.mp4" -t 10.0 -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/seg_title.mp4" -loglevel error
"$FF" -y -stream_loop 6 -i "$W/cyc_end.mp4"   -t 9.9  -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/seg_end.mp4"   -loglevel error

# The middle of the film is copied through untouched.
"$FF" -y -ss 9.4 -to 121.6 -i "$IN" -an -c:v libx264 -pix_fmt yuv420p -crf 16 "$W/seg_mid.mp4" -loglevel error

# Two cross-fades. offset = (length so far) - XF
"$FF" -y -i "$W/seg_title.mp4" -i "$W/seg_mid.mp4" -i "$W/seg_end.mp4" \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=$XF:offset=9.4[a];\
                   [a][2:v]xfade=transition=fade:duration=$XF:offset=121.0[v]" \
  -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart "$OUT" -loglevel error
echo "  -> $OUT"
