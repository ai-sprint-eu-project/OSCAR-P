#!/bin/bash

INPUT_FILE=`basename "$INPUT_FILE_PATH"`

tar -xvzf "$INPUT_FILE_PATH"
deepspeech --model deepspeech-0.9.3-models.pbmm --scorer deepspeech-0.9.3-models.scorer --audio "${INPUT_FILE%.tar.gz}.wav" > "$TMP_OUTPUT_DIR/transcript.txt"
cat "$TMP_OUTPUT_DIR/transcript.txt"

cp "${INPUT_FILE%.tar.gz}.mp4" "$TMP_OUTPUT_DIR/${INPUT_FILE%.tar.gz}.mp4"

cd $TMP_OUTPUT_DIR
tar -czvf "$INPUT_FILE" "${INPUT_FILE%.tar.gz}.mp4" "transcript.txt"
rm "${INPUT_FILE%.tar.gz}.mp4"
rm transcript.txt