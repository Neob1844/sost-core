#!/usr/bin/env bash
set -euo pipefail
FF=/tmp/ffbin/ffmpeg
DL="/mnt/c/Users/ferna/Downloads"
W=/tmp/gxvideo
mkdir -p "$W/seg"
SOSTW="$W/sostwm.png"; FINBG="$W/finale_bg.png"
AUDIO="$DL/SOVEREIGN STOCK TOKEN - SOST Token - Creation of wealth_audio.aac"
XF=0.7; SD=8

# splash from animated frames
echo ">> splash (animated pulsing logos)"
"$FF" -y -hide_banner -loglevel error -framerate 30 -i "$W/splashfr/f%04d.png" \
  -vf "format=yuv420p,fade=t=in:st=0:d=1.2" -t $SD -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg/seg_0.mp4"

# --- remote-sensing montage for the GeaSpirit "OPEN DATA + SATELLITE" scene ---
PH="$W/photos"
sc(){ local fr=$(awk -v d="$2" 'BEGIN{print int(d*30)}'); "$FF" -y -hide_banner -loglevel error -loop 1 -t "$2" -i "$1" \
  -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,setsar=1,format=yuv420p" \
  -frames:v $fr -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$3"; }
for n in 0 1 2 3 4 5; do sc "$PH/m$n.png" 4.1 "$W/z$n.mp4"; done   # STATIC photos (no jitter)
"$FF" -y -hide_banner -loglevel error -i "$W/z0.mp4" -i "$W/z1.mp4" -i "$W/z2.mp4" -i "$W/z3.mp4" -i "$W/z4.mp4" -i "$W/z5.mp4" \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=3.6[a1];[a1][2:v]xfade=transition=fade:duration=0.5:offset=7.2[a2];[a2][3:v]xfade=transition=fade:duration=0.5:offset=10.8[a3];[a3][4:v]xfade=transition=fade:duration=0.5:offset=14.4[a4];[a4][5:v]xfade=transition=fade:duration=0.5:offset=18.0,format=yuv420p[v]" \
  -map "[v]" -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg5photos.mp4"
# ConvergenceX logo — grows from small to big (de menos a mas)
"$FF" -y -hide_banner -loglevel error -i "$W/logoframe.png" \
  -vf "scale=2560:1440,zoompan=z='min(zoom+0.00031,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=255:s=1920x1080:fps=30,setsar=1,format=yuv420p" \
  -frames:v 255 -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg9logo.mp4"
# Sovereign gold coin — slow push-in (acercandose lentamente)
"$FF" -y -hide_banner -loglevel error -i "$W/coinframe.png" \
  -vf "scale=2560:1440,zoompan=z='min(zoom+0.0004,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=255:s=1920x1080:fps=30,setsar=1,format=yuv420p" \
  -frames:v 255 -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg10coin.mp4"
echo ">> montage (6 photos) + ConvergenceX logo + gold coin built"

