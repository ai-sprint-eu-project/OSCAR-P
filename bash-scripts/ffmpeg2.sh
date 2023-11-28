#!/bin/bash

INPUT_FILE=`basename "$INPUT_FILE_PATH"`

# extract audio track
ffmpeg -i "$INPUT_FILE_PATH" -map 0:a "${INPUT_FILE_PATH%.mp4}.wav"

# down-sample audio track
ffmpeg -i "${INPUT_FILE_PATH%.mp4}.wav" -vn -ar 16000 -ac 1 "$TMP_OUTPUT_DIR/"${INPUT_FILE%.mp4}.wav""

# compress video file
ffmpeg -i "$INPUT_FILE_PATH" -vcodec libx265 -crf 30 "$TMP_OUTPUT_DIR/$INPUT_FILE"

# alternative that copies the clip without compression
#cp "$INPUT_FILE_PATH" "$TMP_OUTPUT_DIR/$INPUT_FILE"

cd $TMP_OUTPUT_DIR
tar -czvf "${INPUT_FILE%.mp4}.tar.gz" "$INPUT_FILE" "${INPUT_FILE%.mp4}.wav"
rm "$INPUT_FILE"
rm "${INPUT_FILE%.mp4}.wav"
