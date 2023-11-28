#!/bin/bash

VIDEO_NAME=`basename "$INPUT_FILE_PATH"`
SUBFOLDER_NAME=`echo "$VIDEO_NAME" | cut -f 1 -d '.'`
OUTPUT_SUBFOLDER="$TMP_OUTPUT_DIR/$SUBFOLDER_NAME"

echo $EVENT

mkdir "$OUTPUT_SUBFOLDER"

echo "SCRIPT: Analyzing file '$INPUT_FILE_PATH', saving the output images in '$OUTPUT_SUBFOLDER'"

ffmpeg -i "$INPUT_FILE_PATH" -vf fps=12/60 "$OUTPUT_SUBFOLDER/img%d.jpg"
ffmpeg_end=`date +%s%N`
delta=$((ffmpeg_end-ffmpeg_start))

for IMAGE in "$OUTPUT_SUBFOLDER"/*
do 
    python auto_blur_image.py -i "$IMAGE" -o "$IMAGE"
done

TMP=$(cat /proc/sys/kernel/random/uuid | sed 's/[-]//g' | head -c 5)

# cp "influxdb.csv" "$TMP_OUTPUT_DIR/blur_${TMP}_influxdb.csv"
cp "influxdb.csv" "$TMP_OUTPUT_DIR/blur_${SUBFOLDER_NAME}_influxdb.csv"
