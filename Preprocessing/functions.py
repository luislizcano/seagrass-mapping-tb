import ee
ee.Initialize()

## Function for scaling bands and preserving image metadata
def rescale(image):
  img = ee.Image(image).divide(10000)
  return img.copyProperties(image, image.propertyNames())

## Function to mask land (with feature collection) in an image collection
def maskLand(imgColl, geometry):
  def apply(image):
    mask = ee.Image.constant(1).clip(geometry).mask().Not()
    return image.updateMask(mask)
  return imgColl.map(apply)

## Function to clip an image collection by REGION
def clipRegion(imgColl, geometry):
  def apply(image):
    maskRegion = ee.Image.constant(1).clip(geometry).mask()
    return image.updateMask(maskRegion)
  return imgColl.map(apply)

## Function to clean joins.
def cleanJoin(feature):
  return ee.Image.cat(feature.get('stats')).copyProperties(feature.get('counts'))

## Function to calculate NDTI
def NDTI(image):
  ndti = image.normalizedDifference(['B4','B3']).rename('NDTI')
  return image.addBands(ndti)

## Statistics function. It retrieves the mean and std values of the bands of interest 
## from each image in the collection.
def getStats(imgColl, region):
  def apply(img):
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
  return imgColl.map(apply)

## Function for counting pixels
def countPixels(imgColl, region):
  def apply(img):
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
  return imgColl.map(apply)
  
## Load Cloud Mask function for Sentinel-2 Images
# =============================================================================
# Function to mask clouds using band thresholds.

# Buildings, Sand and Glinted pixels are too bright so they are also masked.
# It works very well for oceanographic purposes. It needs to be tweked to work
# with inland areas.

## Usage:
# img = image to apply cloud mask
# cloudThresh = integer used as threshold to mask clouds (see more info below)
# =============================================================================
## Composite parameters
## cloudThresh: If using the cloudScoreTDOMShift method-Threshold for cloud 
##     masking (lower number masks more clouds.  Between 10 and 30 generally 
##     works best).
## 20 is the best value for Sentinel-2 according to Zhu et al. (2015) & 
## Qiu et al. 2019 (https://doi.org/10.1016/j.rse.2019.05.024)
#cloudThresh = 12 # 12 works best for me. At 2 it cleans all cirrus, but land as well.

## A helper to apply an expression and linearly rescale the output.
## Used in the landsatCloudScore function.
def threshold(img, exp, thresholds):
  return (img.expression(exp, {'img': img})
    .subtract(thresholds[0]).divide(thresholds[1] - thresholds[0]))
 
## For BOA Sentinel-2 images, processed with the Py6S model 
## Adapted according to Chastain et al. 2019 (https://doi.org/10.1016/j.rse.2018.11.012).
## Compute a cloud score:
def CloudScore6S(imgColl, cloudThresh):
  thrValue = int(cloudThresh)
  def apply(img):
    ## Compute several indicators of cloudyness and take the minimum of them.
    ## Bands required: [B1,B2,B3,B4,B8,B11,B12]
    score = ee.Image(1.0)

    ## Clouds are reasonably bright in the blue band.
    ## (BLUE−0.1) / (0.5−0.1)
    score = score.min(threshold(img, 'img.B2', [0.01, 0.3])) #[0.01,0.5]-for ocean

    ## Aerosols.
    ## (AEROSOL−0.1) / (0.3−0.1)
    score = score.min(threshold(img, 'img.B1', [0.01, 0.3])) #[0.01,0.5]-for ocean

    ## Clouds are reasonably bright in all visible bands.
    ## (BLUE+GREEN+RED−0.2) / (0.8−0.2)
    score = score.min(threshold(img, 'img.B4 + img.B3 + img.B2', [0.01, 0.8]))

    ## (((NIR−SWIR1)/(NIR+SWIR1))+0.1) / (0.1+0.1)
    score =  score.min(threshold(img, 'img.B8 + img.B11 + img.B12', [0.01, 0.8])) #.multiply(100).byte()

    ## However, clouds are not snow.
    ## (((GREEN−SWIR1)/(GREEN+SWIR1))−0.8) / (0.6−0.8)
    ndsi = img.normalizedDifference(['B3', 'B11'])
    score =  score.min(threshold(ndsi, 'img', [0.8, 0.6])).multiply(100).byte()
           
    ## Apply threshold
    score = score.lt(thrValue).rename('cloudMask')
    img = img.updateMask(img.mask().And(score))
    return ee.Image(img).addBands(score)
  return imgColl.map(apply)

## Deglint function (applied on single images -not collections)
def deglint(img, geometry):
  image = ee.Image(img)
  reducer = ee.Reducer.linearFit()
  scale = 10
  
  ## Fit a linear model between NIR and other bands, in the sunglint polygons
  ## Output: a dictionary such that: linear_fit.keys() =  ["coefficients","residuals"]
  
  ## NIR vs COASTAL
  linearFit1 = image.select(['B8', 'B1']).reduceRegion(**{
    'reducer': reducer,
    'geometry': geometry,
    'scale': scale,
    'maxPixels': 1e12})
  
  ## NIR vs BLUE
  linearFit2 = image.select(['B8', 'B2']).reduceRegion(**{
    'reducer': reducer,
    'geometry': geometry,
    'scale': scale,
    'maxPixels': 1e12})
  
  ## NIR vs GREEN
  linearFit3 = image.select(['B8', 'B3']).reduceRegion(**{
    'reducer': reducer,
    'geometry': geometry,
    'scale': scale,
    'maxPixels': 1e12})
  
  ## NIR vs RED
  linearFit4 = image.select(['B8', 'B4']).reduceRegion(**{
    'reducer': reducer,
    'geometry': geometry,
    'scale': scale,
    'maxPixels': 1e12})
  
  ## Extract the slope of the fit, convert it into a constant image
  slopeImage = (ee.Dictionary({'B1': linearFit1.get('scale'), 
                              'B2': linearFit2.get('scale'), 
                              'B3': linearFit3.get('scale'), 
                              'B4': linearFit4.get('scale')}).toImage())
  
  ## Calculate the minimum of NIR in the image, in the sunglint polygons
  minNIR = image.select('B8').reduceRegion(**{
    'reducer': ee.Reducer.min(),
    'geometry': geometry,
    'scale': scale,
    'maxPixels': 1e12}).toImage(['B8'])
  
  ## Apply the expression  
  return image.select(['B1','B2', 'B3', 'B4']).subtract(slopeImage.multiply((image.select('B8')).subtract(minNIR)))

