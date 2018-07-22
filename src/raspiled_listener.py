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
from twisted.web.resource import Resource
from twisted.web.server import Site, Request
from twisted.web.static import File
import json
from named_colours import NAMED_COLOURS
import copy
import logging
import configparser
import datetime
import requests

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
        'pi_port'     : 9090,
        'pig_port'    : 8888,
        'red_pin'     : '',
        'green_pin'   : '',
        'blue_pin'    : ''
            }

config_path = os.path.expanduser(RASPILED_DIR+'/raspiled.conf')
parser = configparser.ConfigParser(defaults=DEFAULTS)

if os.path.exists(config_path):
    logging.info('Using config file: {}'.format(config_path))
    parser.read(config_path)
else:
    logging.warn('No config file found. Creating default {} file.'.format(config_path))
    logging.warn('*** Please edit this file as needed. ***')
    
    while True:
        try:
            DEFAULTS['red_pin']=input('RED pin number:')
            DEFAULTS['green_pin']=input('GREEN pin number:')
            DEFAULTS['blue_pin']=input('BLUE pin number:')

            if (DEFAULTS['red_pin']==DEFAULTS['blue_pin'] 
	      or DEFAULTS['red_pin']==DEFAULTS['green_pin'] 
	      or DEFAULTS['green_pin']==DEFAULTS['blue_pin']):
	        logging.warn('*** The pin number should be different for all pins. ***')
	    else:
	        logging.info('Configuration Finished.')
	        break
        except:
	    logging.warn('*** The input should be an integer ***')
    parser = configparser.ConfigParser(defaults=DEFAULTS)
    with open(config_path, 'w') as f:
        parser.write(f)

