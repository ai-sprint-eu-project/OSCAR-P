#!/bin/bash

#INPUT_FILE_PATH="./test_charlie_0.tar.gz"
INPUT_FILE=`basename "$INPUT_FILE_PATH"`

echo $INPUT_FILE_PATH

tar -xvzf "$INPUT_FILE_PATH"

filename='timestamps.txt'
n=0
while read line; do
  n=$((n+1))
  echo "--> $n"
  echo "$line"
  start=${line% *}
  end=${line#* }
  echo "$start"
  echo "$end"
  ffmpeg -ss $start -accurate_seek -i "${INPUT_FILE%.tar.gz}.mp4" -to $end -c copy "$TMP_OUTPUT_DIR/${INPUT_FILE%.tar.gz}$n.mp4"
  # ffmpeg -ss $start -accurate_seek -i "${INPUT_FILE%.tar.gz}.mp4" -to $end "$TMP_OUTPUT_DIR/${INPUT_FILE%.tar.gz}$n.mp4"
done < $filename
