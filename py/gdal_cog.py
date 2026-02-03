#!/usr/bin/env python3
"""
Python script to convert GeoTIFF files to Cloud Optimized GeoTIFF (COG) format.
Downloads from GCS, creates VRT, checks/reprojects to EPSG:3857, then converts to COG.
"""

import subprocess
import sys
import os
import tempfile
from google.cloud import storage
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from osgeo import gdal


def setup_gdal_optimizations():
    """Set up GDAL environment variables for optimal performance."""
    # Memory and caching optimizations
    os.environ['GDAL_CACHEMAX'] = '2048'  # 2GB cache
    os.environ['VSI_CACHE'] = 'TRUE'
    os.environ['VSI_CACHE_SIZE'] = '1000000000'  # 1GB
    
    # HTTP optimizations for GCS
    os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
    os.environ['GDAL_HTTP_MERGE_CONSECUTIVE_RANGES'] = 'YES'
    os.environ['GDAL_HTTP_MULTIPLEX'] = 'YES'
    os.environ['GDAL_HTTP_VERSION'] = '2'
    os.environ['CPL_VSIL_CURL_ALLOWED_EXTENSIONS'] = '.tif,.vrt'
    
    # No sign request for public buckets
    os.environ['GS_NO_SIGN_REQUEST'] = 'YES'
    os.environ['GDAL_NUM_THREADS'] = '5'


