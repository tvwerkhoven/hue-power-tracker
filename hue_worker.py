#!/usr/bin/env python3

from phue import Bridge
import requests
import datetime
import json

# Influxdb/Hue bridge settings URI
INFLUX_WRITE_URI="http://localhost:8086/write?db=smarthome&precision=s"
INFLUX_QUERY_URI="http://localhost:8086/query?db=smarthome"

# Queries to get last huelights energy and
#INFLUX_QUERY_RAW="hue,light={},model={} bri={}" # Use if you want to store raw brightness for each device, or set to None to skip
INFLUX_QUERY_RAW=None
INFLUX_QUERY_GET="select huelights from energy order by desc limit 1"
INFLUX_QUERY_SET="energy huelights={:.0f}"

HUE_BRIDGE_IP='172.16.0.1'

# Power usage per model, both (empirical) max as well as min (idle) power
hue_power_min_max = {
	'TRADFRI bulb E27 W opal 1000lm': [12.8, 0.3],
	'TRADFRI bulb E14 WS opal 400lm': [4.4, 0.4],
	'TRADFRI bulb GU10 W 400lm': [4.4, 0.4], # guesstimate based on TRADFRI bulb E14 WS opal 400lm
	'LTW010': [6.8, 0.3],
	'LTW012': [4.5, 0.27],
	'LTW013': [4.5, 0.25], # guesstimate based on LTW012
	'LST002': [16.7, 0.1],
	'Plug 01': [1.0+0.4, 0.4] # hacky: set max to 1+min to ensure scaling with multiplier works
	}

# For some Hue apparati we need to know the multiplier. E.g. lightstrips can 
# be extended, and on/off switches should have the power connected to them.
# Minimum power is not affected by multiplier because it remains one device. 
hue_multiplier = {
	'3b5d20': 5.7-0.4, # 'On/Off plug' -- full load 5.7W (plug + device)
	'20d2d8': 1.4, # 'Lightstrip', 4m = 40% extra power wrt 2m (no really)
	}

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
	power_max, power_min = hue_power_min_max[lmodelid]
	thispower = power_min + ((lbri/254)**2.0)*(power_max-power_min)*hue_multiplier.get(lid,1)
	totalpower += thispower
	print("lid={}, power={} min={}, bri={}, max={}, mult={}".format(lid, thispower, power_min, lbri/254, power_max, hue_multiplier.get(lid,1)))
 
# Get last entry of huelights as reference, use time delta to calculate energy usage
r = requests.post(INFLUX_QUERY_URI, data={'q': INFLUX_QUERY_GET}, timeout=5)

# If data is OK, continue, else fail
if (r.ok and r.status_code == 200):
	resp = json.loads(r.text)
	
	# Check if we have results, if not we keep default 0
	lastduration = lastenergy = 0
	respseries = resp['results'][0].get('series',[])
	if (len(respseries)):
		# Get first value of first series of first result. Lasttimestr is like 2019-08-02T22:42:43+02:00
		lasttimestr, lastenergy = respseries[0]['values'][0]
		# In python3.7 we could use %z to parse TZ info. Since influxdb will 
		# return UTC, we add this timezone manually for 3.5/3.6 compatibility.
		lasttime = datetime.datetime.strptime(lasttimestr, "%Y-%m-%dT%H:%M:%SZ")
		lasttime = lasttime.replace(tzinfo=datetime.timezone.utc)
		lastduration = (datetime.datetime.now(tz=lasttime.tzinfo) - lasttime).seconds

	# 3. Calculate energy use, add to previous entry, store to influx
	query = INFLUX_QUERY_SET.format(lastenergy + totalpower*lastduration)
	r = requests.post(INFLUX_WRITE_URI, data=query, timeout=5)
