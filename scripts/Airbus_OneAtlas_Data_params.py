try:
    from ujson import loads, load
    from ujson import dumps, dump
except:
    from json import loads, load
    from json import dumps, dump
from genericpath import isdir
import requests
import arcpy
from os.path import join
from os import path
from os import mkdir
from arcpy import mp
import logging
import time

timestr = time.strftime("%Y%m%d-%H%M%S")
logs_dir = path.abspath(path.join(path.dirname(__file__), '..', 'logs'))
if not path.isdir(logs_dir):
    mkdir(logs_dir)
logfile = join(logs_dir, 'log-{}.txt'.format(timestr))
logging.basicConfig(
    filename=logfile,
    format='%(asctime)s - %(levelname)-8s - %(message)s',
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S')

# Get the current project
aprx = arcpy.mp.ArcGISProject("CURRENT")
defaultGDB = aprx.defaultGeodatabase
fc_name = 'Airbus_Results'
out_fc = join(defaultGDB, fc_name)
#out_fc = join('memory', fc_name)

if not arcpy.Exists(defaultGDB):
    arcpy.CreateFileGDB_management(path.abspath(defaultGDB), path.basename(defaultGDB))
if not arcpy.Exists(out_fc):
    sr = arcpy.SpatialReference(4326)
    arcpy.CreateFeatureclass_management(defaultGDB, fc_name, "POLYGON", spatial_reference = sr)
    arcpy.management.AddFields(
        out_fc,[['id', 'TEXT', 'ID', 60, '', ''],
        ])
if not arcpy.Exists(join(aprx.homeFolder, 'Airbus_Results.lyrx')):
    arcpy.MakeFeatureLayer_management(out_fc, 'Airbus_Results')
    arcpy.management.SaveToLayerFile('Airbus_Results', 'Airbus_Results.lyrx', 'RELATIVE')

# Check for the active Map
try:
    m = aprx.listMaps(aprx.activeMap.name)[0]
    # Check for the layer name in the Map
    layer_list = []
    for lyr in m.listLayers():
        layer_list.append(lyr.name)
    if not 'Airbus_Results' in layer_list: 
        lf = arcpy.mp.LayerFile(path.join(path.split(defaultGDB)[0], 'Airbus_Results.lyrx'))
        m.addLayer(lf)
        # Set layer symbology
        l = m.listLayers('Airbus_Results')[0]
        sym = l.symbology
        sym.renderer.symbol.color = {'RGB' : [0, 0, 0, 0]}
        sym.renderer.symbol.outlineColor = {'RGB' : [255, 0, 0, 100]}
        l.symbology = sym
except:
    logging.info('There is no Map in this ArcGIS Project. Please add one.')
def get_products_in_workspace():
    user_api_key_from_json = get_api_key()
    if user_api_key_from_json == 'your OneAtlas Data API key goes here' or ' ' in user_api_key_from_json:
        return ['Check your API key in: " ' + path.abspath(path.join(path.dirname(__file__), 'settings.json')) + ' and run this tool again.']
    auth_header = 'Bearer ' + get_token(user_api_key_from_json)
    # Get user's One Atlas Data subscription details
    workspace_id = get_subscription_info(auth_header)
    # Query the workspace for delivered products
    url = 'https://search.foundation.api.oneatlas.airbus.com/api/v1/opensearch'
    querystring = {"itemsPerPage":100, "startPage":1, "sortBy": "-publicationDate", "workspace": workspace_id}
    headers = {'Cache-Control': 'no-cache','Authorization': auth_header, 'Content-Type': 'application/json'}
    response = requests.request('GET', url, headers=headers, params=querystring)
    products = []
    for feature in loads(response.text)['features']:
        if ('properties' in feature) and ('sourceIdentifier' in feature['properties']) and ('processingLevel' in feature['properties']) and ('productType' in feature['properties'])  and ('id' in feature['properties']) and ('download' in feature['_links']) and ('resourceId' in feature['_links']['download']) and ('resourceId' in feature['_links']['download']):
            products.append(feature['properties']['sourceIdentifier'] + ', ' 
                + feature['properties']['processingLevel'] + ', '
                + feature['properties']['productType'] + ', '
                + feature['_links']['download']['resourceId'] 
                + ', ID=' + feature['properties']['id'])
    return products

def get_api_key():
    with open(path.abspath(path.join(path.dirname(__file__), 'settings.json')), 'r') as settings_file:
        data = settings_file.read()
    obj = loads(data)
    key = str(obj['apikey'])
    settings_file.close()
    return key

def get_token(api_key):
    url = 'https://authenticate.foundation.api.oneatlas.airbus.com/auth/realms/IDP/protocol/openid-connect/token'
    payload='client_id=IDP&grant_type=api_key&apikey=' + api_key
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.request('POST', url, headers=headers, data=payload)
    logging.info('get_token response: ' + str(response.status_code))
    # TODO try except on HTTP403 (stale apikey)
    return loads(response.text)['access_token']

def get_subscription_info(auth_header):
    url = 'https://data.api.oneatlas.airbus.com/api/v1/me'
    payload={}
    headers = {'Authorization': auth_header}
    my_info = requests.request('GET', url, headers=headers, data=payload)
    workspace_id = loads(my_info.text)['contract']['workspaceId']
    return workspace_id

def get_product_geometry(selected_product):
    user_api_key_from_json = get_api_key()
    auth_header = 'Bearer ' + get_token(user_api_key_from_json)
    logging.info('auth_header:' + auth_header)
    workspace_id = get_subscription_info(auth_header)
    # search the workspace
    url = 'https://search.foundation.api.oneatlas.airbus.com/api/v1/opensearch'
    querystring = {"workspaceid":workspace_id, "id":selected_product}
    headers = {'Cache-Control': 'no-cache','Authorization': auth_header, 'Content-Type': 'application/json'}
    response = requests.request('GET', url, headers=headers, params=querystring)
    for feature in loads(response.text)['features']:
        geometry = feature['geometry']
    return dumps(geometry)

def extent_offset(in_feature, offset, out_feature):
    d = arcpy.Describe(in_feature).extent
    o = offset
    #bl = arcpy.Point(d.XMin-o, d.YMin-o)
    #tl = arcpy.Point(d.XMin-o, d.YMax+o)
    #tr = arcpy.Point(d.XMax+o, d.YMax+o)
    #br = arcpy.Point(d.XMax+o, d.YMin-o)
    bl = arcpy.Point(d.XMax+o, d.YMax+o)
    tl = arcpy.Point(d.XMax+o, d.YMin-o)
    tr = arcpy.Point(d.XMin-o, d.YMin-o)
    br = arcpy.Point(d.XMin-o, d.YMax+o)
    offset_poly = arcpy.Polygon(arcpy.Array([bl, tl, tr, br]), spatial_reference=arcpy.Describe(in_feature).spatialReference)
    return arcpy.CopyFeatures(offset_poly, out_feature)

def get_dl_dir():
    with open(path.abspath(path.join(path.dirname(__file__), 'settings.json')), 'r') as settings_file:
        data = settings_file.read()
    obj = loads(data)
    dl_dir = str(obj['download_dir'])
    logging.info('returning: ' + dl_dir)
    settings_file.close()
    return dl_dir

class ToolValidator:
    # Class to add custom behavior and properties to the tool and tool parameters.
    
    def __init__(self):
        # set self.params for use in other function
        self.params = arcpy.GetParameterInfo()

    def initializeParameters(self):
        # Customize parameter properties. 
        # This gets called when the tool is opened.
        self.params[5].enabled = False
        self.params[6].enabled = False
        self.params[8].enabled = False
        self.params[0].filter.list = get_products_in_workspace()
        self.params[5].value = time.strftime("%Y%m%d-%H%M%S")
        self.params[2].value = get_dl_dir()
        return

    def updateParameters(self):
        # Modify parameter values and properties.
        # This gets called each time a parameter is modified, before 
        # standard validation.

        if self.params[4].value == True:
            self.params[3].value = True
            # if self.params[1].value == True: 
            self.params[5].enabled = True
            self.params[6].enabled = True
            if self.params[6].value == 'Dynamic Imagery Layer':
                self.params[7].enabled = True
            else:
                if self.params[6].value != 'Dynamic Imagery Layer':
                    self.params[7].enabled = False
            if self.params[0].value:
                if self.params[0].value.split(',')[2].replace(' ','') == 'bundle':
                    self.params[8].enabled = True
                else:
                    self.params[8].enabled = False
                # Suggest a layer name if null
                if not self.params[5].value or self.params[5].value == '':
                    suggested_layer_name = self.params[0].value.split(',')[3].replace(' ','')
                    self.params[5].value = suggested_layer_name[:len(suggested_layer_name) - 4]
        else:
            self.params[5].enabled = False
            self.params[6].enabled = False
            self.params[7].enabled = False
            self.params[8].enabled = False

        if self.params[1].value == True:
            self.params[0].enabled = False
            # For now, publishing is only available for a single product selection
            # self.params[4].value = False
            # self.params[5].enabled = False
            # self.params[6].enabled = False
        if self.params[1].value == False:
            self.params[0].enabled = True

        # Get the geometry for selected product
        if self.params[0].value is not None and 'Check your API key' not in self.params[0].filter.list[0]:
            selected_product = self.params[0].value.split('=',1)[1]
            logging.info('Selected product:' + selected_product)
            geojsonpoly = str(get_product_geometry(selected_product))
            # Clear out any previous features
            if int(arcpy.GetCount_management(out_fc)[0]) > 0:
                arcpy.DeleteFeatures_management(out_fc)
            # Insert the geometry and ID from selected product    
            icur = arcpy.da.InsertCursor(out_fc, ['SHAPE@', 'id'])
            newPoly = arcpy.AsShape(geojsonpoly)
            icur.insertRow([newPoly, self.params[0].value.split(',')[0]])
            del icur
            arcpy.RecalculateFeatureClassExtent_management(out_fc)
            desc = arcpy.Describe(out_fc)
            logging.info('Airbus_Results extent: ' + str(desc.extent))
            #extent_offset_feature = join('memory', 'offset_feature')
            #extent_offset(out_fc, 0.00001, extent_offset_feature)
            #desc = arcpy.Describe(extent_offset_feature)      
            if len(aprx.listMaps()) > 0: 
                aprx.activeView.camera.setExtent(desc.extent)
        
        # update the settings json file with user's specified download directory         
        a_file = open(path.abspath(path.join(path.dirname(__file__), 'settings.json')), 'r')
        json_object = load(a_file)
        json_object["download_dir"] = str(self.params[2].value)
        a_file = open(path.abspath(path.join(path.dirname(__file__), 'settings.json')), 'w')
        dump(json_object, a_file)
        a_file.close()
        
        return

    def updateMessages(self):
        # Customize messages for the parameters.
        # This gets called after standard validation.
        if not self.params[0].value:
            self.params[0].setErrorMessage('No product selection has been made.')

        if not self.params[2].value:
            self.params[2].setErrorMessage('Please specify a Download Directory that exists on your machine.')
        
        if not self.params[5].value:
            self.params[5].setErrorMessage('No Layer Name has been specified for publishing.')
        
        if not self.params[6].value:
            self.params[6].setErrorMessage('No Layer Type has been specified for publishing.')

        if self.params[7].value == True:
            self.params[7].setWarningMessage('For Dynamic Image Collection, uploaded images will not be converted to Cloud Raster Format.')
        
        if 'Check your API key' in self.params[0].filter.list[0]: 
            self.params[0].setErrorMessage('Check your API key in: " ' + path.abspath(path.join(path.dirname(__file__), 'settings.json')) + ' and then run this tool again.')
        return

    # def isLicensed(self):
    #     # set tool isLicensed.
    #     return True