def download_from_gcs(storage_client: storage.Client, bucket_name: str, source_blob_name: str, destination_file_name: str) -> None:
    """Download a blob from GCS bucket."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)


def create_vrt(input_files: list, output_vrt: str) -> None:
    """Create a VRT file from input files."""
    cmd = ['gdalbuildvrt', output_vrt] + input_files
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdalbuildvrt failed: {result.stderr}")


def create_vrt_from_gcs(bucket_name: str, gcs_files: list, output_vrt: str) -> None:
    """Create VRT directly from GCS using /vsigs/ paths (no download needed)."""
    vsigs_files = [f'/vsigs/{bucket_name}/{f}' for f in gcs_files]
    cmd = ['gdalbuildvrt', output_vrt] + vsigs_files
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdalbuildvrt failed: {result.stderr}")


def get_raster_info(input_file: str) -> dict:
    """Get raster information using rio info."""
    cmd = ['rio', 'info', input_file]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"rio info failed: {result.stderr}")
    return json.loads(result.stdout)


def reproject_to_3857(input_file: str, output_file: str, dtype: str = 'float64') -> None:
    """Reproject raster to EPSG:3857 using gdalwarp with optimizations."""
    # Use nearest neighbor for categorical data, cubic for continuous
    resampling = 'near' if dtype == 'uint8' else 'cubic'
    
    cmd = [
        'gdalwarp',
        '-t_srs', 'EPSG:3857',
        '-overwrite',
        '-r', resampling,
        input_file,
        output_file,
        '-co', 'NUM_THREADS=ALL_CPUS',
        '-co', 'TILED=YES',
        '-co', 'COMPRESS=LZ4',  # Faster than LZW
        '-co', 'BIGTIFF=YES',
        '-multi',  # Use multiple threads for warping
        '--config', 'CHECK_DISK_FREE_SPACE', 'FALSE'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdalwarp failed: {result.stderr}")


def apply_color_table(input_file: str, rgb_colors: list, values: list, mask_zeros: bool = False) -> None:
    """Apply color table to raster using GDAL."""
    
    # Open the dataset with COG layout break option
    dataset = gdal.OpenEx(input_file, gdal.GA_Update, open_options=['IGNORE_COG_LAYOUT_BREAK=YES'])
    if dataset is None:
        raise RuntimeError(f"Cannot open {input_file}")
    
    band = dataset.GetRasterBand(1)
    
    # Create color table
    color_table = gdal.ColorTable()
    
    # Add transparent entry for 0 values if masking is enabled
    if mask_zeros:
        color_table.SetColorEntry(0, (0, 0, 0, 0))  # Transparent black for 0 values
    
    # Add colors for each value
    for value, rgb in zip(values, rgb_colors):
        color_table.SetColorEntry(int(value), (rgb[0], rgb[1], rgb[2], 255))
    
    # Apply color table
    band.SetColorTable(color_table)
    band.SetColorInterpretation(gdal.GCI_PaletteIndex)
    
    # Close dataset
    dataset = None
    
    mask_info = " (with 0 values masked as transparent)" if mask_zeros else ""
    print(f"Applied color table with {len(rgb_colors)} colors{mask_info}")


def translate_to_cog(input_file: str, output_file: str, apply_colors: bool = False, rgb_colors: list = None, values: list = None, mask_zeros: bool = False) -> None:
    """Translate raster to COG format using gdal_translate."""
    
    # Apply color table if requested
    if apply_colors and rgb_colors and values:
        print(f"Applying color table with {len(rgb_colors)} colors...")
        apply_color_table(input_file, rgb_colors, values, mask_zeros)
    
    cmd = [
        'gdal_translate',
        input_file,
        output_file,
        '-of', 'COG',
        '-co', 'OVERVIEWS=IGNORE_EXISTING',
        '-co', 'COMPRESS=ZSTD',
        '-co', 'LEVEL=22',
        '-co', 'PREDICTOR=2',
        '-co', 'INTERLEAVE=BAND',
        '-co', 'NUM_THREADS=ALL_CPUS',
        '--config', 'CHECK_DISK_FREE_SPACE', 'FALSE'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdal_translate failed: {result.stderr}")



def download_files_parallel(storage_client: storage.Client, bucket_name: str, gcs_files: list, temp_dir: str) -> list:
    """Download files in parallel for better performance."""
    def download_single(gcs_file):
        local_file = os.path.join(temp_dir, os.path.basename(gcs_file))
        download_from_gcs(storage_client, bucket_name, gcs_file, local_file)
        return local_file
    
    with ThreadPoolExecutor(max_workers=min(8, len(gcs_files))) as executor:
        local_files = list(executor.map(download_single, gcs_files))
    
    return local_files


def list_gcs_files(storage_client: storage.Client, bucket_name: str, prefix: str) -> list:
    """List all files in GCS bucket with given prefix."""
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    return [blob.name for blob in blobs if blob.name.endswith('.tif')]


def load_layer_metadata(metadata_file: str, layer_name: str) -> dict:
    """Load RGB colors and values for a specific layer from metadata JSON."""
    try:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        # Look in both rasters and cocs sections
        for section in ['rasters', 'cocs']:
            if section in metadata and layer_name in metadata[section]:
                layer_data = metadata[section][layer_name]
                if layer_data.get('discrete') and 'rgb_colors' in layer_data:
                    return {
                        'rgb_colors': layer_data['rgb_colors'],
                        'values': layer_data['values']
                    }
        
        return None
    except Exception as e:
        print(f"Warning: Could not load metadata for layer {layer_name}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Convert GeoTIFF to COG format for GCS files')
    parser.add_argument('input_path', help='Input GCS path pattern (gs://bucket/path/)')
    parser.add_argument('output_path', help='Output local path for the converted COG file')
    parser.add_argument('--no-stream', action='store_true', help='Download files instead of streaming from GCS')
    parser.add_argument('--layer-metadata', help='Path to layer metadata JSON file')
    parser.add_argument('--layer-name', help='Name of layer in metadata to apply colors from')
    parser.add_argument('--apply-colors', action='store_true', help='Apply color table to discrete layers')
    parser.add_argument('--mask-zeros', action='store_true', help='Mask values of 0 as transparent')
    
    args = parser.parse_args()
    
    # Set up GDAL optimizations
    setup_gdal_optimizations()
    
    # Parse GCS input path
    if not args.input_path.startswith('gs://'):
        raise ValueError("Input path must be a GCS path starting with gs://")
    
    # Parse bucket and prefix
    path_parts = args.input_path[5:].split('/', 1)
    bucket_name = path_parts[0]
    prefix = path_parts[1] if len(path_parts) > 1 else ''
    
    # Create storage client once for reuse
    storage_client = storage.Client()
    
    # Load color metadata early if requested
    layer_data = None
    if args.apply_colors and args.layer_metadata and args.layer_name:
        layer_data = load_layer_metadata(args.layer_metadata, args.layer_name)
        if not layer_data:
            print(f"Warning: No color data found for layer '{args.layer_name}'")
    
    # Create temporary directory for processing (use /tmp for faster I/O)
    with tempfile.TemporaryDirectory(dir='/tmp') as temp_dir:
        print(f"Listing files in {args.input_path}...")
        gcs_files = list_gcs_files(storage_client, bucket_name, prefix)
        
        if not gcs_files:
            raise ValueError(f"No .tif files found in {args.input_path}")
        
        print(f"Found {len(gcs_files)} files.")
        
        # Create VRT - either from GCS directly or from downloaded files
        temp_vrt = os.path.join(temp_dir, 'temp.vrt')
        temp_reprojected = os.path.join(temp_dir, 'reprojected.tif')
        
        if args.no_stream:
            print("Downloading files in parallel...")
            local_files = download_files_parallel(storage_client, bucket_name, gcs_files, temp_dir)
            print("Creating VRT from downloaded files...")
            create_vrt(local_files, temp_vrt)
        else:
            print("Creating VRT directly from GCS (streaming)...")
            create_vrt_from_gcs(bucket_name, gcs_files, temp_vrt)
        
        print("Checking projection...")
        raster_info = get_raster_info(temp_vrt)
        current_crs = raster_info.get('crs')
        dtype = raster_info.get('dtype', 'float64')
        
        if current_crs != 'EPSG:3857':
            print(f"Reprojecting from {current_crs} to EPSG:3857...")
            reproject_to_3857(temp_vrt, temp_reprojected, dtype)
            source_file = temp_reprojected
        else:
            print("Already in EPSG:3857, skipping reprojection...")
            source_file = temp_vrt
        
        print("Converting to COG...")
        
        # Apply colors if metadata was loaded
        if layer_data:
            rgb_colors = layer_data['rgb_colors']
            values = layer_data['values']
            translate_to_cog(source_file, args.output_path, True, rgb_colors, values, args.mask_zeros)
        else:
            translate_to_cog(source_file, args.output_path, False, None, None, args.mask_zeros)
        
        print(f"Conversion complete! Output saved to {args.output_path}")


if __name__ == '__main__':
    main()
    