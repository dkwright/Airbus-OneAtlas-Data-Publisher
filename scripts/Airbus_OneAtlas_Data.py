from arcpy import AddMessage
import requests
from os import path
from zipfile import ZipFile
try:
    from ujson import loads
except:
    from json import loads
import os

def read_api_key():
    with open(path.abspath(path.join(path.dirname(__file__), '..', 'arcgis', 'settings.json')), 'r') as settings_file:
        data = settings_file.read()
    obj = loads(data)
    api_key = str(obj['apikey'])
    settings_file.close()
    return api_key

def get_token(user_api_key):
    url = 'https://authenticate.foundation.api.oneatlas.airbus.com/auth/realms/IDP/protocol/openid-connect/token'
    payload='client_id=IDP&grant_type=api_key&apikey=' + user_api_key
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.request('POST', url, headers=headers, data=payload)
    #todo try except on HTTP403 (stale apikey)
    return loads(response.text)['access_token']

def get_workspace_id(auth_header):
    url = 'https://data.api.oneatlas.airbus.com/api/v1/me'
    payload={}
    headers = {'Authorization': auth_header}
    my_info = requests.request('GET', url, headers=headers, data=payload)
    return loads(my_info.text)['contract']['workspaceId']

# Get products available in the My Data workspace
def get_products_in_workspace(auth_header, workspace_id):
    url = 'https://search.foundation.api.oneatlas.airbus.com/api/v1/opensearch'
    headers = {'Authorization': auth_header}
    querystring = {"itemsPerPage":100, "startPage":1, "sortBy": "-publicationDate", "workspace": workspace_id}
    headers = {'Cache-Control': 'no-cache','Authorization': auth_header, 'Content-Type': 'application/json'}
    response = requests.request('GET', url, headers=headers, params=querystring)
    products = []
    for feature in loads(response.text)['features']:
        products.append(feature['properties']['id'] + ',' 
            + feature['_links']['download']['href'] + ','
            + feature['_links']['download']['resourceId'])
    return products

def get_product_info(workspace_id, selected_product, auth_header):
    url = 'https://search.foundation.api.oneatlas.airbus.com/api/v1/opensearch'
    querystring = {"workspaceid":workspace_id, "id":selected_product}
    headers = {'Cache-Control': 'no-cache','Authorization': auth_header, 'Content-Type': 'application/json'}
    response = requests.request('GET', url, headers=headers, params=querystring)
    for feature in loads(response.text)['features']:
        product_href = feature['_links']['download']['href']
        product_resource_id = feature['_links']['download']['resourceId']
    return product_href, product_resource_id

def download_product(href, filename, localdir):
    AddMessage('Started downloading {0}'.format(filename))
    global auth_header
    headers = {'Authorization': auth_header}
    image_archive = requests.request('GET', href, headers=headers)
    with open(path.join(download_dir, filename), 'wb') as f:
        f.write(image_archive.content)
    AddMessage('Finished downloading {0}'.format(filename))
    return

def extract_product(product_resource_id, download_dir):
    zf = ZipFile(path.join(download_dir, product_resource_id))
    AddMessage('Extracting product archive...')
    archive_base_name = path.splitext(product_resource_id)[0]
    archive_local_path = path.join(download_dir, archive_base_name)
    zf.extractall(archive_local_path)
    zf.close()
    AddMessage('Product extracted to: ' + archive_local_path)
    return

