#!/usr/bin/env bash
# SOST x GeaSpirit promo PRO — splash intro + content + SOST watermark + loud audio
set -euo pipefail
FF=/tmp/ffbin/ffmpeg
DL="/mnt/c/Users/ferna/Downloads"
W=/tmp/gxvideo
mkdir -p "$W/seg"
SOSTW="$W/sost_t.png"
SPLASH="$W/splash.png"
AUDIO="$DL/SOVEREIGN STOCK TOKEN - SOST Token - Creation of wealth_audio.aac"
XF=0.7; CD=9; SD=8

mapfile -t LINES < "$W/manifest.txt"
M=${#LINES[@]}          # content scenes (13)
N=$((M+1))              # incl. splash

echo ">> splash"
"$FF" -y -hide_banner -loglevel error -loop 1 -t $SD -i "$SPLASH" \
  -vf "scale=1920:1080,setsar=1,fps=30,format=yuv420p,fade=t=in:st=0:d=1.2" \
  -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg/seg_0.mp4"

echo ">> $M content scenes (with title + SOST corner)"
i=0
for ln in "${LINES[@]}"; do
  SRC="${ln%%:::*}"; IN="${ln##*:::}"; T="$W/png/t$i.png"
  FG="[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,format=yuv420p[bg];"
  FG+="[1:v]format=rgba,fade=t=in:st=0.4:d=0.7:alpha=1,fade=t=out:st=7.9:d=0.8:alpha=1[ti];"
  FG+="[2:v]scale=118:-1,format=rgba,colorchannelmixer=aa=0.80[wm];"
  FG+="[bg][ti]overlay=0:0[b1];[b1][wm]overlay=W-w-42:36[v]"
  "$FF" -y -hide_banner -loglevel error -ss "$IN" -t $CD -i "$DL/$SRC" -loop 1 -t $CD -i "$T" -loop 1 -t $CD -i "$SOSTW" \
    -filter_complex "$FG" -map "[v]" -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg/seg_$((i+1)).mp4"
  echo "   [$((i+1))/$M] $SRC"
  i=$((i+1))
done

echo ">> xfade chain (splash 8s + 13x9s) + loud audio"
# durations array
DUR=($SD); for ((k=0;k<M;k++)); do DUR+=($CD); done
TOTAL=$(awk -v sd=$SD -v cd=$CD -v m=$M -v xf=$XF 'BEGIN{printf "%.2f", sd+m*cd-(m)*xf}')
# (N-1)=M xfades
INARGS=(); for ((k=0;k<N;k++)); do INARGS+=(-i "$W/seg/seg_$k.mp4"); done

FG=""; prev="0:v"; cum=0
for ((k=1;k<N;k++)); do
  cum=$(awk -v c="$cum" -v d="${DUR[$((k-1))]}" 'BEGIN{print c+d}')
  off=$(awk -v c="$cum" -v k="$k" -v xf=$XF 'BEGIN{printf "%.2f", c-k*xf}')
  if [ "$k" -lt $((N-1)) ]; then out="[x$k]"; else out="[vx]"; fi
  FG+="[$prev][$k:v]xfade=transition=fade:duration=$XF:offset=$off$out;"
  prev="x$k"
done
FOUT=$(awk -v t="$TOTAL" 'BEGIN{printf "%.2f", t-1.5}')
AOUT=$(awk -v t="$TOTAL" 'BEGIN{printf "%.2f", t-4}')
FG+="[vx]fade=t=out:st=$FOUT:d=1.5[vout];"
FG+="[${N}:a]loudnorm=I=-15:TP=-1.5:LRA=11,atrim=0:$TOTAL,afade=t=in:st=0:d=2,afade=t=out:st=$AOUT:d=4[aout]"

OUT="$DL/SOST_x_GeaSpirit_2min.mp4"
"$FF" -y -hide_banner -loglevel error "${INARGS[@]}" -i "$AUDIO" \
  -filter_complex "$FG" -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart \
  -t "$TOTAL" "$OUT"

echo ">> DONE $OUT"
/tmp/ffbin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
/tmp/ffbin/ffmpeg -hide_banner -i "$OUT" -af volumedetect -f null - 2>&1 | grep -iE "mean_volume|max_volume"
ls -la "$OUT" | awk '{print $5" bytes"}'
