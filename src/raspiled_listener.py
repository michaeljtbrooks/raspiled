#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Raspiled - HTTP Listener
    
        Listens on HTTP port 9090 for commands. Passes them on to any classes
        running. 
    
        @requires: twisted
"""

from __future__ import unicode_literals
from utils import *
from ledstrip import LEDStrip
import os
from subprocess import check_output, CalledProcessError
import time
from twisted.internet import reactor, endpoints,protocol
from twisted.protocols import basic
from twisted.web.resource import Resource
from twisted.web.server import Site, Request
from twisted.web.static import File
import json
from named_colours import NAMED_COLOURS
import copy
import logging
import configparser
import datetime

try:
    #python2
    from urllib import urlencode
except ImportError:
    #python3
    from urllib.parse import urlencode

APP_NAME="python ./raspiled_listener.py"

logging.basicConfig(format='[%(asctime)s RASPILED] %(message)s',
                            datefmt='%H:%M:%S',level=logging.INFO)

RASPILED_DIR = os.path.dirname(os.path.realpath(__file__)) #The directory we're running in



DEFAULTS = {
        'config_path' : RASPILED_DIR,
        'pi_host'     : 'localhost',
        'pi_port'     : 9090,   # the port our web server listens on (192.168.0.33:<pi_port>)
        'pig_port'    : 8888,   # the port pigpio daemon is listening on for pin control commands
        'latitude'    : 52.2053,  # If you wish to sync your sunrise/sunset to the real sun, enter your latitude as a decimal
        'longitude'    : 0.1218,  # If you wish to sync your sunrise/sunset to the real sun, enter your longitude as a decimal

        # Initial default values for your output pins. You can override them in your raspiled.conf file
        'red_pin'     : '17',
        'green_pin'   : '22',
        'blue_pin'    : '24'
}

config_path = os.path.expanduser(RASPILED_DIR+'/raspiled.conf')
parser = configparser.ConfigParser(defaults=DEFAULTS)
params = {}

if os.path.exists(config_path):
    logging.info('Using config file: {}'.format(config_path))
    parser.read(config_path)
    params = Odict2int(parser.defaults())
    config_file_needs_writing = False
else:
    config_file_needs_writing = True
    # No config file exists, give the user a chance to specify their pin configuration
    logging.warn('No config file found. Creating default {} file.'.format(config_path))
    logging.warn('*** Please edit this file as needed. ***')

    # Allow user to customise their pin config
    while True:
        try:  # These will assume the default settings UNLESS you enter a different value
            user_input_red_pin = int(input('RED pin number [{}]:'.format(DEFAULTS["red_pin"])) or DEFAULTS["red_pin"])
            user_input_green_pin = int(input('GREEN pin number [{}]:'.format(DEFAULTS["green_pin"])) or DEFAULTS["green_pin"])
            user_input_blue_pin = int(input('BLUE pin number [{}]:'.format(DEFAULTS["blue_pin"])) or DEFAULTS["blue_pin"])
        except (ValueError, TypeError):
            logging.warn('*** The input should be an integer ***')
        else:
            DEFAULTS['red_pin'] = user_input_red_pin
            DEFAULTS['green_pin'] = user_input_green_pin
            DEFAULTS['blue_pin'] = user_input_blue_pin
            if DEFAULTS['red_pin'] == DEFAULTS['blue_pin'] or DEFAULTS['red_pin'] == DEFAULTS['green_pin'] or DEFAULTS['green_pin'] == DEFAULTS['blue_pin']:
                logging.warn('*** The pin number should be different for all pins. ***')
            else:
                config_file_needs_writing = True
                break

# Check that our ports are sane:
user_pi_port = params.get("pi_port", DEFAULTS["pi_port"])
user_pig_port = params.get("pig_port", DEFAULTS["pig_port"])
while True:
    config_is_ok = True
    try:
        if int(user_pi_port) == int(user_pig_port):
            config_is_ok = False
            raise RuntimeError("*** You cannot have the web server running on port {} while the pigpio daemon is also running on that port! ***".format(DEFAULTS["pi_port"]))
    except RuntimeError as e:
        logging.warn(e)
    except (ValueError, TypeError):
        logging.warn("*** You have specified an invalid port number for the Raspiled web server ({}) or the Pigpio daemon ({}) ***".format(DEFAULTS["pi_port"], DEFAULTS["pig_port"]))
    else:  # Config is fine... carry on
        DEFAULTS["pi_port"] = user_pi_port
        DEFAULTS["pig_port"] = user_pig_port
        break

    try:
        user_pi_port = int(input('Raspiled web server port (e.g. 9090) [{}]:'.format(DEFAULTS["pi_port"])) or DEFAULTS["pi_port"])
        user_pig_port = int(input('Pigpio daemon port (e.g. 8888) [{}]:'.format(DEFAULTS["pig_port"])) or DEFAULTS["pig_port"])
    except (ValueError, TypeError):
        logging.warn('*** The input should be an integer ***')
    else:
        config_file_needs_writing = True


# Now write the config file if needed
if config_file_needs_writing:
    parser = configparser.ConfigParser(defaults=DEFAULTS)
    with open(config_path, 'w') as f:
        parser.write(f)
    params = Odict2int(parser.defaults())


RESOLVED_USER_SETTINGS = params  # Alias for clarity

DEBUG = False


def D(item):
    if DEBUG:
        logging.info(item)


class Preset(object):
    """
    Represents a preset for the web UI for the user to click on
    
        args and kwargs become the querystring
    """
    args=None
    kwargs=None
    label=None
    display_colour=None
    display_gradient=None
    
    def __init__(self, label="??", display_colour=None, display_gradient=None, is_sequence=False, is_sun=False, *args, **kwargs):
        """
        Sets up this preset
        """
        self.label=label
        self.display_colour = display_colour
        self.display_gradient= display_gradient or []
        self.is_sequence = is_sequence
        self.is_sun = is_sun
        self.args = args
        self.kwargs = kwargs

    def __repr__(self):
        """
        Says what this is
        """
        out = "Preset '{label}': {colour} - {querystring} - {sunquery}".format(label=self.label, colour=self.colour, querystring=self.querystring, sunquery=self.sunquery)
        return out
    
    def __unicode__(self):
        return self.render()
    
    @property
    def colours(self):
        """
        Returns a faithful hex value for the given colour(s)
        """
        if not self.display_gradient:
            colours = [self.display_colour] #Listify single entity
        else:
            colours = self.display_gradient
        colours_out_list = []
        for colour_term in colours:
            try:
                col_value = NAMED_COLOURS[str(colour_term).lower()]
            except KeyError:
                col_value = colour_term
            colours_out_list.append(col_value)
        return colours_out_list
    
    @property
    def colour(self):
        """
        Returns a string value for the colours in the form of faithful hex
        """
        return ", ".join(self.colours)
    
    def colours_for_css_background(self):
        """
        Renders the colours as a CSS background!
        
            linear-gradient(to right, col1 , col2, col3)
        """
        css_colours = self.colours
        if len(css_colours)<1: #No colours, go with trans
            return "transparent"
        elif len(css_colours)==1: #One colour means one single coloured bg
            return self.colours[0]
        return """linear-gradient(40deg, {colour_list})""".format(colour_list=", ".join(css_colours))      
    
    @property
    def querystring(self):
        """
        Converts args and kwargs into a querystring
        """
        kwargs = copy.copy(self.kwargs)
        for arg in self.args: #Add in terms for args
            kwargs[arg] = ""
        qs = urlencode(kwargs, doseq=True) #Flattens list
        return qs
    
    def render_css(self):
        """
        Generates a CSS gradient from the self.display_gradient list
        """
        if self.display_gradient:
            return "background: linear-gradient(-40deg, {colour_values}); color: white; text-shadow: 2px 2px 2px #000000".format(colour_values=self.colour)
        if self.display_colour:
            contrast_colour = LEDStrip.contrast_from_bg(col=self.colour, dark_default="202020")
            return "background: {display_colour}; color: {contrast_colour}".format(
                display_colour=self.colours_for_css_background(),
                contrast_colour=contrast_colour
            )
        return "" 
    
    def render_is_sequence(self):
        """
        Returns Javascript boolean for whether this is a sequence or not
        """
        if self.is_sequence:
            return "true"
        return ""
    
    @property
    def sunquery(self):
        """
        Returns sunset or sunrise temperature values
        """
        if self.is_sun:
            sunarg={}
            #for ii in range(0,len(self.display_gradient)):
                 #if self.display_gradient[0]>self.display_gradient[1]:
            sunarg['temp']=list(self.display_gradient)#self.display_gradient[ii].split('K')[0]
            cs = urlencode(sunarg, doseq=True)
            return cs
        return ""
    
    def render(self):
        """
        Renders this preset as an HTML button
        """
        html = """
            <a href="javascript:void(0);" class="select_preset preset_button" data-qs="{querystring}" data-sequence="{is_sequence}" data-color="{sun_temp}" style="{css_style}">
                {label}
            </a>
        """.format(
            querystring=self.querystring,
            css_style=self.render_css(),
            label=self.label,
            is_sequence=self.render_is_sequence(),
            sun_temp=self.sunquery
        )
        return html


class PresetSpace(object):
    """
    Simply spaces presets apart!
    """
    def render(self):
        return "&nbsp;"


class RaspiledControlResource(Resource):
    """
    Our web page for controlling the LED strips
    """
    isLeaf = False  # Allows us to go into dirs
    led_strip = None  # Populated at init
    _path = None  # If a user wants to hit a dynamic subpage, the path appears here
    
    # State what params should automatically trigger actions. If none supplied will show a default page. Specified in order of hierarchy
    PARAM_TO_ACTION_MAPPING = (
        # Stat actions
        ("off", "off"),
        ("stop", "stop"),
        ("set", "set"),
        ("fade", "fade"),
        ("color", "fade"),
        ("colour", "fade"),
        # Sequences
        ("sunrise", "sunrise"),
        ("morning", "sunrise"),
        ("dawn", "sunrise"),
        ("sunset", "sunset"),
        ("evening", "sunset"),
        ("dusk", "sunset"),
        ("night", "sunset"),
        ("jump", "jump"),
        ("rotate", "rotate"),
        ("rot", "rotate"),
        ("huerot", "rotate"),
        ("colors", "rotate"),
        ("colours", "rotate"),
        # Docs:
        ("capabilities", "capabilities"),
        ("capability", "capabilities"),
        ("status", "status"),
    )
    
    # State what presets to render:
    OFF_PRESET = Preset(label="""<img src="/static/figs/power-button-off.svg" class="icon_power_off"> Off""", display_colour="black", off="")
    PRESETS = {
        "Whites":( #I've had to change the displayed colours from the strip colours for a closer apparent match
                Preset(label="Candle", display_colour="1500K", fade="1000K"),
                Preset(label="Tungsten", display_colour="3200K", fade="2000K"),
                Preset(label="Bulb match", display_colour="3900K", fade="ff821c"), 
                Preset(label="Warm white", display_colour="4800K", fade="2600k"), #Bulb match
                Preset(label="Strip white", display_colour="6000K", fade="3200K"),
                Preset(label="Daylight", display_colour="6900K", fade="5800K"),
                Preset(label="Cool white", display_colour="9500K", fade="10500K"),
            ),
        "Sunrise / Sunset":(
                Preset(label="&uarr; 2hr", display_gradient=("2000K","5000K"), sunrise=60*60*2, is_sequence=True, is_sun=True),
                Preset(label="&uarr; 1hr", display_gradient=("2000K","5000K"), sunrise=60*60*1, is_sequence=True, is_sun=True),
                Preset(label="&uarr; 30m", display_gradient=("2000K","5000K"), sunrise=60*30, is_sequence=True, is_sun=True),
                Preset(label="&uarr; 1m", display_gradient=("2000K","5000K"), sunrise=60*1, is_sequence=True, is_sun=True),
                PresetSpace(),
                Preset(label="&darr; 1m", display_gradient=("5000K","2000K"), sunset=60*1, is_sequence=True, is_sun=True),
                Preset(label="&darr; 30m", display_gradient=("5000K","2000K"), sunset=60*30, is_sequence=True, is_sun=True),
                Preset(label="&darr; 1hr", display_gradient=("5000K","2000K"), sunset=60*60*1, is_sequence=True, is_sun=True),
                Preset(label="&darr; 2hr", display_gradient=("5000K","2000K"), sunset=60*60*2, is_sequence=True, is_sun=True),
            ),
        "Colours":(
                Preset(label="Red", display_colour="#FF0000", fade="#FF0000"),
                Preset(label="Orange", display_colour="#FF8800", fade="#FF8800"),
                Preset(label="Yellow", display_colour="#FFFF00", fade="#FFFF00"),
                Preset(label="Lime", display_colour="#88FF00", fade="#88FF00"),
                Preset(label="Green", display_colour="#00BB00", fade="#00FF00"),
                Preset(label="Aqua", display_colour="#00FF88", fade="#00FF88"),
                Preset(label="Cyan", display_colour="#00FFFF", fade="#00FFFF"),
                Preset(label="Blue", display_colour="#0088FF", fade="#0088FF"),
                Preset(label="Indigo", display_colour="#0000FF", fade="#0000FF"),
                Preset(label="Purple", display_colour="#8800FF", fade="#7A00FF"),  # There's a difference!
                Preset(label="Magenta", display_colour="#FF00FF", fade="#FF00FF"),
                Preset(label="Crimson", display_colour="#FF0088", fade="#FF0088"),
            ),
        "Sequences":(
                Preset(label="&#x1f525; Campfire", display_gradient=("600K","400K","1000K","400K"), rotate="900K,1000K,500K,1700K,1100K,500K,1300K,1100K,1000K,800K,1300K,900K,1000K,600K,800K,600K,600K,700K,700K,1500K,700K,1000K,1100K,1100K,800K,1000K,1300K,500K,700K,1800K,600K,1000K,800K,1400K,1100K,1100K,1100K,600K,1800K,800K,1300K,900K,500K,600K,1300K,900K,800K,900K", milliseconds="120", is_sequence=True),
                Preset(label="&#x1f41f; Fish tank", display_gradient=("#00FF88","#0088FF","#007ACC","#00FFFF"), rotate="00FF88,0088FF,007ACC,00FFFF", milliseconds="2500", is_sequence=True),
                Preset(label="&#x1f389; Party", display_gradient=("cyan","yellow","magenta"), rotate="cyan,yellow,magenta", milliseconds="1250", is_sequence=True),
                Preset(label="&#x1f33b; Flamboyant", display_gradient=("yellow","magenta"), jump="yellow,magenta", milliseconds="150", is_sequence=True),
                Preset(label="&#x1f6a8; NeeNaw", display_gradient=("cyan","blue"), jump="cyan,blue", milliseconds="100", is_sequence=True),
                Preset(label="&#x1f6a8; NeeNaw USA", display_gradient=("red","blue"), jump="red,blue", milliseconds="100", is_sequence=True),
                Preset(label="&#x1f308; Full circle", display_gradient=("#FF0000","#FF8800","#FFFF00","#88FF00","#00FF00","#00FF88","#00FFFF","#0088FF","#0000FF","#8800FF","#FF00FF","#FF0088"), milliseconds=500, rotate="#FF0000,FF8800,FFFF00,88FF00,00FF00,00FF88,00FFFF,0088FF,0000FF,8800FF,FF00FF,FF0088", is_sequence=True),
            )
    }
    PRESETS_COPY = copy.deepcopy(PRESETS)  # Modifiable dictionary. Used in alarms and music.

    def __init__(self, *args, **kwargs):
        """
        @TODO: perform LAN discovery, interrogate the resources, generate controls for all of them
        """
        self.led_strip = LEDStrip(RESOLVED_USER_SETTINGS)
        Resource.__init__(self, *args, **kwargs) #Super
        # Add in the static folder.
        static_folder = os.path.join(RASPILED_DIR,"static")
        self.putChild("static", File(static_folder))  # Any requests to /static serve from the filesystem.
    
    def getChild(self, path, request, *args, **kwargs):
        """
        Entry point for dynamic pages 
        """
        self._path = path
        return self
    
    def getChildWithDefault(self, path, request):
        """
        Retrieve a static or dynamically generated child resource from me.

        First checks if a resource was added manually by putChild, and then
        call getChild to check for dynamic resources. Only override if you want
        to affect behaviour of all child lookups, rather than just dynamic
        ones.

        This will check to see if I have a pre-registered child resource of the
        given name, and call getChild if I do not.

        @see: L{IResource.getChildWithDefault}
        """
        if path in self.children:
            return self.children[path]
        return self.getChild(path, request)
    
    def render_GET(self, request):
        """
        MAIN WEB PAGE ENTRY POINT
            Responds to GET requests

            If a valid action in the GET querystring is present, that action will get performed and
            the web server will return a JSON response. The assumption is that a javascript function is calling
            this web server to act as an API

            If a human being arrives at the web server without providing a valid action in the GET querystring,
            they'll just be given the main html page which shows all the buttons.

        @param request: The http request, passed in from Twisted, which will be an instance of <SmartRequest>

        @return: HTML or JSON depending on if there is no action or an action.
        """
        _colour_result = None
        
        # Look through the actions if the request key exists, perform that action
        clean_path = unicode(self._path or u"").rstrip("/")
        for key_name, action_name in self.PARAM_TO_ACTION_MAPPING:
            if request.has_param(key_name) or clean_path == key_name:
                action_func_name = "action__%s" % action_name
                if action_name in ("capabilities", "status"):  # Something is asking for our capabilities or status
                    output = getattr(self, action_func_name)(request)  # Execute that function
                    request.setHeader("Content-Type", "application/json; charset=utf-8")
                    return json.dumps(output)
                else:
                    self.led_strip.stop_current_sequence() #Stop current sequence
                    _colour_result = getattr(self, action_func_name)(request) #Execute that function
                break
        
        # Now deduce our colour:
        current_colour = "({})".format(self.led_strip)
        current_hex = self.led_strip.hex
        contrast_colour = self.led_strip.contrast_from_bg(current_hex, dark_default="202020")
        
        # Return a JSON object if an action has been performed (i.e. _colour_result is set):
        if _colour_result is not None:
            json_data = {
                "current" : current_hex,
                "contrast" : contrast_colour,
                "current_rgb": current_colour
            }
            try:
                request.setHeader("Content-Type", "application/json; charset=utf-8")
                return json.dumps(json_data)
            except (TypeError, ValueError):
                return b"Raspiled generated invalid JSON data!"
        
        # Otherwise, we've not had an action, so return normal page
        request.setHeader("Content-Type", "text/html; charset=utf-8")
        htmlstr = ''
        with open(RASPILED_DIR+'/static/index.html') as index_html_template:
            htmlstr = index_html_template.read()  # 2018-09-08 It's more efficient to pull the whole file in
        return htmlstr.format(
                current_colour=current_colour,
                current_hex=current_hex,
                contrast_colour=contrast_colour,
                off_preset_html=self.OFF_PRESET.render(),
                light_html=self.light_presets(request),
                alarm_html=self.alarm_presets(request),
                music_html=self.udevelop_presets(request),
                controls_html=self.udevelop_presets(request)
            ).encode('utf-8')

    #### Additional pages available via the menu ####

    def light_presets(self, request):
        """
        Renders the light presets as options

        @param request: The http request object

        """
        out_html_list = []
        for group_name, presets in self.PRESETS.items():
            preset_list = []
            #Inner for
            for preset in presets:
                preset_html = preset.render()
                preset_list.append(preset_html)
            group_html = """
                <div class="preset_group">
                    <h2>{group_name}</h2>
                    <div class="presets_row">
                        {preset_html}
                    </div>
                </div>
            """.format(
                group_name = group_name,
                preset_html = "\n".join(preset_list)
            )
            out_html_list.append(group_html)
        out_html = "\n".join(out_html_list)
        return out_html

    def alarm_presets(self,request):
       """
       Renders the alarm presets as options. Same sunrise or sunset routine except for 100k.
       """
       out_html_list = []
       preset_list = []
       #Inner for
       group_name="Sunrise / Sunset"
       presets=self.PRESETS_COPY[group_name]
       for preset in presets:
            try:
                if preset.display_gradient[0]=='5000K':
                    preset.display_gradient=('5000K','50K')
                else:
                    preset.display_gradient=('50K','5000K')
            except:
                pass
            preset_html = preset.render()
            preset_list.append(preset_html)
       group_html = """
                <p id="clock" class="current-colour"></p>
                <h2>{group_name}</h2>
                <div class="sun-alarm" data-latitude="{users_latitude}" data-longitude="{users_longitude}"></div>
                <div class="preset_group">
                    <div class="presets_row">
                        {preset_html}
                    </div>
                </div>
            """.format(
                group_name = group_name,
                preset_html = "\n".join(preset_list),
                users_latitude = RESOLVED_USER_SETTINGS.get("latitude", DEFAULTS.get("latitude", 52.2053)),
                users_longitude = RESOLVED_USER_SETTINGS.get("longitude", DEFAULTS.get("longitude", 0.1218))
            )
       out_html_list.append(group_html)
       out_html = "\n".join(out_html_list)
       return out_html

    def udevelop_presets(self,request):
       """
       Renders the Under Development text.
       """
       out_html="""
           <div class="underdevelop">
           <h1> Under Development, please refer to the Github repository.</h1>
           </div>
       """
       return out_html

    #### Actions: These are the actions our web server can initiate. Triggered by hitting the url with ?action_name=value ####

    def action__set(self, request):
        """
        Run when user wants to set a colour to a specified value
        """
        set_colour = request.get_param("set", force=unicode)
        D("Set to: %s" % set_colour)
        return self.led_strip.set(set_colour)
    action__set.capability = {
        "param": "set",
        "description": "Sets the RGB strip to a single colour.",
        "value": "<unicode> A named colour (e.g. 'pink') or colour hex value (e.g. '#19BECA').",
        "validity": "<unicode> A known named colour, or valid colour hex in the range #000000-#FFFFFF.",
        "widget": "colourpicker",
        "returns": "<unicode> The hex value of the colour the RGB strip has been set to."
    }
    
    def action__fade(self, request):
        """
        Run when user wants to set a colour to a specified value
        """
        fade_colour = request.get_param("fade", force=unicode)
        logging.info("Fade to: %s" % fade_colour)
        return self.led_strip.fade(fade_colour)
    action__fade.capability = {
        "param": "fade",
        "description": "Fades the RGB strip from its current colour to a specified colour.",
        "value": "<unicode> A named colour (e.g. 'pink') or colour hex value (e.g. '#19BECA').",
        "validity": "<unicode> A known named colour, or valid colour hex in the range #000000-#FFFFFF",
        "returns": "<unicode> The hex value of the colour the RGB strip has been set to."
    }
    
    def action__sunrise(self, request):
        """
        Performs a sunrise over the specified period of time
        """
        seconds = request.get_param(["seconds","s","sunrise"], default=10.0, force=float)
        milliseconds = request.get_param(["milliseconds","ms"], default=0.0, force=float)
        temp_start = request.get_param(['temp_start','K'], default=None, force=unicode)
        temp_end = request.get_param('temp_end', default=None, force=unicode)
        logging.info("Sunrise: %s seconds" % (seconds + (milliseconds/1000.0)))
        return self.led_strip.sunrise(seconds=seconds, milliseconds=milliseconds, temp_start=temp_start, temp_end=temp_end)
    action__sunrise.capability = {
        "param": "sunrise",
        "description": "Gently fades-in the RGB strip from deep red to daylight.",
        "value": "The number of seconds you would like the sunrise to take.",
        "validity": "<float> > 0",
        "optional_concurrent_parameters": [
            {
                "param": "milliseconds",
                "value": "The number of milliseconds the sunrise should take. Will be added to seconds (if specified) to give a total time.",
                "validity": "<int> > 0",
                "default": "1000",
            },
            {
                "param": "temp_start",
                "value": "The colour temperature you wish to start from (e.g. 500K).",
                "validity": "<unicode> Matches a named colour temperature (50K - 15000K in 100 Kelvin steps)",
                "default": "6500K"
            },
            {
                "param": "temp_end",
                "value": "The colour temperature you wish to finish at (e.g. 4500K).",
                "validity": "<unicode> Matches a named colour temperature (50K - 15000K in 100 Kelvin steps)",
                "default": "500K"
            }
        ],
        "returns": "<unicode> The hex value of the colour the RGB strip has been set to."
    }
    
    def action__sunset(self, request):
        """
        Performs a sunset over the specified period of time
        """
        seconds = request.get_param(["seconds","s","sunset"], default=10.0, force=float)
        milliseconds = request.get_param(["milliseconds","ms"], default=0.0, force=float)
        temp_start = request.get_param(['temp_start', 'K'], default=None, force=unicode)
        temp_end = request.get_param('temp_end', default=None, force=unicode)
        logging.info("Sunset: %s seconds" % (seconds + (milliseconds/1000.0)))
        return self.led_strip.sunset(seconds=seconds, milliseconds=milliseconds, temp_start=temp_start, temp_end=temp_end)
    action__sunset.capability = {
        "param": "sunset",
        "description": "Gently fades-out the RGB strip from daylight to deep-red.",
        "value": "The number of seconds you would like the sunrise to take.",
        "validity": "<float> > 0",
        "optional_concurrent_parameters": [
            {
                "param": "milliseconds",
                "value": "The number of milliseconds the sunset should take. Will be added to seconds (if specified) to give a total time.",
                "validity": "<int> > 0",
                "default": "1000",
            },
            {
                "param": "temp_start",
                "value": "The colour temperature you wish to start from (e.g. 500K).",
                "validity": "<unicode> Matches a named colour temperature (50K - 15000K in 100 Kelvin steps)",
                "default": "500K"
            },
            {
                "param": "temp_end",
                "value": "The colour temperature you wish to finish at (e.g. 4500K).",
                "validity": "<unicode> Matches a named colour temperature (50K - 15000K in 100 Kelvin steps)",
                "default": "6500K"
            }
        ],
        "returns": ""
    }
    
    def action__jump(self, request):
        """
        Jump from one specified colour to the next
        """
        jump_colours = request.get_param_values("jump")
        seconds = request.get_param(["seconds","s"], default=0.0, force=float)
        milliseconds = request.get_param(["milliseconds","ms"], default=0.0, force=float)
        self.led_strip.stop_current_sequence() #Terminate any crap that's going on
        total_seconds = (seconds + (milliseconds/1000.0))
        logging.info("Jump: %s, %s seconds" % (jump_colours, total_seconds))
        return self.led_strip.jump(jump_colours, seconds=seconds, milliseconds=milliseconds) #Has its own colour sanitisation routine
    action__jump.capability = {
        "param": "jump",
        "description": "Hops from one colour to the next over an even period of time.",
        "value": "A comma delimited list of colours you wish to jump between.",
        "validity": "<unicode> valid colour names or hex values separated by commas (e.g. red,blue,green,cyan,#FF00FF)",
        "optional_concurrent_parameters": [
            {
                "param": "milliseconds",
                "value": "The number of milliseconds the each colour should be displayed for. Will be added to seconds (if specified) to give a total time.",
                "validity": "<int> > 0",
                "default": "200",
            },
            {
                "param": "seconds",
                "value": "The number of seconds each colour should be displayed for. Will be added to milliseconds (if specified) to give a total time.",
                "validity": "<int> > 0",
                "default": "0",
            },
        ],
        "returns": "<unicode> The first hex value of sequence."
    }

    def action__rotate(self, request):
        """
        Rotates (fades) from one specified colour to the next
        """
        rotate_colours = request.get_param_values("rotate")
        seconds = request.get_param(["seconds","s"], default=0.0, force=float)
        milliseconds = request.get_param(["milliseconds","ms"], default=0.0, force=float)
        self.led_strip.stop_current_sequence() #Terminate any crap that's going on
        total_seconds = (seconds + (milliseconds/1000.0))
        logging.info("Rotate: %s, %s seconds" % (rotate_colours, total_seconds))
        return self.led_strip.rotate(rotate_colours, seconds=seconds, milliseconds=milliseconds) #Has its own colour sanitisation routine
    action__rotate.capability = {
        "param": "rotate",
        "description": "Fades from one colour to the next over an even period of time.",
        "value": "A comma delimited list of colours you wish to cross-fade between.",
        "validity": "<unicode> valid colour names or hex values separated by commas (e.g. red,blue,green,cyan,#FF00FF)",
        "optional_concurrent_parameters": [
            {
                "param": "milliseconds",
                "value": "The number of milliseconds the each colour fade should take. Will be added to seconds (if specified) to give a total time.",
                "validity": "<int> > 0",
                "default": "200",
            },
            {
                "param": "seconds",
                "value": "The number of seconds each colour fade should take. Will be added to milliseconds (if specified) to give a total time.",
                "validity": "<int> > 0",
                "default": "0",
            },
        ],
        "returns": "<unicode> The first hex value of sequence."
    }

    def action__stop(self, request):
        """
        Stops the current sequence
        """
        return self.led_strip.stop()
    action__stop.capability = {
        "param": "stop",
        "description": "Halts the current sequence or fade.",
        "value": "",
        "returns": "<unicode> The hex value of colour the RGB strip got halted on."
    }
    
    def action__off(self, request):
        """
        Turns the strip off
        """
        logging.info("Off!")
        return self.led_strip.off()
    action__off.capability = {
        "param": "off",
        "description": "Stops any fades or sequences. Quickly Fades the RGB strip to black (no light)",
        "value": "",
        "returns": "<unicode> The hex value of colour the RGB strip ends up at (#000000)."
    }

    def action__capabilities(self, request, *args, **kwargs):
        """
        Reports this listener's capabilities
        """
        output_capabilities = []
        for function_name in dir(self):
            if function_name.startswith("action__"):
                try:
                    capability_details = getattr(self,function_name).capability
                    output_capabilities.append(capability_details)
                except AttributeError:
                    pass
        return output_capabilities

    def action__status(self, request, *args, **kwargs):
        """
        Reports the status of the RGB LED strip
        """
        return {
            "current": self.led_strip.hex,
            "contrast": self.led_strip.contrast_from_bg(self.led_strip.hex, dark_default="202020"),
            "current_rgb": "({})".format(self.led_strip)
        }
    
    def teardown(self):
        """
        Called automatically when exiting the parent reactor
        """
        self.led_strip.teardown()


class NotSet():
    pass
NOT_SET = NotSet()


class SmartRequest(Request, object):
    """
    The class for request objects returned by our web server.
        This child version has methods for easily grabbing params safely.
    
        Usage:
            #If you just want the first value
            sunset = request["sunset"]
            sunset = request.get_param("sunset")
            
            #You can even test the water with multiple values, it will stop at the first valid one
            sunset = request.get_param(["sunset","ss","twilight"])
            
            #If you want a whole list of values
            jump = request.get_list("jump")

    See docs: https://twistedmatrix.com/documents/8.0.0/api/twisted.web.server.Request.html

    """
    def __init__(self, *args, **kwargs):
        super(SmartRequest, self).__init__(*args, **kwargs)

    def get_param_values(self, name, default=None):
        """
        Failsafe way of getting querystring get and post params from the Request object
        If not provided, will return default
        
        @return: ["val1","val2"] LIST of arguments, or the default
        """
        return self.args.get(name, default)
    get_params = get_param_values #Alias
    get_list = get_param_values #Alias
    get_params_list = get_param_values #Alias
    
    def get_param(self, names, default=None, force=None):
        """
        Failsafe way of getting a single querystring value. Will only return one (the first) value if found
        
        @param names: <str> The name of the param to fetch, or a list of candidate names to try
        @keyword default: The default value to return if we cannot get a valid value
        @keyword force: <type> A class / type to force the output into. Default is returned if we cannot force the value into this type 
        """
        if isinstance(names,(str, unicode)):
            names = [names]
        for name in names:
            val = self.get_param_values(name=name, default=NOT_SET)
            if val is not NOT_SET: #Once we find a valid value, continue
               break
        #If we have no valid value, then bail
        if val is NOT_SET:
            return default
        try:
            if len(val)==1:
                single_val = val[0]
                if force is not None:
                    return force(single_val)
                return single_val
            else:
                mult_val = val
                if force is not None:
                     mult_val = [force(ii) for ii in val]
                return mult_val
        except (IndexError, ValueError, TypeError):
            pass
        return default
    get_value = get_param
    param = get_param
    
    def has_params(self, *param_names):
        """
        Returns True or the value if any of the param names given by args exist
        """
        for param_name in param_names:
            try:
                return self.args[param_name] or True
            except KeyError:
                pass
        return False
    has_param = has_params
    has_key = has_params
    
    def __getitem__(self, name):
        """
        Lazy way of getting a param list, with the fallback default being None 
        """
        return self.get_param(name)
    

        
class RaspiledControlSite(Site, object):
    """
    Site thread which initialises the RaspiledControlResource properly
    """
    def __init__(self, *args, **kwargs):
        resource = kwargs.pop("resource",RaspiledControlResource())
        super(RaspiledControlSite, self).__init__(resource=resource, requestFactory=SmartRequest, *args, **kwargs)
    
    def stopFactory(self):
        """
        Called automatically when exiting the reactor. Here we tell the LEDstrip to tear down its resources
        """
        self.resource.teardown()



def get_matching_pids(name, exclude_self=True):
    """
    Checks the process ID of the specified processes matching name, having excluded itself
    
        check_output(["pidof", str]) will return a space delimited list of all process ids
        
    @param name: <str> The process name to search for
    @keyword exclude_self: <Bool> Whether to remove own ID from returned list (e.g. if searching for a python script!) 
    
    @return: <list [<str>,]> List of PIDs 
    """
    #Get all matching PIDs
    try:
        pids_str = check_output(["pidof",name])
    except CalledProcessError: #No matches
        pids_str = ""
    #Process string-list into python list
    pids = pids_str.strip().split(" ")
    #Remove self if required:
    if exclude_self:
        my_pid = str(os.getpid()) #Own PID - getpid() returns integer
        try:
            pids.remove(my_pid)  #Remove my PID string:
        except ValueError:
            pass
    return pids


def checkClientAgainstWhitelist(ip, user,token):
    IPS = {
           'IP1' : '127.0.0.1',
           }

    config_path = os.path.expanduser(RASPILED_DIR+'/.whitelist')
    parser = configparser.ConfigParser(defaults=IPS)
    
    if os.path.exists(config_path):
        parser.read(config_path)
    else:
        with open(config_path, 'w') as f:
            parser.write(f)

    whitelist=parser.defaults()
    for ii in whitelist.keys():
        if ip == whitelist[ii]:
            logging.info('Client registered')
            connection = True
            break
        else:
            connection = False
    return connection


class RaspiledProtocol(basic.LineReceiver):
    """
    Twisted Protocol to handle HTTP connections
    """

    def __init__(self):
        self.lines = []

    def lineReceived(self, line):
        self.lines.append(line)
        if not line:
            self.sendResponse()

    def sendResponse(self):
        self.sendLine("HTTP/1.1 200 OK")
        self.sendLine("")
        responseBody = "You said:\r\n\r\n" + "\r\n".join(self.lines)
        self.transport.write(responseBody)
        self.transport.loseConnection()


class HTTPEchoFactory(protocol.ServerFactory):
    def buildProtocol(self, addr):
        return RaspiledProtocol()

def start_if_not_running():
    """
    Checks if the process is running, if not, starts it!
    """
    pids = get_matching_pids(APP_NAME, exclude_self=True) #Will remove own PID
    pids = filter(bool,pids)
    if not pids: #No match! Implies we need to fire up the listener
        logging.info("[STARTING] Raspiled Listener with PID %s" % str(os.getpid()))
        factory = RaspiledControlSite(timeout=8) #8s timeout
        endpoint = endpoints.TCP4ServerEndpoint(reactor, RESOLVED_USER_SETTINGS['pi_port'])
        endpoint.listen(factory)
        reactor.run()
    else:
        logging.info("Raspiled Listener already running with PID %s" % ", ".join(pids))


if __name__=="__main__":
    start_if_not_running()


