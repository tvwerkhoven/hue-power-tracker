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

1. Per lamp, query brightness, state (=on/off), uniqueid, modelid
2. Per lamp, compute power_min + (brightness*state)**2 * (power_max - power_min)
3. Query last data point from InfluxDB including timestamp
4. Write new energy use point in InfluxDB 

# Calibration

To get brightness to power mapping, I used a Brennenstuhl PM 231 E power meter
with rated power measurement precision of +/-1% or +/-0.2 W. For idle power, 
in some cases I confirmed the meter's linearity by a constant base load of 15W
(incandescent bulb). The results are shown in the below table and graph.

| Type                              | Modelid                        | Brightness (lm) | Rated power (W) | Measured max power (W) | Idle power (W) | Efficiency (lm/W) |
|-----------------------------------|--------------------------------|-----------------|-----------------|------------------------|----------------|-------------------|
| Ikea Trådfri E27                  | TRADFRI bulb E27 W opal 1000lm | 1000            | 12.5            | 12.8                   | 0.3            | 78                |
| Ikea Trådfri E14                  | TRADFRI bulb E14 WS opal 400lm | 400             | 5.3             | 4.4                    | 0.4            | 91                |
| Philips Hue White Ambiance E27    | LTW010                         | 806             | 9               | 6.8                    | 0.3            | 118               |
| Philips Hue White Ambiance E14    | LTW012                         | 470             | 6               | 4.5                    | 0.3            | 104               |
| Philips Hue LightStrip+ (2 meter) | LST002                         | 1600            | 20.5            | 16.7                   | 0.1            | 96                |
| Philips Hue LightStrip+ (4 meter) | LST002                         | 3500            | 43.5            | 23.0                   | 0.1            | 152               |

![Hue and Trådfri brightness to power calibration](https://tweakers.net/ext/f/4WxxyZJZHI44JGXEMJ2fPOxk/full.png)

Note that I have three different lightstrips, one of nominal 2.0m length, one 
of 2.7m, and one of 4.0m length. Surprisingly, the 4.0m version only uses ±40%
more power (instead of expected 100%). This is because the Hue Lighstrip Plus
luminosity is fixed: 2 meter or 10 meter both give 1600 lumen as output, as 
confirmed by the Hue Customer Service. Also, since the PSU is rated at 20W,
and LEDs typically have ±100lm/W efficiency, it follows that the PSU cannot
support more than 2000 lm. The ±900 lumen spec for the 1-meter extension 
strip is only valid in the hypothetical case this extension strip is powered
individually.

After getting brightness to power data, I normalized these and subtracted the
0 brightness (idle) power to get the curves below.

![Hue and Trådfri brightness to normalized power calibration](https://tweakers.net/ext/f/irs4go5hGpgoAtYLNywCJTJu/full.png)

Finally, I fitted the curve (yeah yeah, that's Excel, apologies) to get a
calibration curve for all lights. I could have made a curve per bulb, but
didn't feel this was worth the trouble.

![Hue and Trådfri brightness to normalized power calibration with polynomial fit](https://tweakers.net/ext/f/n7Db3DPovU1tHmgI01QSX7Eu/full.png)

Although I expected an exponential response curve due to eyesight behaving
logarithmically, it turns out the response is quadratic. For simplicity I
ignored the 0.8 factor and the linear component of the response.
