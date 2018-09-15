#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Raspiled - LED strip light control from Raspberry Pi!

    SM5050 (tricolour LED chips) wavelengths:
        Red = 625nm
        Green = 523nm
        Blue = 468nm

    @author: Dr Mike Brooks
    @Coathor : Josue Martinez Moreno
"""
from __future__ import unicode_literals

from named_colours import NAMED_COLOURS

import copy
import pigpio
import re
import time
from time import sleep
import threading
import subprocess
import logging
import schedule
import os
import signal
from multiprocessing import Process
logging.basicConfig(format='[%(asctime)s RASPILED] %(message)s',
                            datefmt='%H:%M:%S',level=logging.INFO)

#Python version safe importing of HTML parser
try:
    # Python 2.6-2.7 
    from HTMLParser import HTMLParser
    html_parser = HTMLParser()
except ImportError:
    # Python 3-3.3
    try:
        from html.parser import HTMLParser
        html_parser = HTMLParser()
    except ImportError:
        # Python 3.4
        import html
        html_parser = html

##### Constants #####

NO_CALIBRATION = {  #RGB multipliers when var -> light
    "r" : 1.0,
    "g" : 1.0,
    "b" : 1.0
}
AUTO_CALIBRATE = {  #RGB multipliers when var -> light
    "r" : 1.0,
    "g" : 0.63, #Green is usually a bit brighter!
    "b" : 1.0
}
PIN_MODE = "BCM" #Broadcom mode

PWM_MAX = 255.0
PWM_MIN = 0.0

#####################


#pigpio_interface = pigpio.pi("192.168.0.33",8888) #We use ONE class instance
def pigpiod_process():
    cmd='pgrep pigpiod'

    process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()

    if output=='':
        logging.warn('*** [STARTING PIGPIOD] i.e. "sudo pigpiod" ***') 
        cmd='sudo pigpiod'
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
        output, error = process.communicate()
    else:
        logging.info('PIGPIOD is running! PID: %s' % output.split('\n')[0]) 

pigpiod_process()

class PiPinInterface(pigpio.pi, object):
    """
    Represents an interface to the pins on ONE Raspberry Pi. This is a lightweight python wrapper around
    pigpio.pi.
    
    Create a new instance for every Raspberry Pi you wish to connect to. Normally we'll stick with one (localhost)
    """
    
    def __init__(self, params):
        super(PiPinInterface, self).__init__(params['pi_host'], params['pig_port'])
    
    def __unicode__(self):
        """
        Says who I am!
        """
        status = "DISCONNECTED"
        if self.connected:
            status = "CONNECTED!"
        return "RaspberryPi Pins @ {ipv4}:{port}... {status}".format(ipv4=self._host, port=self._port, status=status)
    
    def __repr__(self):
        return str(self.__unicode__()) 


class LEDStrip(object):
    """
    Represents an LED strip
    """
    #Runtime vars
    r = 0.0 #Current value of red channel
    g = 0.0 #Current value of green channel
    b = 0.0 #Current value of blue channel
    colour = (0,0,0) #Tuple expressing the current colour (0-255)
    iface = None
    _sequence = None #The current sequence we are running
    _sequence_stop_signal = False #Whether to stop a sequence or not
    
    def __init__(self, params, calibrate=None, interface=None):
        """
        Initialises the lights
        
        @param red_pin: <int> The pin which controls red LEDs
        @param green_pin: <int> The pin which controls green LEDs
        @param blue_pin: <int> The pin which controls blue LEDs
        @keyword calibrate: {} dict of channel letter : multiplier
        @keyword inteface: <PiPinInterface> The RaspberryPi hardware we're talking to!
        """
        #Resolve interface - create if not provided!
        need_to_generate_new_interface = False #Flag to see what we're doing
        if interface is None: 
            need_to_generate_new_interface = True
        else: #Check the interface is connected!
            try:
                iface_host = interface._host
            except AttributeError:
                iface_host = None
            if iface_host is None:
                need_to_generate_new_interface = True
                logging.info("No existing iface host")
            elif pi_host and unicode(pi_host) != unicode(iface_host):
                need_to_generate_new_interface = True
                logging.info("iface host different to intended: iface=%s vs pi=%s" % (iface_host, pig_host))
            try:
                iface_port = interface._port
            except AttributeError:
                iface_port = None
                logging.info("iface port different to intended: iface=%s vs pi=%s" % (iface_port, pig_port))
            if iface_port is None:
                need_to_generate_new_interface = True
            elif pig_port and unicode(pig_port) != unicode(iface_port):
                need_to_generate_new_interface = True
            try:
                iface_connected = interface.connected
            except AttributeError:
                iface_connected = False
            if not iface_connected:
                logging.info("iface not connected!")
                need_to_generate_new_interface = True
        if need_to_generate_new_interface:
            self.iface = self.generate_new_interface(params)
        else:
            self.iface = interface
        
        #Set vars
        if calibrate is None:
            calibrate = copy.copy(AUTO_CALIBRATE) #Don't pollute global mutable!
        self._calibrate = calibrate #Whether to adjust for differing RGB light intensities (green is brighter)
        self._red_pin = params['red_pin']
        self._green_pin = params['green_pin']
        self._blue_pin = params['blue_pin']
        
        self.p_alarm = []
        #self._red_pin = self.pin_lim(red_pin) 
        #self._green_pin = self.pin_lim(green_pin)
        #self._blue_pin = self.pin_lim(blue_pin)
        
        #Initialise strip... it may already be alive!
        self.sync_channels() #Sets internal channels to match the values of the actual pins
    
    @classmethod
    def lim(cls, lower=PWM_MIN, upper=PWM_MAX, value=None, less_than_lower_default=None, greater_than_upper_default=None):
        """
        Checks that the value specified is between the given values, or returns default
        """
        #Sanitise inputs
        if less_than_lower_default is None:
            less_than_lower_default = lower
        if greater_than_upper_default is None:
            greater_than_upper_default = upper
        if not (less_than_lower_default >= lower and greater_than_upper_default <= upper):
            raise Exception("LEDStrip.lim(): Defaults %s,%s are not within %s - %s" % (less_than_lower_default, greater_than_upper_default, lower, upper))  
        if value is None:
            return less_than_lower_default
        
        #Test values
        try:
            if value < lower:
                logging.warn(" LEDStrip.lim(): Value %s is less than lower limit %s. Setting to %s." % (value, lower, less_than_lower_default))
                return float(less_than_lower_default)
            if value > upper:
                logging.warn(" LEDStrip.lim(): Value %s is greater than upper limit %s. Setting to %s" % (value, upper, greater_than_upper_default))
                return float(greater_than_upper_default)
        except (ValueError, TypeError, AttributeError):
            return float(less_than_lower_default)
        return float(value)
    
    @classmethod
    def int_lim(cls, lower=PWM_MIN, upper=PWM_MAX, value=None, less_than_lower_default=None, greater_than_upper_default=None):
        """
        Checks that the value specified is between the given values, or returns default. Always an integer.
        """
        out_float = cls.lim(lower, upper, value, less_than_lower_default, greater_than_upper_default)
        return int(round(out_float))
    
    @classmethod
    def pin_lim(cls, value):
        """
        Checks that the pin specified is between valid ranges
        """
        return cls.int_lim(lower=0, upper=27, value=value, less_than_lower_default=27, greater_than_upper_default=27)
    
    @classmethod
    def hex_to_rgb(cls, hex_value):
        """
        Converts a hex string into RGB tuple
        """
        hex_value = hex_value.lstrip("#")
        r,g,b = tuple(int(hex_value[i:i+2], 16) for i in (0, 2 ,4))
        return (r,g,b)
    
    @classmethod
    def rgb_to_hex(cls, r, g, b):
        """
        Converts red / green / blue integers to hex string
        """
        return '#%02x%02x%02x' % (int(r), int(g), int(b))
    
    RE_COLOUR_RGB = re.compile(r"rgb\(([0-9]{1,3}),\s?([0-9]{1,3}),\s?([0-9]{1,3})", re.IGNORECASE)
    RE_COLOUR_HEX_6 = re.compile(r'^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$')
    RE_COLOUR_HEX_3 = re.compile(r'^#?([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])$')
    
    @classmethod
    def colour_to_rgb_tuple(cls, col_str):
        """
        Converts a colour string to an RGB tuple
        
        @param col_str: <str> a hex or RGB html colour
        
        @return: <tuple> (r,g,b) component values converted into base 10 integers in range (0-255)
        """
        hex_6 = cls.RE_COLOUR_HEX_6.search(col_str)
        if hex_6:
            #Simply converts hex directly to dec 
            return tuple(int(c,16) for c in hex_6.groups())
        hex_3 = cls.RE_COLOUR_HEX_3.search(col_str)
        if hex_3:
            #First must convert single value range 0-15 to range 0-255 
            return tuple(int(int(c,16)/15.0*255.0) for c in hex_3.groups())
        rgb = cls.RE_COLOUR_RGB.search(col_str)
        if rgb:
            return tuple(int(c) for c in rgb.groups()) #Direct output of tuple from regex!
        return None #Otherwise canny do i' captain
    
    @classmethod
    def contrast_from_bg(cls, col="#000000", dark_default="000000", light_default="FFFFFF", hashed="#"):
        """
            Returns a suggested colour for the foreground to make it readable
            over the specified background.
            
            @param col: <str> A colour represented in html 6-digit hex, 3-digit hex, or rgb(r,g,b)
            @keyword dark_default: <str> A colour to set the foreground to for good contrast against a bright background, default = black
            @keyword light_default: <str> A colour to set the foreground to for good contrast against a dark background, default = white
            @keyword hashed: <str> The prefix to slam in front of the output e.g. "#"  
            
            @return: <str> A hex colour for the contrast
        """
        trigger = float(0.45) #Values greater than this result in black text
        if not col:
            return "#000000"    #Default to black
        if col in ("Transparent","transparent"):
            return "#000000"    #Default to black
        if not hashed:
            hashed = ""
        elif hashed is True:
            hashed = "#"
        try:
            col_out = cls.colour_to_rgb_tuple(col)
            r,g,b = col_out
            div = 255.0 #Produces a value between 0-1 as a float
            lum = float(0.2126*pow(r/div, 2.2)) + float(0.7152*pow(g/div, 2.2)) + float(0.0722*pow(b/div, 2.2))
        except (TypeError, ValueError):
            return dark_default
        #logging.info ("Luminosity: %s" % lum)
        #Decision gate:
        if lum >= trigger: #Light background, need dark text
            return "%s%s" % (hashed, dark_default)
        else: #Dark background, need light text
            return "%s%s" % (hashed, light_default)
    
    @classmethod
    def convert_to_colour_list(cls, colours, *args, **kwargs):
        """
        Takes a whole munge of nonsense input, converts it into a list of colours.
        Will split apart comma delimited strings. Will decode HTML chars. Will
        concatenate a mixture of comma strings and items
        """
        colours = copy.deepcopy(colours) #Ensure we don't bugger up original
        if isinstance(colours, (str,unicode)):
            colours = [colours] #Listify
        colours.extend(args)
        intermediate_list = []
        #Add in comma delimited stuff
        for colour_term in colours:
            if isinstance(colour_term, (str,unicode)):
                colour_term_decoded = html_parser.unescape(colour_term) #HTML char decode
                colour_terms_list = colour_term_decoded.split(",")
                intermediate_list.extend(colour_terms_list)
            else:
                intermediate_list.append(colour_term)
        #Now sanitise the list again
        output_list = []
        for colour in intermediate_list:
            if isinstance(colour, (str,unicode)):
                colour_clean = colour.strip()
            output_list.append(colour)
        return output_list
    
    @classmethod
    def clean_time_in_milliseconds(cls, seconds=None, milliseconds=None, default_seconds=1, minimum_milliseconds=200):
        """
        Takes a time expressed in seconds and milliseconds, converts it into a
        integer number of milliseconds
        """
        #Sanitise inputs:
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            seconds = None
        try:
            milliseconds = float(milliseconds)
        except (TypeError, ValueError):
            milliseconds = None
        
        #Resolve total time
        if seconds is None and milliseconds is None:
            out_milliseconds = default_seconds * 1000 #1s
        else:
            seconds = seconds or 0
            milliseconds = milliseconds or 0
            out_milliseconds = seconds*1000 + milliseconds
        
        #Check this isn't stupidly short
        if out_milliseconds < minimum_milliseconds:
            out_milliseconds = minimum_milliseconds
        
        return out_milliseconds
    
    def __unicode__(self):
        """
        Print current colours as unicode
        """
        return "{},{},{}".format(*self.rgb)
    
    def sync_channels(self):
        """
        Sets internal pointers to match actual pin values
        """
        self.r, self.g, self.b = self.read_rgb(decalibrate=False) #We want the RAW values in the self.r|g|b properties!!
        return (self.r, self.g, self.b)
    
    def calibrate_rgb(self, r, g, b):
        """
        Takes the values of RGB and adjusts them to account for visual sensitivity
        """
        new_r = r*self._calibrate["r"] 
        new_g = g*self._calibrate["g"]
        new_b = b*self._calibrate["b"]
        return (new_r,new_g,new_b)
    
    def decalibrate_rgb(self, r, g, b):
        """
        Takes the values of RGB and adjusts them to account for visual sensitivity
        """
        new_r = r/self._calibrate["r"] 
        new_g = g/self._calibrate["g"]
        new_b = b/self._calibrate["b"]
        return (new_r,new_g,new_b)
    
    @property
    def red(self):
        """
        Calibration-adjusted red
        """
        r = self.r
        if self._calibrate:
            r = r/self._calibrate["r"]
        return int(r)
    @property
    def green(self):
        """
        Calibration-adjusted green
        """
        g = self.g
        if self._calibrate:
            g = g/self._calibrate["g"]
        return int(g)
    @property
    def blue(self):
        """
        Calibration-adjusted blue
        """
        b = self.b
        if self._calibrate:
            b = b/self._calibrate["b"]
        return int(b)
    @property
    def rgb(self):
        """
        Calibration-adjusted RGB
        """
        return (self.red, self.green, self.blue)
    
    @property
    def hex(self):
        """
        Calibration-adjusted HEX value
        """
        r, g, b = self.rgb
        return self.rgb_to_hex(r, g, b)
    
    def generate_new_interface(self, params):
        """
        Builds a new interface, stores it in self.iface
        """
        #Kill existing iface
        try:
            self.iface.stop()
        except (AttributeError, IOError):
            pass
        self.iface = PiPinInterface(params)
        return self.iface
    
    def set_led(self, pin, value=0):
        """
        Sets the LED pin to the specified value
        
        @param pin: <int> The pin to change
        @param value: <int> The value to set it to
        """
        value = self.int_lim(lower=PWM_MIN, upper=PWM_MAX, value=value) #Standardise the value to our correct range
        if self.iface.connected:
            try:
                self.iface.set_PWM_dutycycle(pin, value)
            except (AttributeError, IOError):
                logging.error(" Cannot output to pins. PWM of pin #%s would be %s" % (pin,value))
        else:
            logging.error(" Interface not connected. Cannot output to pins. PWM of pin #%s would be %s" % (pin,value))
        return value
    
    def read_led(self, pin):
        """
        Reads the current LED pin value, sets our internal pointer to its value
        
        @param pin: <int> The pin to read 
        """
        value = 0 #Default to nowt
        if self.iface.connected:
            try:
                value = self.iface.get_PWM_dutycycle(pin)
            except (AttributeError, IOError, pigpio.error):
                logging.error(" Cannot read PWM of pin #%s" % (pin,))
        else:
            logging.error(" Interface not connected. Cannot read PWM of pin #%s." % (pin,))
        return value
    
    def read_rgb(self, decalibrate=False):
        """
        Reads the LED pin values (raw values)
        
        @keyword decalibrate: If True, will adjust the values according to calibration weights 
        """
        r = self.read_led(self._red_pin)
        g = self.read_led(self._green_pin)
        b = self.read_led(self._blue_pin)
        if decalibrate:
            r,g,b = self.decalibrate_rgb(r, g, b)
            return int(round(r)),int(round(g)),int(round(b))
        return (r,g,b)        
    
    def set_red(self, value=0, calibrate=True):
        """
        Sets the red LED to value
        """
        if calibrate and self._calibrate:
            value = value * self._calibrate.get("r",1.0) 
        self.r = self.set_led(self._red_pin, value)
        return self.red
    
    def set_green(self, value=0, calibrate=True):
        """
        Sets the green LED to value 
        """
        if calibrate and self._calibrate:
            value = value * self._calibrate.get("g",1.0)
        self.g = self.set_led(self._green_pin, value)
        return self.green
    
    def set_blue(self, value=0, calibrate=True):
        """
        Sets the blue LED to value
        """
        if calibrate and self._calibrate:
            value = value * self._calibrate.get("b",1.0)
        self.b = self.set_led(self._blue_pin, value)
        return self.blue
    
    def set_rgb(self, r=0, g=0, b=0, calibrate=True):
        """
        Sets the LED array to rgb
        @return: (r,g,b)
        """
        r = self.set_red(r)
        g = self.set_green(g)
        b = self.set_blue(b)
        return (r,g,b)
    
    def fade_to_rgb(self, r=0, g=0, b=0, fade=300, check=True):
        """
        Fades to the rgb values over the specified time period (in milliseconds)
        Human perception notices things slower than 50Hz (20ms)
        
        @keyword fade: <float> if provided, will make the colour transition smooth over the specified period of time
        """
        #When we're doing a fade, the pin values may have changed... check first!!
        if check:
            self.sync_channels()
        
        #Now we'll have the correct init values!!!
        init_r = self.red
        init_g = self.green
        init_b = self.blue
        gap_r = r - init_r
        gap_g = g - init_g
        gap_b = b - init_b
        n_steps = int(float(fade)/20.0) #50Hz = 20 milliseconds
        
        for step in xrange(0, n_steps):
            fractional_progress = float(step)/n_steps
            cur_r = init_r + (gap_r*fractional_progress)
            cur_g = init_g + (gap_g*fractional_progress)
            cur_b = init_b + (gap_b*fractional_progress)
            cur_col = self.set_rgb(cur_r,cur_g,cur_b)
            sleep(0.02) #20ms
            if self._sequence and self._sequence_stop_signal: #Instantly escape the fade if changing routine
                break 
        
        #And fix it to the target in case float calcs put us off a bit
        return self.set_rgb(r,g,b)
    
    def set_hex(self, hex_value="#000000", fade=False, check=True):
        """
        Turns a hex string into a tuple of 255,255,255
        """
        r,g,b = self.hex_to_rgb(hex_value)
        if fade:
            out = self.fade_to_rgb(r, g, b, fade=fade, check=check)
        else:
            out = self.set_rgb(r, g, b)
        return self.rgb_to_hex(*out)
    
    def set(self, r=None, g=None, b=None, hex_value=None, name=None, fade=False, check=True):
        """
        Sets the LEDs to the specified colour
        Can provide an RGB tuple, RGB separately
        
        @keyword fade: <float> if provided, will make the colour transition smooth over the specified period of time
        """
        #Has a named colour been provided?
        if r and g is None and b is None and name is None:
            name = r
        try:
            hex_value = NAMED_COLOURS[unicode(name).lower()]
        except KeyError:
            pass
        else:
            return self.set_hex(hex_value, fade=fade, check=check)
        
        #Has a hex value been provided?
        if r and g is None and b is None and hex_value is None:
            hex_value = r
        if unicode(hex_value)[0] != "#":
            hex_value = "#%s" % hex_value
        if len(unicode(hex_value))>=4:
            try:
                return self.set_hex(hex_value, fade=fade, check=check)
            except ValueError:
                pass
        
        #Has a tuple been provided, or comma string?
        if r and isinstance(r, (tuple,list)):
            r, g, b = r #Unpack
        else:
            try:
                r,g,b = unicode(r).split(",",3)
            except ValueError:
                pass
        try:
            r = int(r)
            g = int(g)
            b = int(b)
        except (ValueError, TypeError):
            logging.info("WARNING: no colour identified by '%s'. Using current colour." % r)
            return self.rgb
        
        if fade:
            return self.fade_to_rgb(r,g,b, fade=fade, check=check)
        else:
            return self.set_rgb(r,g,b)
    
    def fade(self, r=None, g=None, b=None, hex_value=None, name=None, fade_time=300, check=True):
        """
        Fades to the specified colour
        """
        return self.set(r, g, b, hex_value, name, fade=fade_time, check=check)
        
    def off(self, *args, **kwargs):
        """
        Fades all channels off
        """
        self.stop_current_sequence()
        return self.fade(0,0,0)
    
    def stop(self, *args, **kwargs):
        """
        Stops current sequence
        """
        self.stop_current_sequence()
        return self.sync_channels()
    
    def fast_off(self, *args, **kwargs):
        """
        Turns all channels off
        """
        return self.set(0,0,0,fade=False)
    
    def set_calibrate(self, calibrate=None, *args, **kwargs):
        """
        Sets the calibration rules
        """
        calibrate = calibrate or self._calibrate or {}
        calibrate = copy.copy(calibrate)
        calibrate.update(kwargs)
        if calibrate is None: #Use auto
            calibrate = copy.copy(AUTO_CALIBRATE)
        self._calibrate = calibrate
        logging.info("Calibration updated! %s" % self._calibrate)
    set_calibration = set_calibrate
    calibrate = set_calibrate
    
    def calibrate_off(self):
        """
        Turns calibration OFF
        """
        self._calibrate = copy.copy(AUTO_CALIBRATION)
        logging.info("Calibration off! %s" % self._calibrate)
    set_calibrate_off = calibrate_off
    set_calibration_off = calibrate_off
    calibration_off = calibrate_off
    
    ### Sequences ###
    """
    Sequences run inside a separate thread so that they do not block the web client
    from returning a page. They should always be called via run_sequence, because
    this ensures that a 
    """
    def sleep(self, seconds):
        """
        A smarter version of sleep, where we check the exit flag each loop
        Minimum units of 10ms
        """
        ten_ms_steps = int(round(seconds * 100))
        for _i in xrange(0,ten_ms_steps):
            if self._sequence_stop_signal:
                break
            sleep(0.01)
        
    def run_sequence(self, func, *args, **kwargs):
        """
        Initiates a sequence in a separate non-blocking thread.
        Ensures any existing sequences are killed
        
        @param sequence: Method on LEDStrip to run
        @args @kwargs: passed to sequence.run() on calling sequence.start()
        """
        self.stop_current_sequence()
        self._sequence = threading.Thread(target=func, args=args, kwargs=kwargs)
        self._sequence_stop_signal = False
        self._sequence.start()
        return self.rgb

    def stop_current_sequence(self, timeout=60):
        """
        Stops the current sequence by issuing a stop flag to the sequence thread then joining it
        until it unblocks
        
        @param timeout: <int>/<float> seconds to wait before killing thread 
        """
        self._sequence_stop_signal=True
        try:
            self._sequence._sequence_stop_signal = True #In case the sequence is pointing to a different signal
            self._sequence.join(timeout) #We'll wait timeout seconds for the thread to stop
        except AttributeError:
            pass
        self._sequence = None #Unset the current sequence
        return self.rgb
    
    def teardown(self):
        """
        Nukes any remaining threads. Called when the parent reactor loop stops
        """
        logging.info("\tLEDstrip: exiting sequence threads...")
        self.off() #Stops all sequences and fades to black
        self.teardown_alarm()
        logging.info("\t\t...done")
    
    def teardown_alarm(self):
        if self.p_alarm!=[]:
              [os.kill(p.pid, signal.SIGKILL) for p in self.p_alarm]
       
    def _colour_loop(self, colours, seconds=None, milliseconds=None, fade=True):
        """
        Loops around the specified colours, changing colour every n seconds or m milliseconds
        
        @param colours: [] A list of named / hex / RGB colours to loop around
        @keyword fade: <boolean> Whether to jump (False) or fade (True)
        """
        colours = self.convert_to_colour_list(colours) #Forces a list of colours into an actual python list
        if len(colours)<2:
            colours.append("#000000") #Blink between black and the specified colour if only one provided
        
        #Start with the first colour immediately:
        if fade:
            self.fade(colours[0])
        else:
            self.set(colours[0])
        step_time = self.clean_time_in_milliseconds(seconds, milliseconds, default_seconds=1, minimum_milliseconds=50)
        
        #Do the loop
        i = 1 #We're moving to the second colour now
        total_colours = len(colours)
        while not self._sequence_stop_signal:
            #Resolve our colour
            next_colour = colours[i]
            i = (i+1) % total_colours #ensures we are never asking for more colours than provided
            if fade: #Fading is a blocking process, thus we let the fade loop use up the time
                _latest_colour = self.fade(next_colour, fade_time=step_time, check=False)
            else: #Set is instant, so we need to consume the step time
                _latest_colour = self.set(next_colour, fade=False, check=False)
                self.sleep(step_time/1000) #NB fade uses milliseconds!!
        #Return the latest colour
        return self.sync_channels()
    
    def jump(self, colours, seconds=None, milliseconds=None):
        """
        Jumps between the specified colours every time interval
        """
        return self.run_sequence(self._colour_loop, colours=colours, seconds=seconds, milliseconds=milliseconds, fade=False)
    blink = jump #Alias
    
    def rotate(self, colours, seconds=None, milliseconds=None):
        """
        Rotates (fades) between the specified colours every time interval
        """
        return self.run_sequence(self._colour_loop, colours=colours, seconds=seconds, milliseconds=milliseconds, fade=True)
    rot = rotate #Alias
    huerot = rotate #Alias
    
    def _sunrise_sunset(self, seconds=None, milliseconds=None, hour=None, freq=None, temp_start=None, temp_end=None, setting=True):
        """
        Silly routine to emulate a sunset
        
        If:  step_time = 100 + f(z)/(65-x)
        
        Then the area under the curve needs to be our target time
        
            target_time = 100x - z*log(x-65)
        
        We have 60 steps, so we can apply limits on x (0 to 60). We end up with:
        
            z = (target_time - 6000) / log(65)-log(5) = (target_time - 6000) / 2.564949357

        @keyword seconds: <float> Number of seconds to do the sequence over
        @keyword milliseconds: <float> Number of milliseconds to do the sequence over, gets added to seconds if both provided
        @keyword temp_start: <unicode> A colour temperature (in Kelvin) to start the sequence from
        @keyword temp_end: <unicode> A colour temperature (in Kelvin) to end the sequence at
        @keyword fade: <Boolean> whether to fade between steps (True) or jump (False)
        """
        FUDGE_FACTOR = 0.86
        if hour==None:
            # Work out what the defaults should be
            ## MOVE IT INSIDE THE Override values.
            t0 = temp_start.split('K')[0]
            t1 = temp_end.split('K')[0]
            if t0 > t1:
                temp_step = -100
                x_start = 0
                x_step_amount = 1
            else:
                temp_step = 100
                x_start = 60
                x_step_amount = -1
            temp_0 = int(t0)
            temp_n = int(t1)
            # You can override these defaults if either temp_start or temp_end is set
            if temp_start:
                try:
                    _exists = NAMED_COLOURS[temp_start.lower()]
                except (TypeError,ValueError):  # Means the starting temp has NOT been provided, use default
                    pass
                except KeyError:
                    logging.warning("Sunrise/sunset: Your starting colour temperature '{}' is not a valid colour temperature".format(temp_start))
            if temp_end:
                try:
                    _exists = NAMED_COLOURS[temp_end.lower()]
                except (TypeError, ValueError):  # Means the ending temp has NOT been provided, use default
                    pass
                except KeyError:
                    logging.warning("Sunrise/sunset: Your ending colour temperature '{}' is not a valid colour temperature".format(temp_end))

            #Add in a fudge factor to cater for CPU doing other things:
            #Calculate our z scaling factor:
            target_time = self.clean_time_in_milliseconds(seconds, milliseconds, default_seconds=1, minimum_milliseconds=1000)
            z_factor = (target_time*FUDGE_FACTOR) / 2.564949357
            x_step = x_start
            #And run the loop
            t1 = time.time()
            check = True #We only check the current values on the first run
            for temp in xrange(temp_0,temp_n,temp_step):
                if self._sequence_stop_signal: #Bail if sequence should stop
                    return None
                k = u"%sk" % temp
                self.fade(k, fade_time=((100+z_factor)/(65-x_step)), check=check) #ms, slows down as sunset progresses
                x_step += x_step_amount
                check=False
            t2 = time.time()
            logging.info("%ss, target=%ss" % ((t2-t1),target_time/1000.0))
        else:
            temp_0=temp_start[0].split('K')[0]
	    temp_n=temp_end[0].split('K')[0]
            if self.p_alarm != []:
                self.teardown_alarm()
            process_alarm=[]
            for tt in range(0,len(hour)):
                milliseconds=0
                proc_hour=hour[tt]
		alarm_arg=(proc_hour,temp_0,temp_n,FUDGE_FACTOR,freq,seconds[tt],milliseconds)
                
                process_alarm.append(Process(target=self.schedule_alarm,args=alarm_arg))
            [pp.start() for pp in process_alarm] # Start processes in the background which contain the schedule of the alarm
            self.p_alarm=process_alarm


    def alarm(self, seconds=None, milliseconds=None, hour=None, freq=None, temp_start=None, temp_end=None):
        """
        Emulates a sunset
        """
        return self.run_sequence(self._sunrise_sunset, seconds=seconds, milliseconds=milliseconds, hour=hour, freq=freq, temp_start=temp_start, temp_end=temp_end)

    def daily_alarm(self,hour=None,t_0=None,t_1=None,fudge_factor=None,freq=None,seconds=None,milliseconds=None):
        if t_0 > t_1:
            temp_step = -100
            x_start = 0
            x_step_amount = 1
        else:
            temp_step = 100
            x_start = 60
            x_step_amount = -1
        temp_0 = int(t_0)
        temp_n = int(t_1)
        #Add in a fudge factor to cater for CPU doing other things:
        FUDGE_FACTOR = 0.86 #i.e we expect the routine to take 12% longer than the target time
        
        #Calculate our z scaling factor:
        target_time = self.clean_time_in_milliseconds(seconds, milliseconds, default_seconds=1, minimum_milliseconds=1000)
        z_factor = (target_time*fudge_factor) / 2.564949357
        x_step = x_start
        t1 = time.time()

        logging.info('Alarm running at {}'.format(hour))
        #And run the loop
        check = True #We only check the current values on the first run
        for temp in xrange(temp_0,temp_n,temp_step):
             if self._sequence_stop_signal: #Bail if sequence should stop
                 return None
             k = u"%sk" % temp
             self.fade(k, fade_time=2*((100+z_factor)/(65-x_step)), check=check) #ms, slows down as sunset progresses
             x_step += x_step_amount
             check=False
        return

    def schedule_alarm(self,hour=None,t_0=None,t_1=None,fudge_factor=None,freq=None,seconds=None,milliseconds=None):
        if freq=='daily':
            schedule.every().day.at(hour).do(self.daily_alarm,hour,t_0,t_1,fudge_factor,freq,seconds,milliseconds) #schedule alarm depending on the frequency selected by the client.
        else:
            pass
        while True:
            schedule.run_pending()
            time.sleep(1) # wait one minute
        
    def sunset(self, seconds=None, milliseconds=None, temp_start=None, temp_end=None):
        """
        Emulates a sunset, run in a separate thread
        """
        return self.run_sequence(self._sunrise_sunset, seconds=seconds, milliseconds=milliseconds, temp_start=temp_start, temp_end=temp_end, setting=True)

    def sunrise(self, seconds=None, milliseconds=None, temp_start=None, temp_end=None):
        """
        Emulates a sunset
        """
        return self.run_sequence(self._sunrise_sunset, seconds=seconds, milliseconds=milliseconds, temp_start=temp_start, temp_end=temp_end, setting=False)
