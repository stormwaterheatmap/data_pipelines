# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a geospatial data pipeline project focused on processing and converting raster data for the Stormwater Heat Map project. The repository contains tools for:

- Converting GeoTIFF files to Cloud Optimized GeoTIFF (COG) format
- Processing Earth Engine exports from Google Cloud Storage
- Managing data transfers between GCS buckets
- Creating STAC (SpatioTemporal Asset Catalog) metadata
- Uploading processed data to Earth Engine assets

## Architecture

The codebase is organized into several key components:

### Data Processing Pipeline
- **Input**: Raw GeoTIFF tiles exported from Earth Engine to GCS bucket `swhm-image-exports`
- **Processing**: Convert to COG format with proper projection (EPSG:3857)
- **Output**: Optimized rasters stored in `live_data_layers` bucket and uploaded to Earth Engine

### Core Processing Flow
1. **Export from Earth Engine** (`js/export_ee_images.js`): Batch exports raster layers to GCS
2. **COG Conversion** (`py/gdal_cog.py`, `generate_cog_images.ipynb`): Convert tiles to optimized format
3. **Data Transfer** (`copy_to_bucket.ipynb`): Move processed data between buckets
4. **Earth Engine Upload**: Convert processed COGs to Earth Engine assets

## Key Commands

### Python Environment
```bash
# Install dependencies using Pipenv
pipenv install

# Activate virtual environment
pipenv shell

# Run Python scripts
python py/gdal_cog.py gs://bucket/path/ output.tif
python py/get_bucket_contents.py

# Apply color tables to GeoTIFF files
python py/apply_colors.py input.tif --metadata data/layer_metadata.json --layer-name "Layer Name"
python py/apply_colors.py input.tif --rgb-colors "[[255,0,0],[0,255,0]]" --values "[1,2]"
```

### GDAL Commands
```bash
# Convert to COG using GDAL
gdal_translate in.tif out.tif -of COG -co OVERVIEWS=IGNORE_EXISTING -co COMPRESS=ZSTD -co LEVEL=22 -co PREDICTOR=2 -co INTERLEAVE=BAND -co NUM_THREADS=ALL_CPUS

# Shell script for batch processing
sh/gdal_cog.zsh
```

### Google Cloud Commands
```bash
# Set project
gcloud config set project swhm-dev

# Copy files to/from GCS
gcloud storage cp -R gs://source-bucket/path/ .
gcloud storage cp file.tif gs://destination-bucket/path/

# Earth Engine uploads
earthengine upload image --asset_id=projects/ee-swhm/assets/staging/LayerName gs://bucket/path/file.tif
```

## Data Types and Processing

### Layer Categories
- **Environmental layers**: Land cover, imperviousness, slope, soils
- **Hydrologic layers**: Precipitation, runoff, flow duration
- **Water quality layers**: Copper, nitrogen, phosphorus, suspended solids, zinc concentrations
- **Demographic layers**: Population density, traffic

### Processing Specifications
- **Target projection**: EPSG:3857 (Web Mercator)
- **Resampling**: `nearest` for categorical data (uint8), `average` for continuous data
- **Compression**: LZW for general use, ZSTD for optimal compression
- **Color Tables**: RGB color mappings stored in `data/layer_metadata.json` for discrete layers

## Important Files

### Notebooks
- `generate_cog_images.ipynb`: Main pipeline for COG conversion
- `copy_to_bucket.ipynb`: Data transfer utilities
- `Cloud GeoTiff Backed Earth Engine Assets.ipynb`: Earth Engine integration
- `vrt-cloud-rasterio-gdal.ipynb`: VRT processing examples

### Python Scripts
- `py/gdal_cog.py`: Production COG conversion script with parallel processing and color table support
- `py/apply_colors.py`: Standalone script for applying color tables to GeoTIFF files
- `py/get_bucket_contents.py`: GCS bucket inspection utility
- `py/convert_geojson.py`: Vector data conversion

### Configuration
- `data/layer_metadata.json`: Layer metadata with RGB color mappings for discrete layers
- `Pipfile`: Python dependencies (pandas, ipykernel, osgeo/gdal)

## Development Workflow

1. **Layer Export**: Use Earth Engine JavaScript (`js/export_ee_images.js`) to export layers to GCS
2. **COG Conversion**: Run conversion pipeline via `py/gdal_cog.py` or notebooks
3. **Color Application**: Apply color tables to discrete layers using `py/apply_colors.py`
4. **Validation**: Use `rio cogeo validate` to verify COG compliance
5. **Upload**: Transfer to production bucket and upload to Earth Engine assets

## Color Table Management

The pipeline supports applying color tables to discrete raster layers:
- RGB color mappings are stored in `data/layer_metadata.json`
- Each discrete layer includes `rgb_colors` array matching `values` and `labels`
- Use `py/apply_colors.py` to apply colors to existing GeoTIFF files
- Colors can be applied during COG conversion or as a separate step

## GCS Bucket Structure
- `swhm-image-exports/`: Raw Earth Engine exports (tiles)
- `live_data_layers/rasters/`: Processed COG files
- Earth Engine assets: `projects/ee-swhm/assets/staging/` and `projects/ee-swhm/assets/production_layers/`

## Performance Optimizations

The pipeline includes several GDAL optimizations:
- Memory caching (2GB cache, 1GB VSI cache)
- HTTP optimizations for GCS access
- Multi-threading for warping and translation
- Parallel file downloads using ThreadPoolExecutor