#!/bin/bash

SEARCH_TERM="and"

INPUT_FILE=`basename "$INPUT_FILE_PATH"`

tar -xvzf "$INPUT_FILE_PATH"

cat "transcript.txt"

if grep -q $SEARCH_TERM "transcript.txt"; then
    mv "${INPUT_FILE%.tar.gz}.mp4" "$TMP_OUTPUT_DIR/${INPUT_FILE%.tar.gz}.mp4"
fi
