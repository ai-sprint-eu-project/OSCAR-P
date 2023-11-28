#!/bin/bash

INPUT_FILE=`basename "$INPUT_FILE_PATH"`

tar -xvzf "$INPUT_FILE_PATH"
# echo "" > timestamps.txt
python audio_splitter.py "${INPUT_FILE%.tar.gz}.wav" 35

tar -czvf "$TMP_OUTPUT_DIR/$INPUT_FILE" "timestamps.txt" "${INPUT_FILE%.tar.gz}.mp4"

cat timestamps.txt

# mv timestamps.txt "$TMP_OUTPUT_DIR/"
# mv "${INPUT_FILE%.tar.gz}.mp4" "$TMP_OUTPUT_DIR/"
