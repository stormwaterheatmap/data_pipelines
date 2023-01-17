var data  = require('users/stormwaterheatmap/apps:data/data_dictionary.js')
var rasters = data.rasters

var PugetSound = data.vectors.PugetSound
var watermask = ee.Image("projects/ee-stormwaterheatmap/assets/water_mask");
var layers = Object.keys(rasters)

for (var i = 0; i < layers.length; i++) {
  var lay = rasters[layers[i]]
  var img = lay.layer.eeObject//.mask(watermask)
  var scale = lay.scale

  Map.addLayer(lay.layer)
  var layer_description = lay.layer.name
    .replace(/\s/g, '_')
    .replace(/\)/g, '')
    .replace(/\(/g, '')
  print(layer_description)

  Export.image.toCloudStorage({
        image: img,
        description: layer_description, 
        bucket:'swhm-image-exports',
        maxPixels: 1e13,
        scale: scale,
        region: PugetSound,
        fileNamePrefix: layer_description+"/" +
            layer_description, 
        fileFormat: 'GeoTIFF',
        formatOptions: {
            cloudOptimized: true
        }
    })
}