mapfile -t LINES < "$W/manifest3.txt"
M=${#LINES[@]}; N=$((M+1))
DUR=($SD)
i=0
for ln in "${LINES[@]}"; do
  IFS=':::' read -r a b c d <<<"$ln"   # not used; manual parse below
  SRC="${ln%%:::*}"; r="${ln#*:::}"; IN="${r%%:::*}"; r="${r#*:::}"; D="${r%%:::*}"; MODE="${r##*:::}"
  case "$SRC" in /*) SP="$SRC";; *) SP="$DL/$SRC";; esac
  DUR+=("$D")
  S=$((i+1))
  if [ "$MODE" = "f" ]; then
    echo "   [$S/$N] FINALE $SRC"
    "$FF" -y -hide_banner -loglevel error -ss "$IN" -t "$D" -i "$SP" -loop 1 -t "$D" -i "$FINBG" \
      -filter_complex "[1:v]fps=30,setsar=1,format=yuv420p[bg];[0:v]scale=1600:-1,setsar=1,fps=30,format=yuv420p[fg];[bg][fg]overlay=160:150,format=yuv420p[v]" \
      -map "[v]" -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg/seg_$S.mp4"
  elif [ "$MODE" = "l" ]; then
    echo "   [$S/$N] LOGO $SRC"
    "$FF" -y -hide_banner -loglevel error -ss "$IN" -t "$D" -i "$SP" -loop 1 -t "$D" -i "$SOSTW" \
      -filter_complex "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,format=yuv420p[bg];[1:v]scale=118:-1,format=rgba,colorchannelmixer=aa=0.90[wm];[bg][wm]overlay=W-w-42:36,format=yuv420p[v]" \
      -map "[v]" -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg/seg_$S.mp4"
  else
    T="$W/png/t$i.png"; FO=$(awk -v d="$D" 'BEGIN{printf "%.2f", d-1.1}')
    FG="[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,format=yuv420p[bg];"
    FG+="[1:v]format=rgba,fade=t=in:st=0.4:d=0.7:alpha=1,fade=t=out:st=$FO:d=0.8:alpha=1[ti];"
    FG+="[2:v]scale=118:-1,format=rgba,colorchannelmixer=aa=0.90[wm];"
    FG+="[bg][ti]overlay=0:0[b1];[b1][wm]overlay=W-w-42:36[v]"
    "$FF" -y -hide_banner -loglevel error -ss "$IN" -t "$D" -i "$SP" -loop 1 -t "$D" -i "$T" -loop 1 -t "$D" -i "$SOSTW" \
      -filter_complex "$FG" -map "[v]" -an -r 30 -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p "$W/seg/seg_$S.mp4"
    echo "   [$S/$N] $SRC (${D}s)"
  fi
  i=$((i+1))
done

echo ">> xfade chain + loud audio"
TOTAL=$(printf '%s\n' "${DUR[@]}" | awk -v xf=$XF -v n=$N '{s+=$1} END{printf "%.2f", s-(n-1)*xf}')
INARGS=(); for ((k=0;k<N;k++)); do INARGS+=(-i "$W/seg/seg_$k.mp4"); done
FG=""; prev="0:v"; cum=0
for ((k=1;k<N;k++)); do
  cum=$(awk -v c="$cum" -v d="${DUR[$((k-1))]}" 'BEGIN{print c+d}')
  off=$(awk -v c="$cum" -v k="$k" -v xf=$XF 'BEGIN{printf "%.2f", c-k*xf}')
  if [ "$k" -lt $((N-1)) ]; then out="[x$k]"; else out="[vx]"; fi
  FG+="[$prev][$k:v]xfade=transition=fade:duration=$XF:offset=$off$out;"
  prev="x$k"
done
FOUT=$(awk -v t="$TOTAL" 'BEGIN{printf "%.2f", t-1.6}')
AOUT=$(awk -v t="$TOTAL" 'BEGIN{printf "%.2f", t-4}')
FG+="[vx]fade=t=out:st=$FOUT:d=1.6[vout];"
FG+="[${N}:a]loudnorm=I=-15:TP=-1.5:LRA=11,atrim=0:$TOTAL,afade=t=in:st=0:d=2,afade=t=out:st=$AOUT:d=4[aout]"

OUT="$DL/SOST_x_GeaSpirit_2min.mp4"
"$FF" -y -hide_banner -loglevel error "${INARGS[@]}" -i "$AUDIO" \
  -filter_complex "$FG" -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart -t "$TOTAL" "$OUT"

echo ">> DONE $OUT  total=${TOTAL}s"
/tmp/ffbin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
/tmp/ffbin/ffmpeg -hide_banner -i "$OUT" -af volumedetect -f null - 2>&1 | grep -iE "mean_volume|max_volume"
ls -la "$OUT" | awk '{print $5" bytes"}'
