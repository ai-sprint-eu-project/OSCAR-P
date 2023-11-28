#!/bin/bash

SUBFOLDER_NAME=`basename "$(dirname "$STORAGE_OBJECT_KEY")"`

mkdir "$TMP_OUTPUT_DIR/$SUBFOLDER_NAME"

IMAGE_NAME=`basename "$INPUT_FILE_PATH"`
OUTPUT_IMAGE="$TMP_OUTPUT_DIR/$SUBFOLDER_NAME/$IMAGE_NAME"

echo "SCRIPT: Analyzing file '$INPUT_FILE_PATH', saving the output image in '$OUTPUT_IMAGE'"

python mask-detector-image.py --image "$INPUT_FILE_PATH" --output "$OUTPUT_IMAGE"


TMP=$(cat /proc/sys/kernel/random/uuid | sed 's/[-]//g' | head -c 5)

# cp "influxdb.csv" "$TMP_OUTPUT_DIR/mask_${TMP}_influxdb.csv"
cp "influxdb.csv" "$TMP_OUTPUT_DIR/mask_${SUBFOLDER_NAME}_${IMAGE_NAME}_influxdb.csv"
