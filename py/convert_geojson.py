import ijson
import simplejson as json
import sys

def convert_geojson(filename, outfile):
    with open(filename, 'r') as ifp, open(outfile, 'w') as ofp:
        objects = ijson.items(ifp, 'features.item')
        schema = None
        for obj in objects:
            props = obj['properties']  # a dictionary
            props['geometry'] = json.dumps(obj['geometry'],use_decimal=True)
            json.dump(props, fp=ofp)
            ofp.write('\n')  # newline
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

# Entry point for the script
if __name__ == "__main__":
    # Check that the script is called with the right number of arguments
    if len(sys.argv) != 3:
        print("Usage: python script.py <inputfile> <outputfile>")
        sys.exit(1)
    inputfile = sys.argv[1]
    outputfile = sys.argv[2]
    convert_geojson(inputfile, outputfile)
