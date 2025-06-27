import json
from urllib.request import urlopen
import urllib
from google.cloud import storage
import os
dirname = os.path.dirname(__file__)

print(dirname)
# Path: _no_git_dev_cn/py/gcp
os.chdir(dirname)
print(os.getcwd())


client = storage.Client()

filename = os.path.join(dirname,'data/psaufin2.geojson')
print(filename)
with open(filename, 'r') as ifp:
  with open('to_load.json', 'w') as ofp:
    features = json.load(ifp)['features']
    # new-line-separated JSON
    schema = None
    for obj in features:
        props = obj['properties']  # a dictionary
        props['geometry'] = json.dumps(obj['geometry'])  # make the geometry a string
        json.dump(props, fp=ofp)
        print('', file=ofp) # newline
        if schema is None:
            schema = []
            for key, value in props.items():
                if key == 'geometry':
                    schema.append('geometry:GEOGRAPHY')
                elif isinstance(value, str):
                    schema.append(key)
                else:
                    schema.append('{}:{}'.format(key,
                       'int64' if isinstance(value, int) else 'float64'))
            schema = ','.join(schema)
    print('Schema: ', schema)


bucket = client.get_bucket('vector_data')
blob = bucket.blob('psau.json')
blob.upload_from_filename("to_load.json") 
import subprocess

bashCommand = """
bq load \ --source_format=NEWLINE_DELIMITED_JSON 
--json_extension=GEOJSON \                            
--autodetect \
spatial_data.landuse_up \
to_load.json
"""
process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
output, error = process.communicate()