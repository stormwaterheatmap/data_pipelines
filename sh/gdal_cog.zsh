gdal_translate in.tif out.tif \
  -of COG \
  -co OVERVIEWS=IGNORE_EXISTING \
  -co COMPRESS=ZSTD \
  -co LEVEL=22 \
  -co PREDICTOR=2 \
  -co INTERLEAVE=BAND \
  -co NUM_THREADS=ALL_CPUS \