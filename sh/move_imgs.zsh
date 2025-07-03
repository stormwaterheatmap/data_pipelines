#!/bin/zsh

# Exit immediately if a command exits with a non-zero status
set -e

# Check for correct number of arguments
if [[ $# -ne 3 ]]; then
  echo "Usage: $0 SOURCE_BUCKET FILENAME DESTINATION_BUCKET"
  echo "Example: $0 gs://my-source-bucket data.csv gs://my-destination-bucket"
  exit 1
fi

# Assign variables
SOURCE_BUCKET=$1
FILENAME=$2
DEST_BUCKET=$3

echo "Copying ${FILENAME} from ${SOURCE_BUCKET} to ${DEST_BUCKET}..."

# Perform the file copy using gsutil
gsutil cp "${SOURCE_BUCKET}/${FILENAME}" "${DEST_BUCKET}/"

echo "✅ Copy complete."

#gsutil cp gs://live_data_layers/rasters/HSPF_Land_Cover_Type.tif gs://swhm_data/public/layers/raster/HSPF_Land_Cover_Type/HSPF_Land_Cover_Type.tif