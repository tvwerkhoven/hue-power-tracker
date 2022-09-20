#!/usr/bin/env python3

from phue import Bridge
import requests
import datetime
import json
import logging
import logging.handlers
import yaml
import os, sys

# Init logger
# https://docs.python.org/3/howto/logging.html#configuring-logging
my_logger = logging.getLogger("MyLogger")
my_logger.setLevel(logging.DEBUG)

# create console handler and set level to debug
handler_stream = logging.StreamHandler()
handler_stream.setLevel(logging.DEBUG)
my_logger.addHandler(handler_stream)

# create syslog handler which also shows filename in log
handler_syslog = logging.handlers.SysLogHandler(address = '/dev/log')
formatter = logging.Formatter('%(filename)s: %(message)s')
handler_syslog.setFormatter(formatter)
handler_syslog.setLevel(logging.INFO)
my_logger.addHandler(handler_syslog)

my_logger.info("Starting hue_worker...")

# Power usage per model, both (empirical) max as well as min (idle) power
hue_model_power_min_max = {
	'TRADFRI bulb E27 W opal 1000lm': [12.8, 0.3], # [calibrated]
	'TRADFRI bulb E14 WS opal 400lm': [4.4, 0.4], # [calibrated]
	'TRADFRI bulb GU10 W 400lm': [4.4, 0.4], # guesstimate based on TRADFRI bulb E14 WS opal 400lm
	'LTW010': [6.8, 0.3], # Hue White Ambiance E27 [rated 8xxlm @ 9W, calibrated]
	'LTW012': [4.5, 0.27], # Hue White Ambiance E14 [rated 470lm @ 6W, calibrated]
	'LTW013': [4.5, 0.25], # Hue White ambiance GU10 [rated 250lm @ 6W], guesstimate based on LTW012
	'LWA009': [16,  0.3], # Hue White E27 1600 lumen [rated 1600lm @ 16W], guesstimate based on LTW010
	'LTA001': [9,   0.3], # Hue White E27 with Bluetooth [rated 806lm @ 9W], guesstimate based on LTW010
	'LTE002': [4.5, 0.3], # Hue White Ambiance E14 w/ BT [rated ?? @ ?W], guesstimate based on LTW012
	'LTG002': [4.5, 0.25], # Hue White ambiance GU10 with BT [rated 350lm @ 5W], guesstimate based on LTW012
	'LST002': [16.7, 0.1], # Hue Lightstrip Plus [rated 1600lm @ 20W (max), calibrated]
	'LTC015': [55, 0.2], # Hue Aurelle Rectangle Panel Light 30x120cm [guesstimate]
	'SP 120': [0.4, 0.4], # innr SP 120 [calibrated]
	'Plug 01': [0.4, 0.4] # Osram Smart+ [calibrated]
	}

# Load config from same dir as file. hacky? yes.
# https://www.tutorialspoint.com/How-to-open-a-file-in-the-same-directory-as-a-Python-script
with open(os.path.join(sys.path[0], "config.yaml"), 'r') as stream:
	try:
		data = yaml.safe_load(stream)
		INFLUX_WRITE_URI = data['hue_worker']['influx_write_uri'] # e.g. "http://localhost:8086/write?db=smarthome&precision=s"
		INFLUX_QUERY_URI = data['hue_worker']['influx_query_uri'] # e.g. "http://localhost:8086/query?db=smarthome"
		HUE_BRIDGE_IP = data['hue_worker']['hue_bridge_ip']
		# Use if you want to store raw brightness for each device, or set to None to skip
		INFLUX_QUERY_RAW = None # e.g. "hue,light={},model={} bri={}" 
		INFLUX_QUERY_GET = data['hue_worker']['influx_query_get'] # e.g. "select huelights from energy order by desc limit 1"
		INFLUX_QUERY_SET = data['hue_worker']['influx_query_set'] # e.g. "energy huelights={:.0f}"

		# For some specific Hue apparati we specift precise loads. E.g. lightstrips
		# can be extended, and on/off switches should have loads connected to them.
		# Set these device-specific max powers here.
		hue_lamp_power_max = {
			# '3b5d20': 5.7, # 'Plug 01' On/Off plug -- full load 5.7W (plug + device)
			# '20d2d8': 23, # 'Lightstrip', 4m = 40% extra power wrt 2m (no really)
			}
		hue_lamp_power_max = data['hue_worker']['hue_lamp_power_max']
	except yaml.YAMLError as exc:
		my_logger.exception('Could not load yaml file')


