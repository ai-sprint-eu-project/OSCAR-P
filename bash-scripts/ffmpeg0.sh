#!/bin/bash

INPUT_FILE=`basename "$INPUT_FILE_PATH"`

# ffmpeg -i "$INPUT_FILE_PATH" -vcodec libx265 -crf 30 "$TMP_OUTPUT_DIR/$INPUT_FILE"
ffmpeg -i "$INPUT_FILE_PATH" -vcodec libx264 -crf 28 "$TMP_OUTPUT_DIR/$INPUT_FILE"
# cp "$INPUT_FILE_PATH" "$TMP_OUTPUT_DIR/$INPUT_FILE"
ffmpeg -i "$TMP_OUTPUT_DIR/$INPUT_FILE" -map 0:a "$TMP_OUTPUT_DIR/${INPUT_FILE%.mp4}.wav"

cd $TMP_OUTPUT_DIR
tar -czvf "${INPUT_FILE%.mp4}.tar.gz" "$INPUT_FILE" "${INPUT_FILE%.mp4}.wav"
rm "$INPUT_FILE"
rm "${INPUT_FILE%.mp4}.wav"
