// Function for scaling bands and preserving image metadata
var rescale = function(image){
  //var time = ee.Image.constant(image.date().millis()).rename('time') 
  var img = ee.Image(image).divide(10000);
  return img.copyProperties(image, image.propertyNames());
};

/// Load Cloud Mask function for Sentinel-2 Images
var CloudMaskFunction = require('users/lizcanosandoval/sentinel2/:/CloudScore_S2');
var CloudMask = function(image){
  var img = ee.Image(image);
  var mask = CloudMaskFunction.CloudScore(img);
  return mask;
};

/// Function to mask land (with feature collection) in an image collection
var maskInside = function(image, geometry) {
  var mask = ee.Image.constant(1).clip(land).mask().not();
  return image.updateMask(mask);
};

/// Function to mask land (with image collection) in an image collection
var maskInside2 = function(image) {
  var mask = image.updateMask(landmask.max());
  return mask;
};

/// Function to clip an image collection by REGION
function clipRegion(image){
  var maskRegion = ee.Image.constant(1).clip(region).mask();
  return image.updateMask(maskRegion);
}

/// Function to calculate NDTI
function NDTI(image){
  var ndti = image.normalizedDifference(['B4','B3']).rename('NDTI');
  return image.addBands(ndti);
}

/// Statistics function. It retrieves the mean and std values of the bands of interest 
/// from each image in the collection.
var getStats = function(img) {
  // Select and rename bands.
  var image = ee.Image(img);
  // Create and combine reducers of mean and std.
  var reducers = ee.Reducer.mean().combine({
    reducer2: ee.Reducer.stdDev(),
    sharedInputs: true
    });
  // Apply reducers to the image.
  var stats = image.reduceRegion({
    reducer: reducers,
    //geometry: image.select('704').bounds(),
    //bestEffort: true,
    geometry: region,
    scale: 10,
    maxPixels: 1e13
    });
  // Create feature variable to allocate data.
  var feature = ee.Feature(null);
  // Set properties of interest.
  var properties = ['system:index','MGRS_TILE','GENERATION_TIME','MEAN_SOLAR_ZENITH_ANGLE',
                   'MEAN_SOLAR_AZIMUTH_ANGLE','SPACECRAFT_NAME','CLOUDY_PIXEL_PERCENTAGE','704_mean','704_stdDev',
                   'NDTI_mean','NDTI_stdDev'];
  // Apply the stats on every image and collect the output.
  var imageStats = image.setMulti(stats);
  // return feature with the selected properties.
  return ee.Feature(feature).copyProperties(imageStats, properties);
};

/// Function for counting pixels
var countPixels = function(img) {
  var count = ee.Image(img).select(['704']).rename('Valid_Pixels').reduceRegion({
    reducer: ee.Reducer.count(), 
    scale: 10,
    geometry: region,
    //bestEffort: true,
    maxPixels: 1e13
    }); 
  //Create empty feature collection to populate it with properties.  
   var feature = ee.Feature(null);
   var imageStats = img.setMulti(count);
   var properties = ['system:index','Valid_Pixels'];
  //Collection with values
   var validPixels = ee.Feature(feature).copyProperties(imageStats,properties);
  //Extract the number of valid pixels
   var getValid = ee.Number(validPixels.get('Valid_Pixels'));
  //Create a feature with zero's mean and std values
   var zerosDef = {'704_mean': ee.Number(0), '704_stdDev': ee.Number(0),
                  'NDTI_mean': ee.Number(0), 'NDTI_stdDev': ee.Number(0)};
   var zeroValues = ee.Feature(null, zerosDef);
  //Function to identify images with zero pixels and add the missing mean and std values (zero).
   var newCount = ee.Algorithms.If({
     condition: getValid.neq(0), 
     trueCase: validPixels, 
     falseCase: validPixels.copyProperties(zeroValues,['704_mean','704_stdDev',
      'NDTI_mean','NDTI_stdDev'])
   });
  return newCount;
};