params = Odict2int(parser.defaults())

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
        Renders this preset as an HTML button or selection. 
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

    def render_select(self):
        html = """
            <option href="javascript:void(0);" value="{label}" class="select_preset preset_option" data-qs="{querystring}" data-sequence="{is_sequence}" data-color="{sun_temp}" style="{css_style}">
                {label}
            </option>
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
    def render_select(self):
        return "&nbsp;"


class RaspiledControlResource(Resource):
    """
    Our web page for controlling the LED strips
    """
    isLeaf = False #Allows us to go into dirs
    led_strip = None #Populated at init
    
    #State what params should automatically trigger actions. If none supplied will show a default page. Specified in order of hierarchy
    PARAM_TO_ACTION_MAPPING = (
        #Stat actions
        ("off", "off"),
        ("stop", "stop"),
        ("set", "set"),
        ("fade", "fade"),
        ("color", "fade"),
        ("colour", "fade"),
        #Sequences
        ("sunrise", "sunrise"),
        ("morning", "alarm"),
        ("dawn", "alarm"),
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
    )
    
    #State what presets to render:
    OFF_PRESET = Preset(label="&#x23FB; Off", display_colour="black", off="")
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
                Preset(label="Purple", display_colour="#8800FF", fade="#7A00FF"), #There's a difference!
                Preset(label="Magenta", display_colour="#FF00FF", fade="#FF00FF"),
                Preset(label="Crimson", display_colour="#FF0088", fade="#FF0088"),
            ),
        "Sequences":(
                Preset(label="&#x1f525; Campfire", display_gradient=("600K","400K","1000K","400K"), rotate="700K,500K,1100K,600K,800K,1000K,500K,1200K", milliseconds="1800", is_sequence=True),
                Preset(label="&#x1f41f; Fish tank", display_gradient=("#00FF88","#0088FF","#007ACC","#00FFFF"), rotate="00FF88,0088FF,007ACC,00FFFF", milliseconds="2500", is_sequence=True),
                Preset(label="&#x1f389; Party", display_gradient=("cyan","yellow","magenta"), rotate="cyan,yellow,magenta", milliseconds="1250", is_sequence=True),
                Preset(label="&#x1f33b; Flamboyant", display_gradient=("yellow","magenta"), jump="yellow,magenta", milliseconds="150", is_sequence=True),
                Preset(label="&#x1f6a8; NeeNaw", display_gradient=("cyan","blue"), jump="cyan,blue", milliseconds="100", is_sequence=True),
                Preset(label="&#x1f6a8; NeeNaw USA", display_gradient=("red","blue"), jump="red,blue", milliseconds="100", is_sequence=True),
                Preset(label="&#x1f308; Full circle", display_gradient=("#FF0000","#FF8800","#FFFF00","#88FF00","#00FF00","#00FF88","#00FFFF","#0088FF","#0000FF","#8800FF","#FF00FF","#FF0088"), milliseconds=500, rotate="#FF0000,FF8800,FFFF00,88FF00,00FF00,00FF88,00FFFF,0088FF,0000FF,8800FF,FF00FF,FF0088", is_sequence=True),
            )
    }
    ALARM_PRESETS = {
        "Morning":(
                Preset(label="&uarr; 2hr", display_gradient=("0K","5000K"), morning=60*60*2, is_sequence=True, is_sun=True),
                Preset(label="&uarr; 1hr", display_gradient=("0K","5000K"), morning=60*60*1, is_sequence=True, is_sun=True),
                Preset(label="&uarr; 30m", display_gradient=("0K","5000K"), morning=60*30, is_sequence=True, is_sun=True),
                Preset(label="&uarr; 1m", display_gradient=("0K","5000K"), morning=60*1, is_sequence=True, is_sun=True),
            ),
        "Dawn":(
                Preset(label="&darr; 2hr", display_gradient=("5000K","0K"), dawn=60*60*2, is_sequence=True, is_sun=True),
                Preset(label="&darr; 1hr", display_gradient=("5000K","0K"), dawn=60*60*1, is_sequence=True, is_sun=True),
                Preset(label="&darr; 30m", display_gradient=("5000K","0K"), dawn=60*30, is_sequence=True, is_sun=True),
                Preset(label="&darr; 1m", display_gradient=("5000K","0K"), dawn=60*1, is_sequence=True, is_sun=True),
            )
    }

    def __init__(self, *args, **kwargs):
        """
        @TODO: perform LAN discovery, interrogate the resources, generate controls for all of them
        """
        self.led_strip = LEDStrip(params)
        Resource.__init__(self, *args, **kwargs) #Super
        #Add in the static folder
        static_folder = os.path.join(RASPILED_DIR,"static")
        self.putChild("static", File(static_folder))
    
    def getChild(self, path, request, *args, **kwargs):
        """
        Entry point for dynamic pages 
        """
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
        Responds to GET requests
        """
        _colour_result = None
        #Look through the actions if the request key exists, perform that action
        for key_name, action_name in self.PARAM_TO_ACTION_MAPPING:
            if request.has_param(key_name):
                self.led_strip.stop_current_sequence() #Stop current sequence
                action_func_name = "action__%s" % action_name
                _colour_result = getattr(self, action_func_name)(request) #Execute that function
                break
        
        #Now deduce our colour:
        current_colour = "({})".format(self.led_strip)
        current_hex = self.led_strip.hex
        contrast_colour = self.led_strip.contrast_from_bg(current_hex, dark_default="202020")
        
        #Return a JSON object if a result:
        if _colour_result is not None:
            json_data = {
                "current" : current_hex,
                "contrast" : contrast_colour,
                "current_rgb": current_colour
            }
            try:
                return json.dumps(json_data)
            except:
                return b"Json fkucked up"
        
        #Otherwise return normal page
        request.setHeader("Content-Type", "text/html; charset=utf-8")
        htmlstr=''
        with open(RASPILED_DIR+'/static/index.html') as file:
            for line in file:
                 htmlstr+=line
        return htmlstr.format(
                current_colour=current_colour,
                current_hex=current_hex,
                contrast_colour=contrast_colour,
                off_preset_html=self.OFF_PRESET.render(),
                light_html=self.light_presets(request),
                alarm_html=self.alarm_presets(request),
                music_html=self.music_presets(request),
                controls_html=self.udevelop_presets(request),
                addition_js=self.js_interactions(request)
            ).encode('utf-8')
    
    def light_presets(self, request):
        """
        Renders the light presets as options
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
       for group_name, presets in self.ALARM_PRESETS.items():
           preset_list = []
           #Inner for
           for preset in presets:
               preset_html = preset.render_select()
               preset_list.append(preset_html)
           group_html = """
                <p> {group_name} time </p>
                <div class="{group_name}"></div>
                <div class="preset_group">
                    <select class="presets_select {group_name}_select">
                        {preset_html}
                    </select>
                </div>
            """.format(
                group_name = group_name,
                preset_html = "\n".join(preset_list)
           )
           out_html_list.append(group_html)
       out_html = "\n".join(out_html_list)
       return out_html

    def music_presets(self,request):
       """
       Renders the Modipy music front page.
       """
       out_html="""
           <iframe src="http://192.168.182.190:6680/mopify/" style="width:100vw;height:100vh">
           </iframe>
       """
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
    
    def js_interactions(self,request):
        request.setHeader("Content-Type", "text/html; charset=utf-8")
        lat,lon=pi_gps_location()
        jsstr=''
        with open(RASPILED_DIR+'/static/js/raspiled_interaction.js') as file:
            for line in file:
                 jsstr+=line
        return jsstr.format(latcoord=str(lat),loncoord=str(lon)).encode('utf-8')


    def action__set(self, request):
        """
        Run when user wants to set a colour to a specified value
        """
        set_colour = request.get_param("set", force=unicode)
        D("Set to: %s" % set_colour)
        return self.led_strip.set(set_colour)
    
    def action__fade(self, request):
        """
        Run when user wants to set a colour to a specified value
        """
        fade_colour = request.get_param("fade", force=unicode)
        logging.info("Fade to: %s" % fade_colour)
        return self.led_strip.fade(fade_colour)
    
    def action__sunrise(self, request):
        """
        Performs a sunrise over the specified period of time
        """
        seconds = request.get_param(["seconds","s","sunrise"], default=10.0, force=float)
        milliseconds = request.get_param(["milliseconds","ms"], default=0.0, force=float)
        temps = request.get_param(['temp','K'],default=0.0,force=unicode)
        logging.info("Sunrise: %s seconds" % (seconds + (milliseconds/1000.0)))
        return self.led_strip.sunrise(seconds=seconds, milliseconds=milliseconds, temps=temps)
    
    def action__sunset(self, request):
        """
        Performs a sunset over the specified period of time
        """
        seconds = request.get_param(["seconds","s","sunset"], default=10.0, force=float)
        milliseconds = request.get_param(["milliseconds","ms"], default=0.0, force=float)
        temps = request.get_param(['temp','K'],default=0.0,force=unicode)
        logging.info("Sunset: %s seconds" % (seconds + (milliseconds/1000.0)))
        return self.led_strip.sunset(seconds=seconds, milliseconds=milliseconds, temps=temps)
    
    def action__alarm(self, request):
        """
        Performs a sunrise over the specified period of time
        """
        m_seconds = request.get_param(["seconds","s","morning"], default=10.0, force=float)
        d_seconds = request.get_param(["seconds","s","dawn"], default=10.0, force=float)
        time = request.get_param(["time","hr","hour"], default='12:00', force=unicode)
        milliseconds = request.get_param(["milliseconds","ms"], default=0.0, force=float)
        temps = request.get_param(['temp','K'],default=0.0,force=unicode)
        logging.info("Morning Alarm : %s seconds at %s" % (m_seconds + (milliseconds/1000.0), m_time))
        logging.info("Dawn Alarm    : %s seconds at %s" % (d_seconds + (milliseconds/1000.0), d_time))
        return self.led_strip.alarm(seconds=[d_seconds,m_seconds], milliseconds=milliseconds, time=time , temps=temps)

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
    
    def action__stop(self, request):
        """
        Stops the current sequence
        """
        return self.led_strip.stop()
    
    def action__off(self, request):
        """
        Turns the strip off
        """
        logging.info("Off!")
        return self.led_strip.off()
    
    def teardown(self):
        """
        Called automatically when exiting the parent reactor
        """
        self.led_strip.teardown()


class NotSet():
    pass
NOT_SET = NotSet()

def pi_gps_location(ip=''):
    if ip=='':
    	locip = 'https://api.ipify.org?format=json'
    	r = requests.get(locip)
    	j = json.loads(r.text)
    	ipinfo = 'https://ipinfo.io/'+j['ip']
    else:
        ipinfo = 'https://ipinfo.io/'+ip
    r = requests.get(ipinfo)
    j = json.loads(r.text)
    lat,lon=j['loc'].split(',')
    return lat,lon

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
            
    """
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
        print(self,names,default,force)
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
                print(mult_val)
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

