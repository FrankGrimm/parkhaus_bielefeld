#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function
import sys, imp
imp.reload(sys)
sys.setdefaultencoding('utf8')
import logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
import codecs

import datetime
import urllib
import requests
from xml.etree import ElementTree
from bs4 import BeautifulSoup
try:
    # Python 2.6-2.7 
    from HTMLParser import HTMLParser
except ImportError:
    # Python 3
    from html.parser import HTMLParser
from w3lib.html import replace_entities

uris = {
	"featureindex": "http://www.bielefeld01.de/geodaten/geo_dienste/wms.php?url=marketing_wms_641&amp;version=1.3.0&amp;service=WMS&amp;request=GetLegendGraphic&amp;sld_version=1.1.0&amp;layer=parken_p&amp;format=image/png&amp;STYLE=parken_p_style",
	"getfeature": "https://www.stadtplan.bielefeld.de/proxy/featureinfo/%%LAYERID%%/?url=marketing_wms_641&&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&FORMAT=image%2Fpng&TRANSPARENT=true&QUERY_LAYERS=%%LAYERID%%&LAYERS=%%LAYERID%%&SRS=%%LOCATION%%&INFO_FORMAT=text%2Fhtml&FEATURE_COUNT=100&I=50&J=50&CRS=%%LOCATION%%&STYLES=&WIDTH=101&HEIGHT=101&BBOX=%%BBOX%%"
}

geo_ns = {
	"opengis": "http://www.opengis.net/wms",
	"xlink": "http://www.w3.org/1999/xlink",
	"gissld": "http://www.opengis.net/sld",
	"mapserver": "http://mapserver.gis.umn.edu/mapserver",
	"xsi": "http://www.w3.org/2001/XMLSchema-instance"
}

#print(uris)
#print(geo_ns)

def getxml(uri):
	response = requests.get(uri)
	tree = ElementTree.fromstring(response.content)
	return tree

def xml_stripns(tag):
	if not '}' in tag:
		return tag
	return  tag.split('}', 1)[1]

def xml_dict(elem):
	if elem is None:
		return {}
	res = {}
	for child in elem.getchildren():
		childtag = xml_stripns(child.tag)
		if not child.getchildren() is None and len(child.getchildren()) > 0:
			res[childtag] = map(xml_dict, child.getchildren())
		elif not child.text is None:
			res[childtag] = child.text.strip()
	if not elem.text is None:
		res['_text'] = elem.text.strip()
	return res

def service_dump(xmlres):
	service_index = 0
	for serviceDescriptor in xmlres.findall('opengis:Service', geo_ns):
		#print('Service %s' % ElementTree.tostring(serviceDescriptor, encoding="us-ascii", method="xml"))
		service_index += 1
		service_dict = xml_dict(serviceDescriptor)
		# print('Service #%s (%s, %s)' % (service_index, service_dict['Name'], service_dict['Title']))

def layer_dump(xmlres):
	#print('Layers:')
	capabilities = xmlres.find('opengis:Capability', geo_ns)
	firstlayer = capabilities.find('opengis:Layer', geo_ns)
	ids = set()
	for layer_index, layerInfo in enumerate(firstlayer.findall('opengis:Layer', geo_ns)):
		ld = xml_dict(layerInfo)
		# print('Layer #%s: %s\t%s' % (layer_index + 1, ld['Name'], ld['Abstract'])) #, ld['Title']))	
		ids.add(ld['Name'])
	return ids

def layer_locations(xmlres, layer_id):
	capabilities = xmlres.find('opengis:Capability', geo_ns)
	firstlayer = capabilities.find('opengis:Layer', geo_ns)
	for layer_index, layerInfo in enumerate(firstlayer.findall('opengis:Layer', geo_ns)):
		ld = xml_dict(layerInfo)
		if not 'Name' in ld or ld['Name'] != layer_id:
			continue
		#print('found layer #%s: %s\t%s' % (layer_index + 1, ld['Name'], ld['Abstract']))
		locations = set()
		for locationInfo in layerInfo.findall('opengis:CRS', geo_ns):
			#print(locationInfo, locationInfo.text)
			if not locationInfo.text is None:
				locations.add(locationInfo.text)
		bboxes = {}
		for bboxInfo in layerInfo.findall('opengis:BoundingBox', geo_ns):
			if bboxInfo is None or not 'CRS' in bboxInfo.attrib:
				continue
			bboxes[bboxInfo.attrib['CRS']] = bboxInfo.attrib
		return locations, bboxes
	return None	

def encodeURI(uri):
	return urllib.quote(uri, safe='~()*!.\'')

