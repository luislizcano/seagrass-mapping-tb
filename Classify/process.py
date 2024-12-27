def start_processing(imageSource,satellite,regionName,boaFolder,exportFolder,dataFolder,smoothStr,
                     nameCode,regionCountry,state,imageList,sand_areas,groundPoints,land,regions,cloud,dii,flat,turbid):
    """
    Description of arguments required:
    ----------------------------------
    imageSource (str) = use 'ee' or 'assets'. It defines whether the L2 images comes from the Earth Engine catalog or user Assets.
    satellite (str)   = use 'Sentinel2', 'Landsat8', 'Landsat7', or 'Landsat5'. It defines the type of satellite sensor.
    regionName (str)  = used as metadata, and for loading predefined geometries used along the script.
    boaFolder (str)   = user defined location of imageCollection containing L2 images from user Assets. Only used if imageSource is set as 'Assets'.
    exportFolder (str)= user defined location to save classified images in user EE Assets.
    dataFolder (str)  = user defined folder name of ground-truth dataset in user Assets. It is complement of groundPoints argument.
    smoothStr (str)   = use 'smooth' or 'raw' to decide whether to apply a convolution kernel for smoothing L2 image before classification.
    nameCode (str)    = used as metadata. Unique codes of four digits related to the loaded region in regionName.
    regionCountry(str)= used as metadata. Country of the region of interest.
    state (str)       = used as metadata. State of the region of interest, if applicable.
    imageList (list)  = list of specific image IDs.
    sand_areas (ee object) = to import featureCollection (dataset) of sand polygons for DII.
    groundPoints (ee object) = to import featureCollection (dataset) of ground-truth points.
    land (ee object)  = to import imageCollection (dataset) of predefined images to mask land.
    regions (ee object) = to import featureCollection (dataset) of predefined region geometries.
    cloud (int)       = use 1 to apply cloud mask, if not set as 0.
    dii (int)         = use 1 to apply depth invariant index and add it as band, if not set as 0.
    flat (int)        = use 1 to apply tidal flat mask, if not set as 0.
    turbid (int)      = use 1 to apply turbidity mask, if not set as 0.
    """
    
    import pandas as pd
    import xlsxwriter
    import datetime
    from functions import CloudScore6S,landMaskFunction,tidalMask,turbidityMask,DII
    
    from google.colab import auth
    auth.authenticate_user()

    import google
    SCOPES = ['https://www.googleapis.com/auth/cloud-platform', 'https://www.googleapis.com/auth/earthengine']
    CREDENTIALS, project_id = google.auth.default(default_scopes=SCOPES)

    import ee
    ee.Initialize(CREDENTIALS, project='earth-engine-252816')

    
    print('Initiating...')

    ## Initiate loop:
    for i in range(len(imageList)):
        imageID = imageList[i]

        print('Preparing image '+imageID)

        ######################   Prepare image metadata  #########################

        ## If the image source is your asset, then define the folder where the satellite image is:
        if 'assets'== imageSource:
            ## Load BOA image from assets:
            if 'Sentinel' in satellite:
                imageTarget = ee.Image("projects/imars-3d-wetlands/Sentinel-2_L2_Luis/"+boaFolder+'/'+imageID)
            elif 'Landsat' in satellite:
                imageTarget = ee.Image("projects/imars-3d-wetlands/Sentinel-2_L2_Luis/"+boaFolder+'/'+imageID)
            ## Get image metadata:
            imageSat = imageTarget.get('satellite').getInfo() #Image satellite
            imageTile = imageTarget.get('tile_id').getInfo() #Image tile id
            imageDate = imageTarget.get('date').getInfo() #Image date
            imageGeometry = imageTarget.geometry() #Tile geometry.

        ## If the image source is an EE collection, then define the satellite collection:
        if 'ee'== imageSource:
            ## Load BOA image collection from EE cloud:
            if 'Sentinel' in satellite:
                image = ee.Image("COPERNICUS/S2_SR_HARMONIZED/"+imageID)
                imageTarget = image.divide(10000).set(image.toDictionary(image.propertyNames()))
                imageSat = imageTarget.get('SPACECRAFT_NAME').getInfo() #Image satellite
                imageTile = imageTarget.get('MGRS_TILE').getInfo() #Image tile id
                ee_date = imageTarget.get('GENERATION_TIME').getInfo()
                imageDate = str(datetime.datetime.utcfromtimestamp(ee_date/1000.0)) #Image date
                imageGeometry = imageTarget.geometry() #Tile geometry.
            elif 'Landsat8' == satellite:
                image = ee.Image("LANDSAT/LC08/C01/T1_SR/"+imageID)
                imageTarget = image.divide(10000).set(image.toDictionary(image.propertyNames()))
                imageSat = satellite
                imageTile = str(imageTarget.get('WRS_PATH').getInfo())+str(imageTarget.get('WRS_ROW').getInfo()) #Image tile id
                imageDate = imageTarget.get('SENSING_TIME').getInfo()
                imageGeometry = imageTarget.geometry() #Tile geometry.
            elif 'Landsat7' == satellite:
                image = ee.Image("LANDSAT/LE07/C01/T1_SR/"+imageID)
                imageTarget = image.divide(10000).set(image.toDictionary(image.propertyNames()))
                imageSat = satellite
                imageTile = str(imageTarget.get('WRS_PATH').getInfo())+str(imageTarget.get('WRS_ROW').getInfo()) #Image tile id
                imageDate = imageTarget.get('SENSING_TIME').getInfo()
                imageGeometry = imageTarget.geometry() #Tile geometry.
            elif 'Landsat5' == satellite:
                image = ee.Image("LANDSAT/LT05/C01/T1_SR/"+imageID)
                imageTarget = image.divide(10000).set(image.toDictionary(image.propertyNames()))
                imageSat = satellite
                imageTile = str(imageTarget.get('WRS_PATH').getInfo())+str(imageTarget.get('WRS_ROW').getInfo()) #Image tile id
                imageDate = imageTarget.get('SENSING_TIME').getInfo()
                imageGeometry = imageTarget.geometry() #Tile geometry.

        if 'Sentinel' in imageSat:
            imageScale = 10 # Sentinel resolution
        else:
            imageScale = 30 # Landsat resolution
        
        ## Region of interest:
        aoi = regions.filter(ee.Filter.eq('name',regionName))


        ###########################    CLOUD MASK    #############################
        if cloud == 1:
          ## Recommended Threshold values for
          ## *Sentinel: 2
          ## *Landsat: 5
          if 'Sentinel' in imageSat:
              threshold = 5
          else:
              threshold = 5
  
          ## Apply cloud mask
          imageTarget = CloudScore6S(imageSat, imageTarget, threshold)


        #############################    LAND MASK    ############################

        ## Apply land mask
        #landMask = landMaskFunction(imageTarget, land) ## Use if Land is a featureCollection
        landMask = imageTarget.updateMask(land.max()) ## Use if Land is an imageCollection


        ###################   MASK TIDAL FLATS & TURBIDITY  ######################
        ## NOTE: using tidal flat and turbidity mask before the DII calculation
        ## was producing weird classification outputs. So, skip this part.  
        ## Set parameter values
        # if 'Sentinel' in imageSat:
        #     nir = 'B8'
        #     green = 'B3'
        #     swir = 'B11'
        #     blue = 'B2'
        # elif 'Landsat8' in imageSat:
        #     nir = 'B5'
        #     green = 'B3'
        #     swir = 'B6'
        #     blue = 'B2'
        # else:
        #     nir = 'B4'
        #     green = 'B2'
        #     swir = 'B5'
        #     blue = 'B1'
        
        ## Apply tidal flat mask
        #ndwiMask = tidalMask(landMask,nir,green)
        
        ## Apply turbidity mask for the whole image
        #finalMask = turbidityMask(ndwiMask,imageGeometry,nir,swir,blue,land)
        #finalMask = landMask
                
        print('   Image masked...')
        
        
        ####################    WATER COLUMN CORRECTION    #######################    
        
        if dii == 1:
          ## Filter sand polygons by tile/area:
          #sand = ee.FeatureCollection(sand_areas).flatten().filterBounds(imageGeometry)
          sand = ee.FeatureCollection(sand_areas).filterBounds(imageGeometry)

          ## Run the Depth-Invariant Index Function
          imageDII = DII(landMask, imageScale, sand)

          ## Select bands to sample. The B/G band is B2B3 in Sentinel-2 and Landsat-8, and B1B2 for Landsat-7/5
          if 'Sentinel' in imageSat or 'Landsat8' in imageSat:
              bandsClass = ['B1','B2', 'B3', 'B4','B2B3']
              bg = ['B2B3']
          else:
              bandsClass = ['B1','B2', 'B3', 'B1B2']
              bg = ['B1B2']
          finalImage = landMask.addBands(imageDII.select(bg))
          print('   Depth-Invariant index applied...')
        else:
          ## Select bands to sample. The B/G band is B2B3 in Sentinel-2 and Landsat-8, and B1B2 for Landsat-7/5
          if 'Sentinel' in imageSat or 'Landsat8' in imageSat:
              bandsClass = ['B1','B2', 'B3', 'B4']
          else:
              bandsClass = ['B1','B2', 'B3']
          finalImage = landMask


        #######################    LOAD TRAINING DATA    ########################
        # Classes are:

        # 0: Softbottom
        # 1: Hardbottom
        # 2: Seagrass
        # 3: Sparse seagrass //if available

        ## Filter ground points by AOI and display classes
        filterPoints = ee.FeatureCollection(groundPoints).filterBounds(aoi).filterBounds(imageGeometry)


        ###################   CLIP TO REGION & APPLY MASKS   #####################
        ## Apply tidal flat & turbidity masks to specific region of interest:
        # seagrass_mask = ee.Image("users/lizcanosandoval/Seagrass/SeagrassMask_FL_100m")
        # imageClassify = imageClassify.updateMask(seagrass_mask) #For raster
        ## Use image with no turbidity mask
        ## Add B/G band and clip:
        imageClassify = finalImage.clip(aoi)
        ## Create masks
        if flat == 1:
          imageClassify = tidalMask(imageClassify,nir,green)
        if turbid == 1:
          imageClassify = turbidityMask(imageClassify,aoi,nir,swir,blue,land)
        
        ## Add bands of interest to sample training points.
        imageClassify = imageClassify.select(bandsClass)


        ###########################    APPLY SMOOTHER    #########################
        ## Define a boxcar or low-pass kernel (Used if want to smooth the image)
        smooth = ee.Kernel.euclidean(**{
            'radius': 1, 
            'units': 'pixels', 
            'normalize': True
        })

        ## Apply smoother if set:
        if 'smooth' in smoothStr:
            imageClassify = imageClassify.convolve(smooth)
            
            
        ################    GET TRAINING AND VALIDATION DATA    ##################
        ## Sample multi-spectral data using all ground points.
        samplingData = imageClassify.sampleRegions(**{
            'collection': filterPoints,
            'properties': ['class'],
            'scale': imageScale})

        ## Add random numbers to each feature (from 0 to 1).
        randomData = samplingData.randomColumn("random",0)

        ## Split ground data in training (~70%) and validation (~30%) points
        trainingData = randomData.filter(ee.Filter.lt("random",0.7))
        validationData = randomData.filter(ee.Filter.gte("random", 0.7))


        ####################    TRAIN MODELS AND CLASSIFY    #####################
        print('   Training models and classifying...')

        ## Train SVM classifier
        SVM = ee.Classifier.libsvm(**{
           'kernelType': 'RBF',
           'gamma': 100,
           'cost': 100
        })
        trainSVM = SVM.train(**{
           'features': trainingData,
           'classProperty': 'class',
           'inputProperties': bandsClass
        })

        #### Classify the image using the trained classifier
        classifiedSVM = imageClassify.classify(trainSVM)
        
        ## Reproject output:
        classifiedSVM = classifiedSVM.reproject(**{
            'crs': 'EPSG:4326',
            'scale':imageScale
        })

        #######################    TRAINING ACCURACIES    ########################
        print('   Getting accuracies...')
        ## Get a confusion matrix representing resubstitution accuracy.
        ## {Resubstitution error is the error of a model on the training data.}
        ## Axis 0 (first level) of the matrix correspond to the input classes (columns), 
        ## and axis 1 (second level) to the output classes (rows).
        matrixTrainingSVM = trainSVM.confusionMatrix()


        #######################    VALIDATION ACCURACIES    ######################

        ## Calculate accuracy using validation data
        ## Classify the image using the trained classifier
        validationSVM = validationData.classify(trainSVM)

        ## Get a confusion matrix representing expected accuracy (Using validation points - 30%), where:
        #  0: Softbottom
        #  1: Hardbottom
        #  2: Dense Seagrass
        #  3: Spare Seagrass

        ## Axis 0 (the rows) of the matrix correspond to the actual values, 
        ## and Axis 1 (the columns) to the predicted values.
        errorMx = {'actual': 'class', 'predicted': 'classification'}
        errorMatrixSVM = validationSVM.errorMatrix(**errorMx)


        ####################    USER/PRODUCER ACCURACIES    ######################

        ## Estimate user and producer accuracies
        producerAccuracySVM = errorMatrixSVM.producersAccuracy()

        # USER
        userAccuracySVM = errorMatrixSVM.consumersAccuracy()

        print('    Producer accuracy [Seagrass]: ',producerAccuracySVM.get([2,0]).getInfo())
        print('    User accuracy [Seagrass]: ',userAccuracySVM.get([0,2]).getInfo())


        #######################    KAPPA COEFFICIENTS    #########################

        # The Kappa Coefficient is generated from a statistical test to evaluate the accuracy 
        # of a classification. Kappa essentially evaluate how well the classification performed 
        # as compared to just randomly assigning values, i.e. did the classification do better 
        # than random. The Kappa Coefficient can range from -1 to 1. A value of 0 indicated that 
        # the classification is no better than a random classification. A negative number 
        # indicates the classification is significantly worse than random. A value close to 1 
        # indicates that the classification is significantly better than random.
        kappaSVM = errorMatrixSVM.kappa()
        print('    Kappa: ',kappaSVM.getInfo())


        ####################    EXPORT CLASSIFIED IMAGES    ######################
        print('   Exporting classified image to EE Assets...')
        
        method = 'SVM'
        # Rename satellite
        if 'Sentinel' in imageSat:
            sat = 'Sentinel'
        else:
            sat = 'Landsat'

        ## Select classified image
        output_image = ee.Image(classifiedSVM)

        # set some properties for exported image:
        output = output_image.set({'country': regionCountry,
                       'state': state,
                       'location': regionName,
                       'name_code': nameCode,
                       'satellite': imageSat,
                       'tile_id': str(imageTile),
                       'image_id': imageID,                                               
                       'date': imageDate,
                       'year': imageDate[0:4],
                       'classifier': method,
                       'generator': 'Lizcano-Sandoval'
                            })

        # define YOUR assetID. (This do not create folders, you need to create them manually)
        assetID = 'users/lizcanosandoval/Seagrass/'+sat+'/'+exportFolder+'/' ##This goes to an ImageCollection folder
        fileName = imageID+smoothStr+ method +'_'+nameCode
        path = assetID + fileName

        ## Batch Export to Assets
        ee.batch.Export.image.toAsset(\
            image = ee.Image(output),                                                    
            description = method +smoothStr+ imageID,
            assetId = path,
            region = imageGeometry.buffer(10),                                      
            maxPixels = 1e13,
            crs = 'EPSG:4326',
            scale = imageScale).start()
        print('   Classified Image '+str(i+1)+': '+fileName+' submitted...')



        ###############    SAVE MATRICES TO WORKING DIRECTORY    #################
        print('   Saving matrices to working directory...')
        # Extract values from each matrix
        SVM_trainingMatrix = matrixTrainingSVM.array().getInfo()
        SVM_trainingAccuracy = matrixTrainingSVM.accuracy().getInfo()
        SVM_errorMatrix = errorMatrixSVM.array().getInfo()
        SVM_errorAccuracy = errorMatrixSVM.accuracy().getInfo()
        SVM_producerAccuracy = producerAccuracySVM.getInfo()
        SVM_userAccuracy = userAccuracySVM.getInfo()
        SVM_kappa = kappaSVM.getInfo()


        ## Convert matrices to pandas dataframes:
        #Training Matrices
        rowIndex = {0:'Sb', 1:'Hb', 2:'Dn', 3:'Sp'}
        TM_SVM = pd.DataFrame(SVM_trainingMatrix).rename(columns=rowIndex, index=rowIndex)
        TM_concat = pd.concat([TM_SVM], keys=['SVM'])

        #Training Accuracies
        TA_SVM = pd.Series(SVM_trainingAccuracy)
        TA_concat = pd.DataFrame(pd.concat([TA_SVM],ignore_index=True), columns=(['Tr_Accuracy']))\
                        .rename({0:'SVM'})

        #Validation-Error Matrices
        VM_SVM = pd.DataFrame(SVM_errorMatrix).rename(columns=rowIndex, index=rowIndex)
        VM_concat = pd.concat([VM_SVM], keys=['SVM'])

        #Validation Accuracies
        VA_SVM = pd.Series(SVM_errorAccuracy)
        VA_concat = pd.DataFrame(pd.concat([VA_SVM],ignore_index=True), columns=(['Va_Accuracy']))\
                        .rename({0:'SVM'})

        #Producer-User Accuracies
        ## Create a pandas dataframe with producer and user accuracies:
        dfPA_SVM = pd.DataFrame(producerAccuracySVM.getInfo(), columns=['Producer'])
        dfUA_SVM = pd.DataFrame(userAccuracySVM.getInfo()).transpose()

        PU_SVM = pd.concat([dfPA_SVM, dfUA_SVM.rename(columns={0:'User'})], axis=1).rename(index=rowIndex)
        PU_concat = pd.concat([PU_SVM], keys=['SVM'])

        # Kappa coefficients
        Kp_SVM = pd.Series(SVM_kappa)
        Kp_concat = pd.DataFrame(pd.concat([Kp_SVM],ignore_index=True), columns=(['Kappa']))\
                        .rename({0:'SVM'})

        # Extract the number of training and validation points per class:
        trainingInfo = trainingData.aggregate_histogram('class').getInfo()
        validationInfo = validationData.aggregate_histogram('class').getInfo()

        traSeries = pd.Series(trainingInfo)
        valSeries = pd.Series(validationInfo)

        Points_concat = pd.DataFrame(pd.concat([traSeries, valSeries],ignore_index=True,axis=1))\
                        .rename(columns={0:'TraPoints',1:'ValPoints'}).rename({'0':'Sb','1':'Hb','2':'Dn'},axis='index')

        # Organize each matrix in separate excel sheets
        excelName = 'Mrx'+ smoothStr + imageID + '_' + nameCode +'.xlsx'
        excelDir = '/content/drive/My Drive/FromGEE/Matrices/'+excelName
        excel = pd.ExcelWriter(excelDir, engine='xlsxwriter')

        Points_concat.to_excel(excel, sheet_name='Points', index=True, startrow=0)
        TM_concat.to_excel(excel, sheet_name='TrMrx', index=True, startrow=0)
        TA_concat.to_excel(excel, sheet_name='TrAcc', index=True, startrow=0)
        VM_concat.to_excel(excel, sheet_name='VaMrx', index=True, startrow=0)
        VA_concat.to_excel(excel, sheet_name='VaAcc', index=True, startrow=0)
        PU_concat.to_excel(excel, sheet_name='PU-Mrx', index=True, startrow=0)
        Kp_concat.to_excel(excel, sheet_name='Kappa', index=True, startrow=0)

        # Save matrices as .xlsx file:
        excel.close()
        print('   Saved Matrices of '+imageID)

    print('ALL IMAGES HAVE BEEN CLASSIFIED!')
