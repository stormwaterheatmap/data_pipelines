#!/usr/bin/env python3
"""
Stitch multiple GeoTIFF files from Google Cloud Storage into COG(s).

Uses rasterio only (no osgeo import), reprojects to EPSG:3857, outputs as Cloud Optimized GeoTIFF.
When more than --chunk-size files are found, creates multiple COGs instead of one large file.
"""

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

import rasterio
from rasterio.crs import CRS
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from google.cloud import storage


def chunk_list[T](items: list[T], chunk_size: int) -> Iterator[list[T]]:
    """Split a list into chunks of specified size."""
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def list_geotiffs(bucket_name: str, prefix: str = "") -> list[str]:
    """List all GeoTIFF files in a GCS bucket with given prefix."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    
    blobs = bucket.list_blobs(prefix=prefix)
    geotiff_extensions = ('.tif', '.tiff', '.geotiff')
    
    return [
        blob.name for blob in blobs 
        if blob.name.lower().endswith(geotiff_extensions)
    ]


def download_geotiffs(
    bucket_name: str, 
    blob_names: list[str], 
    local_dir: str
) -> list[Path]:
    """Download GeoTIFF files from GCS to local directory, skipping existing files."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    
    local_paths = []
    for blob_name in blob_names:
        blob = bucket.blob(blob_name)
        local_filename = Path(blob_name).name
        local_path = Path(local_dir) / local_filename
        
        if local_path.exists():
            print(f"Skipping (exists): {local_filename}")
        else:
            print(f"Downloading: {blob_name}")
            blob.download_to_filename(str(local_path))
        
        local_paths.append(local_path)
    
    return local_paths