from twisted.protocols import basic

class RaspiledProtocol(basic.LineReceiver):#protocol.Protocol):
    #def __init__(self, factory):
         #super(RaspiledProtocol, self).__init__(factory=factory)
    #     self.factory = factory
     


    #    reactor.stop()    
    #def connectionMade(self):
    #    self.transport.pauseProducing()
    #    ip, port = self.transport.client
         
    #    result = checkClientAgainstWhitelist(ip,'lsls','token' )
    #    if result == False:
    #        logging.warn(('Client attempting to access: IP - {}, Port - {}'.format(ip,port)))
    #        self.transport.loseConnection()
    #     else:
    #        logging.info(('Client connection: IP {}, Port {}'.format(ip,port)))
    #        self.transport.resumeProducing()
    #        return RaspiledControlResource
         #self.factory.numProtocols = self.factory.numProtocols+1 
         #self.transport.write(
         #    "Welcome! There are currently %d open connections.\n" %
         #    (self.factory.numProtocols,))
    #def connectionLost(self, reason):
    #    logging.info('Lost connection')
        #self.transport.loseConnection()
        #self.factory.numProtocols = self.factory.numProtocols-1
    #def dataReceived(self,data):
    #    print(data)

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

    #def sendResponse(self):
    #    self.sendLine("HTTP/1.1 200 OK")
    #    self.sendLine("")
    #    responseBody = "You said:\r\n\r\n" + "\r\n".join(self.lines)
    #    self.transport.write(responseBody)
    #    self.transport.loseConnection()
        #self.transport.write(data)
        #apass  
    #def autentication():
    #    def __init__(self, username, server, clientref):
    #        self.name = username
    #        self.server = password
    #        self.key = key
    #def dataReceived(self, data):
        #self.transport.write(data)

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
        ##resource = RaspiledControlSite()
        
	#factory = protocol.ServerFactory()        
        factory = RaspiledControlSite(timeout=8) #8s timeout
#        print(factory.protocol.transport.client)
        #factory.protocol = RaspiledProtocol#(factory)
        #endpoint.connect(factory)
        endpoint = endpoints.TCP4ServerEndpoint(reactor, params['pi_port'])
        #endpoint.listen(RaspiledProtocol)
        endpoint.listen(factory)
        reactor.run()
#        reactor.listenTCP(9090, HTTPEchoFactory())
#        reactor.run()
    else:
        logging.info("Raspiled Listener already running with PID %s" % ", ".join(pids))

if __name__=="__main__":
    start_if_not_running()


#f = protocol.ServerFactory()
#f.protocol = MyProtocol
#reactor.listenTCP(9111, f)
#reactor.run()


#ip, port = self.transport.client
#print ip
#print port