b = Bridge(HUE_BRIDGE_IP)
# If the app is not registered and the button is not pressed, press the button and call connect() (this only needs to be run a single time)
b.connect()

# API exposes all properties, including modelid required for power usage
hapi = b.get_api()

# Get last 6 digits of uniqueid as key to store, along with brightness.
# Multiply with on/off state because brightness is also non-zero if off.
lights = [(v['uniqueid'][-11:-3].replace(':',''), v['modelid'], v['state']['on']*v['state'].get('bri',254)) for v in hapi['lights'].values()]

### Store raw brightness data

if (INFLUX_QUERY_RAW):
	# Build query of all lights in one go, each separated by a newline, such that
	# we can group all data in one HTTP request
	query = "\n".join(["hue,light={},model={} bri={}".format(*light) for light in lights])

	# Store to influxdb as "hue,light=ID bri=VAL". This fails on connection error, 
	# which is OK because then the rest of the script is useless
	r = requests.post(INFLUX_WRITE_URI, data=query, timeout=5)
	# except requests.exceptions.ConnectionError: print("Failed to connect, continuing")

### Store power usage

# 1. Calculate total current power. We take normalized brightness (lbri/254), 
# then scale quadratically to convert to power.
totalpower = 0
for (lid, lmodelid, lbri) in lights:
	try:
		power_max, power_min = hue_model_power_min_max[lmodelid]
		thispower = power_min + ((lbri/254)**2.0)*(hue_lamp_power_max.get(lid,power_max)-power_min)
		totalpower += thispower
		my_logger.debug("lid={}, power={} min={}, bri={}, max={}, lampmax={}".format(lid, thispower, power_min, lbri/254, power_max, hue_lamp_power_max.get(lid,1)))
	except:
		my_logger.exception('Unknown Zigbee model id')
 
# Get last entry of huelights as reference, use time delta to calculate energy usage
r = requests.post(INFLUX_QUERY_URI, data={'q': INFLUX_QUERY_GET}, timeout=5)

# If data is OK, continue, else fail
if (r.status_code == 200):
	resp = json.loads(r.text)
	
	# Check if we have results, if not we keep default 0
	lastduration = lastenergy = 0
	respseries = resp['results'][0].get('series',[])
	if (len(respseries)):
		# Get first value of first series of first result. Lasttimestr is like 2019-08-02T22:42:43+02:00
		lasttimestr = respseries[0]['values'][0][0]
		lastenergy = respseries[0]['values'][0][-1]
		# In python3.7 we could use %z to parse TZ info. Since influxdb will 
		# return UTC, we add this timezone manually for 3.5/3.6 compatibility.
		lasttime = datetime.datetime.strptime(lasttimestr, "%Y-%m-%dT%H:%M:%SZ")
		lasttime = lasttime.replace(tzinfo=datetime.timezone.utc)
		lastduration = (datetime.datetime.now(tz=lasttime.tzinfo) - lasttime).seconds

	my_logger.debug("Last hue energy was {}, current power is {}, duration since last: {}".format(lastenergy, totalpower,lastduration))

	# 3. Calculate energy use, add to previous entry, store to influx
	query = INFLUX_QUERY_SET.format(lastenergy + totalpower*lastduration)
	r = requests.post(INFLUX_WRITE_URI, data=query, timeout=5)
	if (r.status_code != 204):
		my_logger.error("Push to influxdb failed: {} - {}".format(str(r.status_code), str(r.text)))
else:
	my_logger.error("Could not retrieve last hue power load from database: {} - {}".format(str(r.status_code), str(r.text)))