def encode_bbox(bbox):
	#{'minx': '5.75355e+006', 'CRS': 'EPSG:31467', 'maxx': '5.77579e+006', 'maxy': '3.47852e+006', 'miny': '3.45731e+006'}, 'EPSG:31466': {'minx': '5.75589e+006', 'CRS': 'EPSG:31466', 'maxx': '5.77899e+006', 'maxy': '2.68483e+006', 'miny': '2.66272e+006'}, 'EPSG:4326': {'minx': '51.9143', 'CRS': 'EPSG:4326', 'maxx': '52.1154', 'maxy': '8.6868', 'miny': '8.37579'}, 'E
	for key in bbox.keys():
		if key == 'CRS':
			continue
		bbox[key] = float(bbox[key])
	return encodeURI('%f,%f,%f,%f' % (bbox['minx'], bbox['miny'], bbox['maxx'], bbox['maxy']))

htmlP = HTMLParser()
def htmldecode(text):
	text = BeautifulSoup(text, "html.parser").get_text().replace('<br>', " ")
	return replace_entities(htmlP.unescape(text))

def parse_locations(content):
	content = content.strip().split('//Name')
	content.pop(0)
	objstarts = {'oeffnungszeiten': 'aktuellerDatensatz.oeffnungszeiten = ',
		'belegung': 'aktuellerDatensatz.belegung = ',
		'stand': 'aktuellerDatensatz.stand = '}
	location_data = []
	for location_index, locationdata in enumerate(content):
		curloc = {}
		inobj = None
		for locline in map(unicode.strip, filter(lambda l: l.strip() != '', locationdata.split('\n'))):
			if locline.startswith('aktuellerDatensatz.name = "') and locline.endswith('";'):
				curloc['name'] = locline[len('aktuellerDatensatz.name = "'): -2]
				curloc['name'] = htmldecode(curloc['name'])
				#print(curloc['name'])
				continue

			if locline == '};' and not inobj is None:
				inobj = None
				continue
			
			foundnewstart = False
			for objkey in objstarts:
				if locline.startswith(objstarts[objkey]):
					inobj = objkey
					foundnewstart = True
					break
			if foundnewstart:
				continue
			
			if not inobj is None:
				if not inobj in curloc:
					curloc[inobj] = {}
				if locline.startswith('"'):
					locline = locline[1:]
				locline = locline.split('":', 1)
				locline[1] = locline[1].strip()
				if locline[1].endswith(","):
					locline[1] = locline[1][:-1]
				if locline[1].startswith('"') and locline[1].endswith('"'):
					locline[1] = locline[1][1:-1]
				curloc[inobj][locline[0]] = locline[1]
				continue

			#print(inobj, location_index, locline)
				
			if locline == '//-- WERTE ZUWEISEN -------------------------------------':
				break
		#print(location_index, curloc)
		location_data.append(curloc)
	return location_data
			
def location_dump(layer_id, location_id, bbox):
	uri = uris['getfeature']
	uri = uri.replace('%%LAYERID%%', encodeURI(layer_id))
	uri = uri.replace('%%LOCATION%%', encodeURI(location_id))
	uri = uri.replace('%%BBOX%%', encode_bbox(bbox))
	#print('requesting', uri)
	uri_response = requests.get(uri, verify=False)
	#print('response', uri_response)
	return parse_locations(uri_response.content) 

def dump_locdata(loc):
	locname = loc['name']
	locbel = loc['belegung']
	belstr = ''
	belinfo = False
	for key in ['rest', 'kapazitaet']:
		if not key in locbel or locbel[key] is None:
			continue
		locbel[key] = locbel[key].strip()
		if locbel[key] == '':
			continue
		locbel[key] = int(float(locbel[key]))
		belinfo = True
	if belinfo and locbel['kapazitaet'] > 0:
		belstr = '%s/%s frei' % (locbel['rest'], locbel['kapazitaet'])
	
	if belstr != '':
		updd = datetime.datetime.strptime(loc['stand']['pls_zeit'], "%Y-%m-%d-%H.%M.%S.%f" )
		print(locname, belstr, updd)

fixml = getxml(uris['featureindex'])
bboxes = service_dump(fixml)
layer_ids = layer_dump(fixml)

if not 'parken_p' in layer_ids:
	print('did not find endpoint parken_p')
	sys.exit(1)

location_ids, bboxes = layer_locations(fixml, 'parken_p')
#print('parken_p', ', '.join(location_ids), bboxes)

location_data = []
for location_id in location_ids:
	location_data = location_dump('parken_p', location_id, bboxes[location_id])
	break # one location is apparently enough to get all data

for location in location_data:
	dump_locdata(location)
#print(fixml)
#print(ElementTree.tostring(fixml))