def build_vrt(input_paths: list[Path], vrt_path: Path) -> None:
    """Build a VRT from multiple GeoTIFF files using gdalbuildvrt CLI."""
    print(f"Building VRT from {len(input_paths)} files...")
    
    cmd = [
        'gdalbuildvrt',
        str(vrt_path),
        *[str(p) for p in input_paths]
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdalbuildvrt failed: {result.stderr}")
    
    print(f"VRT created: {vrt_path}")


def reproject_to_cog(
    input_path: Path,
    output_path: Path,
    dst_crs: str = 'EPSG:3857',
    resampling: str = "nearest"
) -> None:
    """Reproject raster to target CRS and save as Cloud Optimized GeoTIFF.

    Skips reprojection if source CRS already matches target CRS.
    """

    resampling_method = getattr(Resampling, resampling, Resampling.nearest)
    dst_crs_obj = CRS.from_string(dst_crs)

    with rasterio.open(input_path) as src:
        print(f"Source CRS: {src.crs}")
        print(f"Source shape: {src.height} x {src.width}")
        print(f"Source bounds: {src.bounds}")
        print(f"Source dtype: {src.dtypes[0]}")

        # Check if reprojection is needed
        needs_reproject = src.crs != dst_crs_obj

        if needs_reproject:
            # Calculate transform for target CRS
            transform, width, height = calculate_default_transform(
                src.crs,
                dst_crs_obj,
                src.width,
                src.height,
                *src.bounds
            )

            print(f"Target CRS: {dst_crs}")
            print(f"Target shape: {height} x {width}")

            # Prepare output profile for COG
            profile = src.profile.copy()
            profile.update({
                'driver': 'GTiff',
                'crs': dst_crs_obj,
                'transform': transform,
                'width': width,
                'height': height,
                'compress': 'deflate',
                'tiled': True,
                'blockxsize': 512,
                'blockysize': 512,
            })

            # PREDICTOR=2 not supported for 64-bit with older libtiff
            # Use predictor only for int8/int16/int32/float32
            dtype = src.dtypes[0]
            if dtype in ('int8', 'int16', 'int32', 'uint8', 'uint16', 'uint32', 'float32'):
                profile['predictor'] = 2
            else:
                print(f"Skipping predictor for dtype: {dtype}")

            # Write reprojected raster
            temp_output = output_path.with_suffix('.temp.tif')

            print(f"Reprojecting to {dst_crs}...")
            with rasterio.open(temp_output, 'w', **profile) as dst:
                for i in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, i),
                        destination=rasterio.band(dst, i),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=dst_crs_obj,
                        resampling=resampling_method
                    )
        else:
            print(f"Source CRS matches target ({dst_crs}), skipping reprojection")
            temp_output = input_path

    # Convert to COG using gdal_translate CLI
    print("Converting to Cloud Optimized GeoTIFF...")
    cmd = [
        'gdal_translate',
        '--config', 'CHECK_DISK_FREE_SPACE', 'FALSE',
        '-of', 'COG',
        '-co', 'COMPRESS=DEFLATE',
        '-co', 'PREDICTOR=2',
        '-co', 'BLOCKSIZE=512',
        '-co', 'OVERVIEWS=AUTO',
        '-co', 'OVERVIEW_RESAMPLING=AVERAGE',
        str(temp_output),
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gdal_translate failed: {result.stderr}")

    # Clean up temp file only if we created one
    if needs_reproject:
        temp_output.unlink()

    print(f"COG created: {output_path}")


def upload_to_gcs(local_path: Path, bucket_name: str, dest_blob_name: str) -> str:
    """Upload a file to GCS and return the gs:// URI."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(dest_blob_name)
    
    print(f"Uploading to: gs://{bucket_name}/{dest_blob_name}")
    blob.upload_from_filename(str(local_path))
    
    return f"gs://{bucket_name}/{dest_blob_name}"


def main():
    parser = argparse.ArgumentParser(
        description="Stitch GeoTIFFs from GCS into a single COG (EPSG:3857)"
    )
    parser.add_argument("--source-bucket", "-s", required=True, help="Source GCS bucket name")
    parser.add_argument("--source-prefix", "-p", default="", help="Prefix/folder path in source bucket")
    parser.add_argument("--dest-bucket", "-d", required=True, help="Destination GCS bucket name")
    parser.add_argument("--dest-path", "-o", default="mosaic.tif", help="Destination blob path")
    parser.add_argument("--dst-crs", default="EPSG:3857", help="Target CRS (default: EPSG:3857)")
    parser.add_argument("--resampling", choices=["nearest", "bilinear", "cubic", "average"], default="nearest")
    parser.add_argument("--work-dir", "-w", default="./geotiff_work", help="Local working directory (default: ./geotiff_work)")
    parser.add_argument("--keep-files", "-k", action="store_true", help="Keep downloaded files and intermediates")
    parser.add_argument("--chunk-size", "-c", type=int, default=32, help="Max files per COG (default: 32). Set to 0 to disable chunking.")
    
    args = parser.parse_args()
    
    print(f"Scanning gs://{args.source_bucket}/{args.source_prefix}")
    geotiff_blobs = list_geotiffs(args.source_bucket, args.source_prefix)
    
    if not geotiff_blobs:
        print("No GeoTIFF files found!")
        return 1
    
    print(f"Found {len(geotiff_blobs)} GeoTIFF files")
    
    # Use local working directory
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = work_dir / "downloads"
    downloads_dir.mkdir(exist_ok=True)
    
    print(f"Working directory: {work_dir.resolve()}")
    
    # Download all files
    local_paths = download_geotiffs(args.source_bucket, geotiff_blobs, str(downloads_dir))

    # Determine chunking strategy
    chunk_size = args.chunk_size
    use_chunking = chunk_size > 0 and len(local_paths) > chunk_size

    if use_chunking:
        chunks = list(chunk_list(local_paths, chunk_size))
        num_chunks = len(chunks)
        print(f"\nSplitting {len(local_paths)} files into {num_chunks} COGs ({chunk_size} files each)")

        # Prepare output naming: mosaic.tif -> mosaic_001.tif, mosaic_002.tif, etc.
        dest_path = Path(args.dest_path)
        dest_stem = dest_path.stem
        dest_suffix = dest_path.suffix or '.tif'
        dest_parent = dest_path.parent

        gcs_uris = []
        for idx, chunk_paths in enumerate(chunks, start=1):
            chunk_name = f"{dest_stem}_{idx:03d}{dest_suffix}"
            print(f"\n{'='*60}")
            print(f"Processing chunk {idx}/{num_chunks}: {len(chunk_paths)} files -> {chunk_name}")
            print(f"{'='*60}")

            # Build VRT for this chunk
            vrt_path = work_dir / f"mosaic_{idx:03d}.vrt"
            build_vrt(chunk_paths, vrt_path)

            # Reproject and convert to COG
            cog_path = work_dir / f"mosaic_cog_{idx:03d}.tif"
            reproject_to_cog(
                vrt_path,
                cog_path,
                dst_crs=args.dst_crs,
                resampling=args.resampling
            )

            # Upload result
            dest_blob = str(dest_parent / chunk_name) if dest_parent != Path('.') else chunk_name
            gcs_uri = upload_to_gcs(cog_path, args.dest_bucket, dest_blob)
            gcs_uris.append(gcs_uri)

            # Clean up VRT for this chunk
            if not args.keep_files:
                vrt_path.unlink(missing_ok=True)

        print(f"\n{'='*60}")
        print(f"Success! Created {num_chunks} COGs:")
        for uri in gcs_uris:
            print(f"  {uri}")
    else:
        # Single COG output (original behavior)
        vrt_path = work_dir / "mosaic.vrt"
        build_vrt(local_paths, vrt_path)

        cog_path = work_dir / "mosaic_cog.tif"
        reproject_to_cog(
            vrt_path,
            cog_path,
            dst_crs=args.dst_crs,
            resampling=args.resampling
        )

        gcs_uri = upload_to_gcs(cog_path, args.dest_bucket, args.dest_path)
        print(f"\nSuccess! COG saved to: {gcs_uri}")
        print(f"Local COG: {cog_path.resolve()}")

        if not args.keep_files:
            vrt_path.unlink(missing_ok=True)
    
    # Clean up if not keeping files
    if not args.keep_files:
        print("Cleaning up temporary files...")
        shutil.rmtree(downloads_dir)
    else:
        print(f"Files kept in: {work_dir.resolve()}")
    
    return 0


if __name__ == "__main__":
    exit(main())