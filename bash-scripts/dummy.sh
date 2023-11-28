#!/bin/bash

SUBFOLDER_NAME=`basename "$(dirname "$STORAGE_OBJECT_KEY")"`
IMAGE_NAME=`basename "$INPUT_FILE_PATH"`

python main.py

TMP=$(cat /proc/sys/kernel/random/uuid | sed 's/[-]//g' | head -c 5)

cp "influxdb.csv" "$TMP_OUTPUT_DIR/dummy_${SUBFOLDER_NAME}_${IMAGE_NAME}_influxdb.csv"
