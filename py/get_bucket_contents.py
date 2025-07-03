#!/usr/bin/env python3
"""
Script to retrieve GCP bucket contents as JSON
"""

import json
from google.cloud import storage
from typing import List, Dict, Any


def get_bucket_contents(bucket_name: str, prefix: str = "", 
                       file_extension: str = None, 
                       project_id: str = None) -> List[Dict[str, Any]]:
    """
    Retrieve contents of a GCP bucket and return as JSON-serializable list.
    
    Args:
        bucket_name: Name of the GCP bucket
        prefix: Optional prefix to filter objects
        file_extension: Optional file extension filter (e.g., '.tif', '.json')
        project_id: Optional GCP project ID
    
    Returns:
        List of dictionaries containing blob information
    """
    if project_id:
        storage_client = storage.Client(project=project_id)
    else:
        storage_client = storage.Client()
    
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    
    bucket_contents = []
    
    for blob in blobs:
        # Apply file extension filter if specified
        if file_extension and not blob.name.endswith(file_extension):
            continue
            
        blob_info = {
            "name": blob.name,
            "size": blob.size,
            "time_created": blob.time_created.isoformat() if blob.time_created else None,
            "updated": blob.updated.isoformat() if blob.updated else None,
            "content_type": blob.content_type,
            "etag": blob.etag,
            "generation": blob.generation,
           # "metageneration": blob.metageneration,
            "storage_class": blob.storage_class,
            "public_url": f"gs://{bucket_name}/{blob.name}"
        }
        bucket_contents.append(blob_info)
    
    return bucket_contents


def main():
    """Main function to demonstrate usage"""
    # Configuration
    BUCKET_NAME = "live_data_layers"
    PREFIX = "rasters"
    FILE_EXTENSION = ".tif"
    PROJECT_ID = "swhm-prod"
    
    try:
        # Get bucket contents
        contents = get_bucket_contents(
            bucket_name=BUCKET_NAME,
            prefix=PREFIX,
            file_extension=FILE_EXTENSION,
            project_id=PROJECT_ID
        )
        
        # Convert to JSON and print
        json_output = json.dumps(contents, indent=2)
        print(json_output)
        
        # Optionally save to file
        with open('bucket_contents.json', 'w') as f:
            json.dump(contents, f, indent=2)
        
        print(f"\nFound {len(contents)} objects in bucket '{BUCKET_NAME}'")
        print(f"Results saved to 'bucket_contents.json'")
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()