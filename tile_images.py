import subprocess
import os 

# List of input raster files
input_files =['/vsigs/swhm-ee-exports/image-exports/traffic/traffic0000000000-0000000000.tif', '/vsigs/swhm-ee-exports/image-exports/traffic/traffic0000000000-0000032768.tif', '/vsigs/swhm-ee-exports/image-exports/traffic/traffic0000000000-0000065536.tif', '/vsigs/swhm-ee-exports/image-exports/traffic/traffic0000032768-0000000000.tif', '/vsigs/swhm-ee-exports/image-exports/traffic/traffic0000032768-0000032768.tif', '/vsigs/swhm-ee-exports/image-exports/traffic/traffic0000032768-0000065536.tif']
input_file_string = ' '.join(input_files)

# Name of output file
output_file = 'output.tif'

# Build the gdal_merge.py command
command = ['gdal_merge.py', '-o', output_file, '-of', 'GTiff', '-co', 'TILED=YES', '-co', 'COPY_SRC_OVERVIEWS=YES']

print(command.append(input_file_string))


# Run the gdal_merge.py command
#os.system(command)