def get_product_proc_level(product_folder):
    AddMessage('Seeking DIMAP file(s) in: ' + path.join(download_dir, product_folder))
    from os import walk
    instruments = []
    instruments_idx = []
    spec_procs = []
    geom_procs = []
    rad_procs = []
    dims = 0
    for root, dirs, files in walk(path.join(download_dir, product_folder)):
        for file in files:
            if file.startswith('DIM_') and file.endswith('.XML'):
                dims += 1
                dimap_file = path.join(root, file)
                # open the DIMAP metadata and discover the product processing level
                import xml.etree.ElementTree as ET
                root = ET.parse(dimap_file).getroot()
                for x in root.iter('INSTRUMENT'):
                    instruments.append(x.text)
                for x in root.iter('INSTRUMENT_INDEX'):
                    instruments_idx.append(x.text)
                for x in root.iter('SPECTRAL_PROCESSING'):
                    spec_procs.append(x.text)
                for x in root.iter('GEOMETRIC_PROCESSING'):
                    geom_procs.append(x.text)
                for x in root.iter('RADIOMETRIC_PROCESSING'):
                    rad_procs.append(x.text)
    for y in range(len(spec_procs)):
        if dims > 1:
            product_proc_level = instruments[y] + '_' + instruments_idx[y] + ' BUNDLE ' + spec_procs[y] + ' ' + geom_procs[y] + ' ' + rad_procs[y]
        else:
            product_proc_level = instruments[y] + '_' + instruments_idx[y] + ' PANSHARPENED ' + spec_procs[y] + ' ' + geom_procs[y] + ' ' + rad_procs[y]
    return product_proc_level

