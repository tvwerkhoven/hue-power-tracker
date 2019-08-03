# hue-power-tracker
Track power usage of your Hue/Innr/Trådfri bulbs. Query brightness data for lights from Philips Hue bridge, then convert to real power, optionally pushing data to InfluxDB.

# About
Measure and Hue energy usage and store this in InfluxDB. We get the 
brightness for each bulb from the Hue bridge, which we convert to power via
calibrated curves (quadratic), taking idle power into account (±0.1-0.4W).
By multiplying power with duration since last measurement, we get energy.

# # Usage

Install as crontab, run every ±minute.

# Method

1. Per lamp, query brightness, state, uniqueid, modelid
2. Per lamp, compute power_min + (brightness*state)**2 * (power_max - power_min)
3. Query last data point from InfluxDB including timestamp
4. Write new energy use point in InfluxDB 
