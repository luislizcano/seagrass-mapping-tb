import ee
ee.Initialize()

## Function for scaling bands and preserving image metadata
def rescale(image):
  img = ee.Image(image).divide(10000)
  return img.copyProperties(image, image.propertyNames())

## Load Cloud Mask function for Sentinel-2 Images
cloudMaskFunction = require('users/lizcanosandoval/sentinel2/:/CloudScore_S2')
def cloudMask(image):
  img = ee.Image(image)
  mask = cloudMaskFunction.CloudScore(img)
  return mask

## Function to mask land (with feature collection) in an image collection
def maskLand(geometry):
  def apply(image):
    mask = ee.Image.constant(1).clip(geometry).mask().Not()
    return image.updateMask(mask)

## Function to clip an image collection by REGION
def clipRegion(geometry):
  def apply(image):
    maskRegion = ee.Image.constant(1).clip(geometry).mask()
    return image.updateMask(maskRegion)

## Function to clean joins.
def cleanJoin(feature):
  return ee.Image.cat(feature.get('stats')).copyProperties(feature.get('counts'))

## Function to calculate NDTI
def NDTI(image):
  ndti = image.normalizedDifference(['B4','B3']).rename('NDTI')
  return image.addBands(ndti)

## Statistics function. It retrieves the mean and std values of the bands of interest 
## from each image in the collection.
def getStats(img,region):
  ## Select and rename bands.
  image = ee.Image(img)
  ## Create and combine reducers of mean and std.
  reducers = ee.Reducer.mean().combine(**{
    'reducer2': ee.Reducer.stdDev(),
    'sharedInputs': True})
  ## Apply reducers to the image.
  stats = image.reduceRegion(**{
    'reducer': reducers,
    'geometry': region,
    'scale': 10,
    'maxPixels': 1e13})
  ## Create feature variable to allocate data.
  feature = ee.Feature(None)
  ## Set properties of interest.
  properties = ['system:index','MGRS_TILE','GENERATION_TIME','MEAN_SOLAR_ZENITH_ANGLE',\
                'MEAN_SOLAR_AZIMUTH_ANGLE','SPACECRAFT_NAME','CLOUDY_PIXEL_PERCENTAGE',\
                '704_mean','704_stdDev','NDTI_mean','NDTI_stdDev']
  ## Apply the stats on every image and collect the output.
  imageStats = image.setMulti(stats)
  ## return feature with the selected properties.
  return ee.Feature(feature).copyProperties(imageStats, properties)

## Function for counting pixels
def countPixels(img,region):
  count = ee.Image(img).select(['704']).rename('Valid_Pixels').reduceRegion(**{
    'reducer': ee.Reducer.count(), 
    'scale': 10,
    'geometry': region,
    'maxPixels': 1e13})
  ##Create empty feature collection to populate it with properties.  
  feature = ee.Feature(None)
  imageStats = img.setMulti(count)
  properties = ['system:index','Valid_Pixels']
  ##Collection with values
  validPixels = ee.Feature(feature).copyProperties(imageStats,properties)
  ##Extract the number of valid pixels
  getValid = ee.Number(validPixels.get('Valid_Pixels'))
  ##Create a feature with zero's mean and std values
  zerosDef = {'704_mean': ee.Number(0), '704_stdDev': ee.Number(0),\
                'NDTI_mean': ee.Number(0), 'NDTI_stdDev': ee.Number(0)}
  zeroValues = ee.Feature(None, zerosDef)
  ##Function to identify images with zero pixels and add the missing mean and std values (zero).
  newCount = ee.Algorithms.If(**{
     'condition': getValid.neq(0), 
     'trueCase': validPixels, 
     'falseCase': validPixels.copyProperties(zeroValues,['704_mean','704_stdDev',\
      'NDTI_mean','NDTI_stdDev'])})
  return newCount