def publish_layer(infiles, airbus_raster_type, product_proc_level, layer_name, layer_type, make_image_collection, pansharpen_from_bundle):

    AddMessage('*********publish_layer parameters*********')
    AddMessage('infiles: ' + str(infiles))
    AddMessage('airbus_raster_type: ' + airbus_raster_type)
    AddMessage('product_proc_level: ' + product_proc_level)
    AddMessage('layer_name: ' + layer_name)
    AddMessage('layer_type: ' + layer_type)
    AddMessage('make_image_collection: ' + make_image_collection)
    AddMessage('pansharpen_from_bundle: ' + pansharpen_from_bundle)

    if layer_type == 'Dynamic Imagery Layer':
        tiles_only_bool = False
    else:
        tiles_only_bool = True
    AddMessage('tiles_only_bool: ' + str(tiles_only_bool))

    for product in infiles:
        AddMessage('inFiles: ' + product)
    AddMessage('Layer Name: ' + layer_name)
    AddMessage('Layer Type: ' + layer_type)

    if len(infiles) < 2:
        infiles = infiles[0]

    if airbus_raster_type == 'Pleiades-1':
        bandMapping = [{"bandName":"Red","wavelengthMin":620,"wavelengthMax":700},
                    {"bandName":"Green","wavelengthMin":510,"wavelengthMax":590},
                    {"bandName":"Blue","wavelengthMin":450,"wavelengthMax":530},
                    {"bandName":"NearInfrared","wavelengthMin":775,"wavelengthMax":915}]
    else:
        if airbus_raster_type == 'SPOT 6' or airbus_raster_type == 'SPOT 7':        
            bandMapping = [{"bandName":"Red","wavelengthMin":625,"wavelengthMax":695},
                    {"bandName":"Green","wavelengthMin":530,"wavelengthMax":590},
                    {"bandName":"Blue","wavelengthMin":450,"wavelengthMax":520},
                    {"bandName":"NearInfrared","wavelengthMin":760,"wavelengthMax":890}]
    
    if product_proc_level.split()[1] == 'BUNDLE' and product_proc_level.split()[4] == 'DISPLAY' and pansharpen_from_bundle == 'true':
        processingTemplate = 'Pansharpen Display'
        productType = 'ORTHO DISPLAY'
    elif product_proc_level.split()[1] == 'BUNDLE' and product_proc_level.split()[4] == 'DISPLAY' and pansharpen_from_bundle == 'false':
        processingTemplate = 'Multispectral Display'
        productType = 'ORTHO DISPLAY'
    elif product_proc_level.split()[1] == 'BUNDLE' and product_proc_level.split()[4] == 'REFLECTANCE' and pansharpen_from_bundle == 'true':
        processingTemplate = 'Pansharpen Reflectance'
        productType = 'ORTHO REFLECTANCE'
    elif product_proc_level.split()[1] == 'BUNDLE' and product_proc_level.split()[4] == 'REFLECTANCE' and pansharpen_from_bundle == 'false':
        processingTemplate = 'Multispectral Reflectance'
        productType = 'ORTHO REFLECTANCE'
    elif product_proc_level.split()[1] == 'PANSHARPENED' and product_proc_level.split()[4] == 'REFLECTANCE':
        processingTemplate = 'Multispectral Reflectance'
        productType = 'ORTHO REFLECTANCE'
    elif product_proc_level.split()[1] == 'PANSHARPENED' and product_proc_level.split()[4] == 'DISPLAY':
        processingTemplate = 'Multispectral Display'
        productType = 'ORTHO DISPLAY'
    
    dyn_raster_type_params = {'productType':productType,'processingTemplate':processingTemplate}
    if 'Pansharpen' in processingTemplate:
        dyn_raster_type_params.update({'pansharpenType':'Gram-Schmidt','filter':'SharpenMore','pansharpenWeights':'0.9 0.75 0.5 0.5'})

    dyn_context = {'outSR':{'wkid':3857},'bandMapping':bandMapping,'resamplingMethod':'BILINEAR','compression':'LERC 0',
           'buildFootprints':True,'footprintsArguments':{'method':'RADIOMETRY',
                                                         'minValue':1,
                                                         'maxValue':'',
                                                         'shrinkDistance':50,
                                                         'skipOverviews':True,
                                                         'updateBoundary':True,
                                                         'maintainEdge':False,
                                                         'simplification':None,
                                                         'numVertices':20,
                                                         'minThinnessRatio':0.05,
                                                         'maxSliverSize':20,
                                                         'requestSize':2000,
                                                         'minRegionSize':100},
                                                         'buildOverview':True}

    AddMessage('dyn_raster_type_params: ' + str(dyn_raster_type_params))
    AddMessage('dyn_context: ' + str(dyn_context))
    AddMessage('airbus_raster_type: ' + airbus_raster_type)
    AddMessage('bandMapping: ' + str(bandMapping))
    AddMessage('processingTemplate: ' + processingTemplate)
    AddMessage('productType: ' + productType)
    AddMessage('Publishing layer: ' + layer_name)

    from arcgis.gis import GIS
    gis = GIS('Pro', verify_cert=False)
    
    if make_image_collection == 'true':
        from arcgis.raster.analytics import create_image_collection
        create_image_collection_layer = create_image_collection(image_collection = layer_name,
                                                                input_rasters = infiles,
                                                                raster_type_name = airbus_raster_type,
                                                                raster_type_params = dyn_raster_type_params,
                                                                context = dyn_context,
                                                                tiles_only = tiles_only_bool,
                                                                gis = gis)
    else:
        from arcgis.raster.analytics import copy_raster
        copy_raster_op = copy_raster(input_raster = infiles,
                                    output_name = layer_name,
                                    raster_type_name = airbus_raster_type,
                                    raster_type_params = dyn_raster_type_params,
                                    context = dyn_context,
                                    tiles_only = tiles_only_bool,
                                    gis = gis)

    AddMessage('Published {}: {}'.format(layer_type, layer_name))

