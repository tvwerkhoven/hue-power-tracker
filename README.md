# Hue Power Tracker
Track power usage of your Hue/Innr/Trådfri bulbs. Query brightness data for lights from Philips Hue bridge, then convert to real power, optionally pushing data to InfluxDB.

# About

Measure and store Hue (or compatible) energy usage and store this in InfluxDB.
We get the brightness for each bulb from the Hue bridge, which we convert to power via
calibrated curves (quadratic), taking idle power into account (±0.1-0.4W).
By multiplying power with duration since last measurement, we get energy.

# Usage

1. Calibrate all light types you have, store in `hue_power_min_max` dict
2. For lightstrips/plugs, or other variable lights, add a multiplication factor to the `hue_multiplier` dict
3. Install as crontab, run every ±minute.

# Method

1. Per lamp, query brightness, state, uniqueid, modelid
2. Per lamp, compute power_min + (brightness*state)**2 * (power_max - power_min)
3. Query last data point from InfluxDB including timestamp
4. Write new energy use point in InfluxDB 

# Calibration

To get brightness to power mapping, I used a Brennenstuhl PM 231 E power meter
with rated power measurement precision of +/-1% or +/-0.2 W. For idle power, 
in some cases I confirmed the meter's linearity by a constant base load of 15W
(incandescent bulb). The results are shown below.

![Hue and Trådfri brightness to power calibration](https://raw.githubusercontent.com/tvwerkhoven/hue-power-tracker/master/hue_calib_response.png)

Note that I have three different lightstrips, one of nominal 2.0m length, one 
of 2.7m, and one of 4.0m length. Surprisingly, the 4.0m version only uses ±40%
more power (instead of expected 100%). It could be that the adapter/driver is 
overspec'ed for only 2m strips (since they can drive up to 10m), and therefore
become more efficient at higher loads.

After getting brightness to power data, I normalized these and subtracted the
0 brightness (idle) power to get the curves below.

![Hue and Trådfri brightness to normalized power calibration](https://raw.githubusercontent.com/tvwerkhoven/hue-power-tracker/master/hue_calib_response_norm_col.png)

Finally, I fitted the curve (yeah yeah, that's Excel, apologies) to get a
calibration curve for all lights. I could have made a curve per bulb, but
didn't feel this was worth the trouble.

![Hue and Trådfri brightness to normalized power calibration with polynomial fit](https://raw.githubusercontent.com/tvwerkhoven/hue-power-tracker/master/hue_calib_response_norm_fit.png)

Although I expected an exponential response curve due to eyesight behaving
logarithmically, it turns out the response is quadratic. For simplicity I
ignored the 0.8 factor and the linear component of the response.
