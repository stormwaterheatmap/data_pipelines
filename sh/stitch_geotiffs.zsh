python3 stitch_geotiffs.py \
--source-bucket swhm-staging-us \
--source-prefix tiles/predictors \
--dest-bucket swhm-staging-us \
--dest-path mosaic/predictors.tif \
--chunk-size 32 \
--work-dir ./geotiff_work \
--keep-files