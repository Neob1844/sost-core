#!/usr/bin/env bash
# SOST x GeaSpirit promo — assemble using PNG title overlays (no drawtext needed)
set -euo pipefail
FF=/tmp/ffbin/ffmpeg
DL="/mnt/c/Users/ferna/Downloads"
W=/tmp/gxvideo
mkdir -p "$W/seg"

mapfile -t LINES < "$W/manifest.txt"
N=${#LINES[@]}
echo ">> $N segments"

i=0
for ln in "${LINES[@]}"; do
  SRC="${ln%%:::*}"; IN="${ln##*:::}"
  PNG="$W/png/t$i.png"
  FG="[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,format=yuv420p[bg];"
  FG+="[1:v]format=rgba,fade=t=in:st=0.4:d=0.7:alpha=1,fade=t=out:st=8.9:d=0.8:alpha=1[ov];"
  FG+="[bg][ov]overlay=0:0:format=auto,format=yuv420p[v]"
  "$FF" -y -hide_banner -loglevel error -ss "$IN" -t 10 -i "$DL/$SRC" -loop 1 -t 10 -i "$PNG" \
    -filter_complex "$FG" -map "[v]" -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg/seg_$i.mp4"
  echo "   [$((i+1))/$N] $SRC"
  i=$((i+1))
done

echo ">> xfade chain + audio"
INARGS=(); for ((k=0;k<N;k++)); do INARGS+=(-i "$W/seg/seg_$k.mp4"); done
AUDIO="$DL/SOVEREIGN STOCK TOKEN - SOST Token - Creation of wealth_audio_from_42s.mp4"
TOTAL=$(awk -v n="$N" 'BEGIN{printf "%.2f", n*10-(n-1)*0.7}')
AFOUT=$(awk -v t="$TOTAL" 'BEGIN{printf "%.2f", t-4}')

FG=""; prev="0:v"
for ((k=1;k<N;k++)); do
  off=$(awk -v k="$k" 'BEGIN{printf "%.2f", k*9.3}')
  if [ "$k" -lt $((N-1)) ]; then out="[x$k]"; else out="[vout]"; fi
  FG+="[$prev][$k:v]xfade=transition=fade:duration=0.7:offset=$off$out;"
  prev="x$k"
done
FG+="[${N}:a]atrim=0:$TOTAL,afade=t=in:st=0:d=2.5,afade=t=out:st=$AFOUT:d=4,volume=0.95[aout]"

OUT="$DL/SOST_x_GeaSpirit_2min.mp4"
"$FF" -y -hide_banner -loglevel error "${INARGS[@]}" -stream_loop -1 -i "$AUDIO" \
  -filter_complex "$FG" -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart \
  -t "$TOTAL" "$OUT"

echo ">> DONE $OUT ($TOTAL s)"
/tmp/ffbin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
ls -la "$OUT" | awk '{print $5" bytes"}'
