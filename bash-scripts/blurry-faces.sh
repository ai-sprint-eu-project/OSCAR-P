#!/bin/bash

echo "#bash_script_start: $(date +"%d-%m-%Y %H:%M:%S.%6N")"

VIDEO_NAME=`basename "$INPUT_FILE_PATH"`
SUBFOLDER_NAME=`echo "$VIDEO_NAME" | cut -f 1 -d '.'`
OUTPUT_SUBFOLDER="$TMP_OUTPUT_DIR/$SUBFOLDER_NAME"

mkdir "$OUTPUT_SUBFOLDER"

echo "SCRIPT: Analyzing file '$INPUT_FILE_PATH', saving the output images in '$OUTPUT_SUBFOLDER'"

echo "#split_start: $(date +"%d-%m-%Y %H:%M:%S.%6N")"
ffmpeg -i "$INPUT_FILE_PATH" -vf fps=12/60 "$OUTPUT_SUBFOLDER/img%d.jpg"
ffmpeg_end=`date +%s%N`
delta=$((ffmpeg_end-ffmpeg_start))
echo "#split_end: $(date +"%d-%m-%Y %H:%M:%S.%6N")"

for IMAGE in "$OUTPUT_SUBFOLDER"/*
do 
    python auto_blur_image.py -i "$IMAGE" -o "$IMAGE"
done

echo "#bash_script_end: $(date +"%d-%m-%Y %H:%M:%S.%6N")"
