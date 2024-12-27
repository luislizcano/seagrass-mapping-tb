### Functions for postprocessing
### Luis Lizcano-Sandoval (2024)

import ee
ee.Initialize()

## Function to select pixels of n frequencies
def mosaic(imgSum, pixelValue):
  sumPixels = imgSum.gte(pixelValue)
  mask = imgSum.updateMask(sumPixels)
  final = ee.Image.constant(1).updateMask(mask).rename('b1')
  return final

## Filter by seagrass pixel values
def seagrassMask(image):
  mask = ee.Image(image).eq(2) # Seagrass code = 2
  return mask.selfMask() # Output seagrass = 1

## Function to mask land (with feature collection) in an image collection
def maskLand(imgColl, geometry):
  def apply(image):
    mask = ee.Image.constant(1).clip(geometry).mask().Not()
    return image.updateMask(mask)
  return imgColl.map(apply)

# ## Calculate areas
# Area = svm_ref.eq(1).multiply(ee.Image.pixelArea())
# reducerArea = Area.reduceRegion(**{
#   'reducer': ee.Reducer.sum(),
#   'geometry': region,
#   'scale': scale,
#   'crs': 'EPSG:4326',
#   'maxPixels': 1e15})

# areaSqKm = ee.Number(reducerArea.get('classification')).divide(1e6);
# print('Area '+year+' (km^2):',areaSqKm);
