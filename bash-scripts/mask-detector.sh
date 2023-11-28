#!/bin/bash

echo "#bash_script_start: $(date +"%d-%m-%Y %H:%M:%S.%6N")"
SUBFOLDER_NAME=`basename "$(dirname "$STORAGE_OBJECT_KEY")"`

mkdir "$TMP_OUTPUT_DIR/$SUBFOLDER_NAME"

IMAGE_NAME=`basename "$INPUT_FILE_PATH"`
OUTPUT_IMAGE="$TMP_OUTPUT_DIR/$SUBFOLDER_NAME/$IMAGE_NAME"

echo "SCRIPT: Analyzing file '$INPUT_FILE_PATH', saving the output image in '$OUTPUT_IMAGE'"

python mask-detector-image.py --image "$INPUT_FILE_PATH" --output "$OUTPUT_IMAGE"
echo "#bash_script_end: $(date +"%d-%m-%Y %H:%M:%S.%6N")"