if __name__ == '__main__':
    AddMessage('Started processing...')
    Debug = False
    if Debug:
        selected_product = '6bba59e1-4e51-4461-8704-94d7d5c240b9'
        download_dir = r'C:\data\Airbus\OAD\ToolboxTests'
        auth_header = 'Bearer: token'
    else:
        from arcpy import GetParameterAsText
        selected_product = GetParameterAsText(0)
        all_products = GetParameterAsText(1)
        download_dir = GetParameterAsText(2)
        extract = GetParameterAsText(3)
        publish = GetParameterAsText(4)
        layer_name = GetParameterAsText(5)
        layer_type = GetParameterAsText(6)
        make_image_collection = GetParameterAsText(7)
        pansharpen_from_bundle = GetParameterAsText(8)
        api_key = read_api_key()
        auth_header = 'Bearer ' + get_token(api_key)
        workspace_id = get_workspace_id(auth_header) 

    if all_products == 'false' or all_products == '':
        selected_product = selected_product.split('=',1)[1]
        AddMessage('Selected Product: ' + selected_product)
        AddMessage('Download Directory: ' + download_dir)
        product_href, product_resource_id = get_product_info(workspace_id, selected_product, auth_header)
        if not path.exists(path.join(download_dir, product_resource_id)):
            download_product(product_href, product_resource_id, download_dir)
        else:
            AddMessage('File {} already exists, skipping download.'.format(path.join(download_dir, product_resource_id)))
        if extract == 'true':
            extract_product(product_resource_id, download_dir)
            # find the DIMAP file in extracted product dir
            product_proc_level = get_product_proc_level(path.splitext(product_resource_id)[0])
    else:
        AddMessage('All products selected')
        AddMessage('Download Directory: ' + download_dir)
        products_list = get_products_in_workspace(auth_header, workspace_id)
        num_products = len(products_list)
        phr_bundle_ortho_disp = []
        phr_bundle_ortho_refl = []
        phr_ps_ortho_disp = []
        phr_ps_ortho_refl = []
        spot6_bundle_ortho_disp = []
        spot6_bundle_ortho_refl = []
        spot6_ps_ortho_disp = []
        spot6_ps_ortho_refl = []
        spot7_bundle_ortho_disp = []
        spot7_bundle_ortho_refl = []
        spot7_ps_ortho_disp = []
        spot7_ps_ortho_refl = []
        i = 1
        for product in products_list:
            AddMessage('Handling product {} of {}'.format(i, num_products))
            product_resource_id = product.split(',')[2]
            archive_base_name = path.splitext(product_resource_id)[0]
            archive_local_path = path.join(download_dir, archive_base_name)
            if not path.exists(path.join(download_dir, product_resource_id)):
                download_product(product.split(',')[1], product_resource_id, download_dir)
            else:
                AddMessage('File {} already exists, skipping download.'.format(path.join(download_dir, product_resource_id)))
            if extract == 'true':
                extract_product(product_resource_id, download_dir)
                # find the DIMAP file in extracted product dir
                this_product = get_product_proc_level(archive_local_path)
                if this_product == 'PHR_1A BUNDLE P ORTHO DISPLAY' or this_product == 'PHR_1B BUNDLE P ORTHO DISPLAY': 
                    phr_bundle_ortho_disp.append(archive_local_path)
                if this_product == 'PHR_1A BUNDLE P ORTHO REFLECTANCE' or this_product == 'PHR_1B BUNDLE P ORTHO REFLECTANCE': 
                    phr_bundle_ortho_refl.append(archive_local_path)
                if this_product == 'PHR_1A PANSHARPENED PMS ORTHO DISPLAY' or this_product == 'PHR_1B PANSHARPENED PMS ORTHO DISPLAY': 
                    phr_ps_ortho_disp.append(archive_local_path)
                if this_product == 'PHR_1A PANSHARPENED PMS ORTHO REFLECTANCE' or this_product == 'PHR_1B PANSHARPENED PMS ORTHO REFLECTANCE': 
                    phr_ps_ortho_refl.append(archive_local_path)
                if this_product == 'SPOT_6 BUNDLE P ORTHO DISPLAY': 
                    spot6_bundle_ortho_disp.append(archive_local_path)
                if this_product == 'SPOT_6 BUNDLE P ORTHO REFLECTANCE': 
                    spot6_bundle_ortho_refl.append(archive_local_path)
                if this_product == 'SPOT_6 PANSHARPENED PMS ORTHO DISPLAY': 
                    spot6_ps_ortho_disp.append(archive_local_path)
                if this_product == 'SPOT_6 PANSHARPENED PMS ORTHO REFLECTANCE': 
                    spot6_ps_ortho_refl.append(archive_local_path) 
                if this_product == 'SPOT_7 BUNDLE P ORTHO DISPLAY': 
                    spot7_bundle_ortho_disp.append(archive_local_path)
                if this_product == 'SPOT_7 BUNDLE P ORTHO REFLECTANCE': 
                    spot7_bundle_ortho_refl.append(archive_local_path)
                if this_product == 'SPOT_7 PANSHARPENED PMS ORTHO DISPLAY': 
                    spot7_ps_ortho_disp.append(archive_local_path)
                if this_product == 'SPOT_7 PANSHARPENED PMS ORTHO REFLECTANCE': 
                    spot7_ps_ortho_refl.append(archive_local_path) 
            i += 1

    if publish == 'true':
        if all_products == 'false' or all_products == '': 
            if product_proc_level.split()[0] == 'PHR_1A' or product_proc_level.split()[0] == 'PHR_1B':
                airbus_raster_type = 'Pleiades-1'
            else:
                if product_proc_level.split()[0] == 'SPOT_6':
                    airbus_raster_type = 'SPOT 6'
                if product_proc_level.split()[0] == 'SPOT_7':
                    airbus_raster_type = 'SPOT 7' 
            archive_base_name = path.splitext(product_resource_id)[0]
            archive_local_path = path.join(download_dir, archive_base_name)
            infiles = []
            infiles.append(archive_local_path)

        #if layer_type == 'Dynamic Imagery Layer':
        #    tiles_only_bool = False
        #else:
        #    tiles_only_bool = True
        #AddMessage('tiles_only_bool: ' + str(tiles_only_bool))

        if all_products == 'false' or all_products == '':            
            publish_layer(infiles, airbus_raster_type, product_proc_level, layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
        else:
            #AddMessage('Publishing all products in layer groups...')
            AddMessage('Reporting all layer groups that have content...')
            # Manage publishing groups that have paths in them
            if len(phr_bundle_ortho_disp) > 0:
                airbus_raster_type = 'Pleiades-1'
                product_proc_level = 'PHR_1 BUNDLE P ORTHO DISPLAY'
                AddMessage('phr_bundle_ortho_disp contains the following paths:')
                for item in phr_bundle_ortho_disp:
                    AddMessage(item)
                infiles = phr_bundle_ortho_disp
                group_layer_name = layer_name + '_phr_bundle_ortho_disp_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(phr_bundle_ortho_refl) > 0:
                airbus_raster_type = 'Pleiades-1'
                product_proc_level = 'PHR_1 BUNDLE P ORTHO REFLECTANCE'
                AddMessage('phr_bundle_ortho_refl contains the following paths:')
                for item in phr_bundle_ortho_refl:
                    AddMessage(item)
                infiles = phr_bundle_ortho_refl
                group_layer_name = layer_name + '_phr_bundle_ortho_refl_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(phr_ps_ortho_disp) > 0:
                airbus_raster_type = 'Pleiades-1'
                product_proc_level = 'PHR_1 PANSHARPENED PMS ORTHO DISPLAY'
                AddMessage('phr_ps_ortho_disp contains the following paths:')
                for item in phr_ps_ortho_disp:
                    AddMessage(item)
                infiles = phr_ps_ortho_disp
                group_layer_name = layer_name + '_phr_ps_ortho_disp_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(phr_ps_ortho_refl) > 0:
                airbus_raster_type = 'Pleiades-1'
                product_proc_level = 'PHR_1 PANSHARPENED PMS ORTHO REFLECTANCE'
                AddMessage('phr_ps_ortho_refl contains the following paths:')
                for item in phr_ps_ortho_refl:
                    AddMessage(item)
                infiles = phr_ps_ortho_refl
                group_layer_name = layer_name + '_phr_ps_ortho_refl_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot6_bundle_ortho_disp) > 0:
                airbus_raster_type = 'SPOT 6'
                product_proc_level = 'SPOT_6 BUNDLE P ORTHO DISPLAY'
                AddMessage('spot6_bundle_ortho_disp contains the following paths:')
                for item in spot6_bundle_ortho_disp:
                    AddMessage(item)
                infiles = spot6_bundle_ortho_disp
                group_layer_name = layer_name + '_spot6_bundle_ortho_disp_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot6_bundle_ortho_refl) > 0:
                airbus_raster_type = 'SPOT 6'
                product_proc_level = 'SPOT_6 BUNDLE P ORTHO REFLECTANCE'
                AddMessage('spot6_bundle_ortho_refl contains the following paths:')
                for item in spot6_bundle_ortho_refl:
                    AddMessage(item)
                infiles = spot6_bundle_ortho_refl
                group_layer_name = layer_name + '_spot6_bundle_ortho_refl_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot6_ps_ortho_disp) > 0:
                airbus_raster_type = 'SPOT 6'
                product_proc_level = 'SPOT_6 PANSHARPENED PMS ORTHO DISPLAY'
                AddMessage('spot6_ps_ortho_disp contains the following paths:')
                for item in spot6_ps_ortho_disp:
                    AddMessage(item)
                infiles = spot6_ps_ortho_disp
                group_layer_name = layer_name + '_spot6_ps_ortho_disp_group'
                publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot6_ps_ortho_refl) > 0:
                airbus_raster_type = 'SPOT 6'
                product_proc_level = 'SPOT_6 PANSHARPENED PMS ORTHO REFLECTANCE'
                AddMessage('spot6_ps_ortho_refl contains the following paths:')
                for item in spot6_ps_ortho_refl:
                    AddMessage(item)
                infiles = spot6_ps_ortho_refl
                group_layer_name = layer_name + '_spot6_ps_ortho_refl_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot7_bundle_ortho_disp) > 0:
                airbus_raster_type = 'SPOT 7'
                product_proc_level = 'SPOT_7 BUNDLE P ORTHO DISPLAY'
                AddMessage('spot7_bundle_ortho_disp contains the following paths:')
                for item in spot7_bundle_ortho_disp:
                    AddMessage(item)
                infiles = spot7_bundle_ortho_disp
                group_layer_name = layer_name + '_spot7_bundle_ortho_disp_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot7_bundle_ortho_refl) > 0:
                airbus_raster_type = 'SPOT 7'
                product_proc_level = 'SPOT_7 BUNDLE P ORTHO REFLECTANCE'
                AddMessage('spot7_bundle_ortho_refl contains the following paths:')
                for item in spot7_bundle_ortho_refl:
                    AddMessage(item)
                infiles = spot7_bundle_ortho_refl
                group_layer_name = layer_name + '_spot7_bundle_ortho_refl_group'
                publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot7_ps_ortho_disp) > 0:
                airbus_raster_type = 'SPOT 7'
                product_proc_level = 'SPOT_7 PANSHARPENED PMS ORTHO DISPLAY'
                AddMessage('spot7_ps_ortho_disp contains the following paths:')
                for item in spot7_ps_ortho_disp:
                    AddMessage(item)
                infiles = spot7_ps_ortho_disp
                group_layer_name = layer_name + '_spot7_ps_ortho_disp_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            if len(spot7_ps_ortho_refl) > 0:
                airbus_raster_type = 'SPOT 7'
                product_proc_level = 'SPOT_7 PANSHARPENED PMS ORTHO REFLECTANCE'
                AddMessage('spot7_ps_ortho_refl contains the following paths:')
                for item in spot7_ps_ortho_refl:
                    AddMessage(item)
                infiles = spot7_ps_ortho_refl
                group_layer_name = layer_name + '_spot7_ps_ortho_refl_group'
                #publish_layer(infiles, airbus_raster_type, product_proc_level, group_layer_name, layer_type, make_image_collection, pansharpen_from_bundle)
            
AddMessage('Finished processing.')