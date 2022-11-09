#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    Raspiled - HTTP Listener
    
        Listens on HTTP port 9090 for commands. Passes them on to any classes
        running. 
    
        @requires: twisted
"""
from __future__ import unicode_literals
import os
import sys
# Add some gymnastics so we can use imports relative to the parent dir.
my_dir = os.path.dirname(os.path.realpath(__file__))  # The directory we're running in
sys.path.append(os.path.dirname(my_dir))  # Parent dir

from src.config import CONFIG, get_setting, DEBUG, logger
from utils import *
from ledstrip import LEDStrip

from subprocess import check_output, CalledProcessError
from twisted.internet import reactor, endpoints
from twisted.web.server import Site, Request
from named_colours import NAMED_COLOURS
import copy
import configparser
import six
from six.moves.urllib.parse import urlencode


APP_NAME = "python ./raspiled_listener.py"

RASPILED_DIR = os.path.dirname(os.path.realpath(__file__))  # The directory we're running in

RESOLVED_USER_SETTINGS = CONFIG  # Alias for clarity


class Preset(object):
    """
    Represents a preset for the web UI for the user to click on
    
        args and kwargs become the querystring
    """
    args = None
    kwargs = None
    label = None
    display_colour = None
    display_gradient = None
    slug = ""

    def __init__(self, label="??", display_colour=None, display_gradient=None, is_sequence=False, is_sun=False, slug=None, *args, **kwargs):
        """
        Sets up this preset
        """
        self.label = label
        self.display_colour = display_colour
        self.display_gradient = display_gradient or []
        self.is_sequence = is_sequence
        self.is_sun = is_sun
        self.args = args
        self.kwargs = kwargs
        self.slug = slugify(slug or label)  # Used to call a preset directly

    def __repr__(self):
        """
        Says what this is
        """
        out = "Preset '{label}': {colour} - {querystring} - {sunquery}".format(
            label=self.label,
            colour=self.colour,
            querystring=self.querystring,
            sunquery=self.sunquery)
        return out

    def __str__(self):
        return self.render()

    @property
    def colours(self):
        """
        Returns a faithful hex value for the given colour(s)
        """
        if not self.display_gradient:
            colours = [self.display_colour]  # Listify single entity
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
        if len(css_colours) < 1:  # No colours, go with trans
            return "transparent"
        elif len(css_colours) == 1:  # One colour means one single coloured bg
            return self.colours[0]
        return """linear-gradient(40deg, {colour_list})""".format(colour_list=", ".join(css_colours))

    @property
    def querystring(self):
        """
        Converts args and kwargs into a querystring
        """
        kwargs = copy.copy(self.kwargs)
        for arg in self.args:  # Add in terms for args
            kwargs[arg] = ""
        qs = urlencode(kwargs, doseq=True)  # Flattens list
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
            sunarg = {}
            # for ii in range(0,len(self.display_gradient)):
            # if self.display_gradient[0]>self.display_gradient[1]:
            sunarg['temp'] = list(self.display_gradient)  # self.display_gradient[ii].split('K')[0]
            cs = urlencode(sunarg, doseq=True)
            return cs
        return ""

    def render(self):
        """
        Renders this preset as an HTML button
        """
        html = """
            <a href="javascript:void(0);" class="select_preset preset_button" data-qs="{querystring}" data-sequence="{is_sequence}" data-slug="{slug}" data-color="{sun_temp}" style="{css_style}">
                {label}
            </a>
        """.format(
            querystring=self.querystring,
            css_style=self.render_css(),
            label=self.label,
            is_sequence=self.render_is_sequence(),
            sun_temp=self.sunquery,
            slug=self.slug
        )
        return html


class PresetSpace(object):
    """
    Simply spaces presets apart!
    """
    slug = None

    def render(self):
        return "&nbsp;"


class PresetRow(object):
    """
    Simply spaces presets apart!
    """
    slug = None

    def render(self):
        return "<br>"


def get_presets_as_options(presets_dict):
    """
    Return the presets as options
    :return: List of tuples
    """
    options = []
    for section_name, presets in presets_dict.items():
        for preset in presets:
            if isinstance(preset, Preset):
                options.append((preset.slug, "{}: {}".format(section_name, preset.label)))
    return options


class RaspiledControlResource(RaspberryPiWebResource):
    """
    Our web page for controlling the LED strips
    """
    led_strip = None  # Populated at init

    # State what params should automatically trigger actions. If none supplied will show a default page. Specified in order of hierarchy
    PRESET_FUNCTIONS = (
        # Stat actions
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
    )
    PARAM_TO_ACTION_MAPPING = (
        # Generic:
        ("off", "off"),
        ("stop", "stop"),
        ("preset", "preset")
    ) + PRESET_FUNCTIONS + (
        # Docs:
        ("capabilities", "capabilities"),
        ("capability", "capabilities"),
        ("status", "status"),
    )

    # State what presets to render:
    OFF_PRESET = Preset(label="""<img src="/static/figs/power-button-off.svg" class="icon_power_off"> Off""", display_colour="black", off="")
    PRESETS = {
        "Whites": (  # I've had to change the displayed colours from the strip colours for a closer apparent match
            Preset(label="Candle", display_colour="1500K", fade="1000K"),
            Preset(label="Tungsten", display_colour="3200K", fade="2000K"),
            Preset(label="Bulb match", display_colour="3900K", fade="ff821c"),
            Preset(label="Warm white", display_colour="4800K", fade="2600k"),  # Bulb match
            Preset(label="Strip white", display_colour="6000K", fade="3200K"),
            Preset(label="Daylight", display_colour="6900K", fade="5800K"),
            Preset(label="Cool white", display_colour="9500K", fade="10500K"),
        ),
        "Sunrise / Sunset": (
            Preset(label="&uarr; 2hr", slug="sunrise2hr", display_gradient=("2000K", "5000K"), sunrise=60 * 60 * 2, is_sequence=True, is_sun=True),
            Preset(label="&uarr; 1hr", slug="sunrise1hr", display_gradient=("2000K", "5000K"), sunrise=60 * 60 * 1, is_sequence=True, is_sun=True),
            Preset(label="&uarr; 30m", slug="sunrise30m", display_gradient=("2000K", "5000K"), sunrise=60 * 30, is_sequence=True, is_sun=True),
            Preset(label="&uarr; 1m",  slug="sunrise1m", display_gradient=("2000K", "5000K"), sunrise=60 * 1, is_sequence=True, is_sun=True),
            PresetSpace(),
            Preset(label="&darr; 1m", slug="sunset1m", display_gradient=("5000K", "2000K"), sunset=60 * 1, is_sequence=True, is_sun=True),
            Preset(label="&darr; 30m", slug="sunset30m", display_gradient=("5000K", "2000K"), sunset=60 * 30, is_sequence=True, is_sun=True),
            Preset(label="&darr; 1hr", slug="sunset1hr", display_gradient=("5000K", "2000K"), sunset=60 * 60 * 1, is_sequence=True, is_sun=True),
            Preset(label="&darr; 2hr", slug="sunset2hr", display_gradient=("5000K", "2000K"), sunset=60 * 60 * 2, is_sequence=True, is_sun=True),
        ),
        "Colours": (
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
            PresetRow(),
            Preset(label="Tasty Teal", display_colour="#009882", fade="#00FF4D"),
            Preset(label="Super Crimson", display_colour="#FF0077", fade="#FF0033"),
        ),
        "Sequences": (
            Preset(label="&#x1f525; Campfire", slug="campfire", display_gradient=("600K", "400K", "1000K", "400K"), rotate="700K,500K,1100K,600K,800K,1000K,500K,1200K",
                   milliseconds="1800", is_sequence=True),
            Preset(label="&#x1f41f; Fish tank", slug="fishtank", display_gradient=("#00FF88", "#0088FF", "#007ACC", "#00FFFF"), rotate="00FF88,0088FF,007ACC,00FFFF",
                   milliseconds="2500", is_sequence=True),
            Preset(label="&#x1f389; Party", slug="party", display_gradient=("cyan", "yellow", "magenta"), rotate="cyan,yellow,magenta", milliseconds="1250",
                   is_sequence=True),
            Preset(label="&#x1f33b; Flamboyant", slug="flamboyant", display_gradient=("yellow", "magenta"), jump="yellow,magenta", milliseconds="150", is_sequence=True),
            Preset(label="&#x1F384; Christmas", slug="christmas", display_gradient=("green", "red"), rotate="green,red", milliseconds="300", is_sequence=True),
            Preset(label="&#x1f6a8; NeeNaw", slug="neenaw", display_gradient=("cyan", "blue"), jump="cyan,blue", milliseconds="100", is_sequence=True),
            Preset(label="&#x1f6a8; NeeNaw USA", slug="neenawusa", display_gradient=("red", "blue"), jump="red,blue", milliseconds="100", is_sequence=True),
            Preset(label="&#x1f308; Full circle", slug="fullcircle", display_gradient=(
                   "#FF0000", "#FF8800", "#FFFF00", "#88FF00", "#00FF00", "#00FF88", "#00FFFF", "#0088FF", "#0000FF", "#8800FF", "#FF00FF", "#FF0088"),
                   milliseconds=500, rotate="#FF0000,FF8800,FFFF00,88FF00,00FF00,00FF88,00FFFF,0088FF,0000FF,8800FF,FF00FF,FF0088", is_sequence=True),
        )
    }
    PRESETS_COPY = copy.deepcopy(PRESETS)  # Modifiable dictionary. Used in alarms and music.

    def __init__(self, *args, **kwargs):
        """
        @TODO: perform LAN discovery, interrogate the resources, generate controls for all of them
        """
        self.led_strip = LEDStrip(RESOLVED_USER_SETTINGS)
        RaspberryPiWebResource.__init__(self, *args, **kwargs)  # Super, deals with generating the static directory etc

    def render_controls(self, request):
        """
        Show the main controls screen
        """
        context = {
            "off_preset_html": self.OFF_PRESET.render(),
            "light_html": self.render_light_presets(request),
            "alarm_html": self.render_alarm_presets(request),
            "music_html": self.render_udevelop_presets(request),
            "controls_html": self.render_udevelop_presets(request),
        }
        return RaspberryPiWebResource.render_controls(self, request, context)

    #### Additional pages available via the menu ####

    def render_light_presets(self, request):
        """
        Renders the light presets as options

        @param request: The http request object

        """
        out_html_list = []
        for group_name, presets in self.PRESETS.items():
            preset_list = []
            # Inner for
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
                group_name=group_name,
                preset_html="\n".join(preset_list)
            )
            out_html_list.append(group_html)
        out_html = "\n".join(out_html_list)
        return out_html

    def render_alarm_presets(self, request):
        """
        Renders the alarm presets as options. Same sunrise or sunset routine except for 100k.
        """
        out_html_list = []
        preset_list = []
        # Inner for
        group_name = "Sunrise / Sunset"
        presets = self.PRESETS_COPY[group_name]
        for preset in presets:
            try:
                if preset.display_gradient[0] == '5000K':
                    preset.display_gradient = ('5000K', '50K')
                else:
                    preset.display_gradient = ('50K', '5000K')
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
            group_name=group_name,
            preset_html="\n".join(preset_list),
            users_latitude=get_setting("latitude", 52.2053),
            users_longitude=get_setting("longitude", 0.1218)
        )
        out_html_list.append(group_html)
        out_html = "\n".join(out_html_list)
        return out_html

    def render_udevelop_presets(self, request):
        """
        Renders the Under Development text.
        """
        out_html = """
           <div class="underdevelop">
           <h1> Under Development, please refer to the Github repository.</h1>
           </div>
        """
        return out_html

    # Actions: These are the actions our web server can initiate. Triggered by hitting the url with ?action_name=value ####

    def before_action(self, *args, **kwargs):
        """
        Called just before an action takes place. We stop whatever current sequence is running
        """
        self.led_strip.stop_current_sequence()  # Stop current sequence

    def action__set(self, request):
        """
        Run when user wants to set a colour to a specified value
        """
        set_colour = request.get_param("set", force=six.text_type)
        D("Set to: %s" % set_colour)
        self.led_strip.set(set_colour)
        return self.outcome(action="set", successful=True, message="Set colour to: {}", message_args=[set_colour])

    action__set.capability = {
        "param": "set",
        "description": "Sets the RGB strip to a single colour.",
        "value": "<unicode> A named colour (e.g. 'pink') or colour hex value (e.g. '#19BECA'), or a comma delimited list of integers for r,g,b.",
        "validity": "<unicode> A known named colour, or valid colour hex in the range #000000-#FFFFFF.",
        "widget": "colourpicker"
    }

    def action__fade(self, request):
        """
        Run when user wants to set a colour to a specified value
        """
        fade_colour = request.get_param("fade", force=six.text_type)
        logger.info("Fade to: %s" % fade_colour)
        self.led_strip.fade(fade_colour)
        return self.outcome(action="fade", successful=True, message="Faded colour to: {}", message_args=[fade_colour])

    action__fade.capability = {
        "param": "fade",
        "description": "Fades the RGB strip from its current colour to a specified colour.",
        "value": "<unicode> A named colour (e.g. 'pink') or colour hex value (e.g. '#19BECA'), or a comma delimited list of integers for r,g,b.",
        "validity": "<unicode> A known named colour, or valid colour hex in the range #000000-#FFFFFF",
    }

    def action__sunrise(self, request):
        """
        Performs a sunrise over the specified period of time
        """
        seconds = request.get_param(["seconds", "s", "sunrise"], default=10.0, force=float)
        milliseconds = request.get_param(["milliseconds", "ms"], default=0.0, force=float)
        temp_start = request.get_param(['temp_start', 'K'], default=None, force=six.text_type)
        temp_end = request.get_param('temp_end', default=None, force=six.text_type)
        logger.info("Sunrise: %s seconds" % (seconds + (milliseconds / 1000.0)))
        self.led_strip.sunrise(seconds=seconds, milliseconds=milliseconds, temp_start=temp_start, temp_end=temp_end)
        return self.outcome(action="sunrise", successful=True, message="Triggered sunrise: {}>{} over {}s", message_args=[temp_start or 500, temp_end or 6500, seconds or 10])

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
        ]
    }

    def action__sunset(self, request):
        """
        Performs a sunset over the specified period of time
        """
        seconds = request.get_param(["seconds", "s", "sunset"], default=10.0, force=float)
        milliseconds = request.get_param(["milliseconds", "ms"], default=0.0, force=float)
        temp_start = request.get_param(['temp_start', 'K'], default=None, force=six.text_type)
        temp_end = request.get_param('temp_end', default=None, force=six.text_type)
        logger.info("Sunset: %s seconds" % (seconds + (milliseconds / 1000.0)))
        self.led_strip.sunset(seconds=seconds, milliseconds=milliseconds, temp_start=temp_start, temp_end=temp_end)
        return self.outcome(action="sunset", successful=True, message="Triggered sunset: {}>{} over {}s", message_args=[temp_start or 6500, temp_end or 500, seconds or 10])

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
    }

    def action__jump(self, request):
        """
        Jump from one specified colour to the next
        """
        jump_colours = request.get_param_values("jump")
        seconds = request.get_param(["seconds", "s"], default=0.0, force=float)
        milliseconds = request.get_param(["milliseconds", "ms"], default=0.0, force=float)
        self.led_strip.stop_current_sequence()  # Terminate any crap that's going on
        total_seconds = (seconds + (milliseconds / 1000.0))
        logger.info("Jump: %s, %s seconds" % (jump_colours, total_seconds))
        self.led_strip.jump(jump_colours, seconds=seconds, milliseconds=milliseconds)  # Has its own colour sanitisation routine
        return self.outcome(action="jump", successful=True, message="Running jump sequence: {} step duration {}ms",
                            message_args=[jump_colours, (seconds or 0 * 1000) or (milliseconds or 300)])

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
    }

    def action__rotate(self, request):
        """
        Rotates (fades) from one specified colour to the next
        """
        rotate_colours = request.get_param_values("rotate")
        seconds = request.get_param(["seconds", "s"], default=0.0, force=float)
        milliseconds = request.get_param(["milliseconds", "ms"], default=0.0, force=float)
        self.led_strip.stop_current_sequence()  # Terminate any crap that's going on
        total_seconds = (seconds + (milliseconds / 1000.0))
        logger.info("Rotate: %s, %s seconds" % (rotate_colours, total_seconds))
        self.led_strip.rotate(rotate_colours, seconds=seconds, milliseconds=milliseconds)  # Has its own colour sanitisation routine
        return self.outcome(action="rotate", successful=True, message="Running colour rotation sequence: {} with fade time {}ms",
                            message_args=[rotate_colours, (seconds or 0 * 1000) or (milliseconds or 300)])

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
    }

    def action__stop(self, request):
        """
        Stops the current sequence
        """
        self.led_strip.stop()
        return self.outcome(action="stop", successful=True, message="Sequence stopped")

    action__stop.capability = {
        "param": "stop",
        "description": "Halts the current sequence or fade.",
        "value": "",
    }

    def action__off(self, request):
        """
        Turns the strip off
        """
        logger.info("Off!")
        self.led_strip.off()
        return self.outcome(action="off", successful=True, message="Turned off")

    action__off.capability = {
        "param": "off",
        "description": "Stops any fades or sequences. Quickly Fades the RGB strip to black (no light)",
        "value": "",
    }

    def action__preset(self, request):
        """
        Runs a named preset based upon its slug
        :param request:
        :return:
        """
        preset_name = request.get_param(["preset", "pre", "pst"], default="", force=six.text_type)
        if not preset_name.strip():
            return self.outcome(action="preset", successful=False, message="No preset name supplied in request params.")
        for preset_section_name, preset_section in self.PRESETS.items():
            for preset in preset_section:
                preset_slug = getattr(preset, "slug", None)
                if not preset_slug:
                    continue
                if preset_slug.lower() == slugify(preset_name):
                    return self.run_preset(request, preset)
        return self.outcome(action="preset", successful=False, message="Could not find a preset by the name '{}'.", message_args=[preset_name])

    action__preset.capability = {
        "param": "preset",
        "description": "Activates the preset by name.",
        "value": "A string corresponding to the slug name of the preset you wish to run.",
        "validity": "<slug> lower case a-z, underscore and hyphen characters only.",
        "options": get_presets_as_options(PRESETS),
        "returns": "<unicode> The first hex value of sequence."
    }

    def run_preset(self, request, preset_instance):
        """
        Runs the given preset_instance
        :param request: The request
        :param preset_instance: The preset we wish to run
        :return:
        """
        preset_kwargs = getattr(preset_instance, "kwargs") or {}
        if not preset_kwargs:  # Skip invalid presets
            return self.outcome(action="preset", successful=False, message="Preset '{}' is misconfigured. It does not have any kwargs.", message_args=[preset_instance.slug])
        for _alias, possible_preset_action in self.PRESET_FUNCTIONS:
            this_preset_action_value = preset_instance.kwargs.get(possible_preset_action, NOT_SET)
            if not this_preset_action_value:
                continue  # This action isn't in the preset kwargs
            # Otherwise inject the preset kwargs into the request as replacement params and send them in.
            # This allows us to read the preset kwargs just as though they cam in via a request
            request.replace_params(preset_kwargs)
            action_func = getattr(self, "action__{}".format(possible_preset_action))  # Should NEVER cause an AttributeError. If is does, your self.PRESET_FUNCTIONS are misconfigured.
            return action_func(request)
        return self.outcome(action="preset", successful=False, message="Selected preset '{}' does not map to an action.",
                            message_args=[preset_instance.label])

    def information__status(self, request, *args, **kwargs):
        """
        Reports the status of the RGB LED strip, flushed into the return state of every action call.
        """
        current_rgb_readable = "({})".format(self.led_strip)
        current_rgb = self.led_strip.rgb
        current_hex = self.led_strip.hex
        current_hsv = self.led_strip.hsv
        current_hs = current_hsv[:2]
        current_kelvin = self.led_strip.kelvin
        current_kelvin_readable = self.led_strip.kelvin_readable
        contrast_colour_hex = self.led_strip.contrast_from_bg(current_hex, dark_default="202020")
        contrast_colour = contrast_colour_hex
        contrast_colour_rgb = self.led_strip.hex_to_rgb(contrast_colour)
        return {
            "sequence": self.led_strip.sequence_colours,
            "current_hex": current_hex,
            "current": current_rgb_readable,
            "current_colour": current_rgb_readable,
            "current_rgb": current_rgb,
            "current_rgb_readable": current_rgb_readable,
            "contrast": contrast_colour,
            "contrast_colour": contrast_colour,
            "contrast_colour_rgb": contrast_colour_rgb,
            "current_hsv": current_hsv,
            "current_hs": current_hs,
            "current_kelvin": current_kelvin,
            "current_kelvin_readable": current_kelvin_readable
        }

    def teardown(self):
        """
        Called automatically when exiting the parent reactor
        """
        self.led_strip.teardown()


class NotSet:

    def __bool__(self):
        return False

    def __nonzero__(self):
        return self.__bool__()


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
    replacement_params = None

    def __init__(self, *args, **kwargs):
        super(SmartRequest, self).__init__(*args, **kwargs)

    def get_param_values(self, name, default=None):
        """
        Failsafe way of getting querystring get and post params from the Request object
        If not provided, will return default.

        Code can "modify" the apparent params that get returned through replace_params(), though the originals are preserved as a fallback.
        
        @return: ["val1","val2"] LIST of arguments, or the default
        """
        if self.replacement_params is not None:
            try:
                out = self.replacement_params[six.ensure_text(name, encoding="utf-8")]
                return out
            except (TypeError, IndexError) as e:
                logger.warning("{}: {}", e.__class__.__name__, e)
            except KeyError:
                pass
        found_items_bytes = self.args.get(six.ensure_binary(name, encoding="utf-8"), NOT_SET)
        if found_items_bytes is NOT_SET:
            return default
        found_items_unicode = []
        for item_bytes in found_items_bytes:
            item_unicode = six.ensure_text(item_bytes, encoding="utf-8")
            found_items_unicode.append(item_unicode)
        return found_items_unicode

    get_params = get_param_values  # Alias
    get_list = get_param_values  # Alias
    get_params_list = get_param_values  # Alias

    def get_param(self, names, default=None, force=None):
        """
        Failsafe way of getting a single querystring value. Will only return one (the first) value if found
        
        @param names: <str> The name of the param to fetch, or a list of candidate names to try
        @keyword default: The default value to return if we cannot get a valid value
        @keyword force: <type> A class / type to force the output into. Default is returned if we cannot force the value into this type 
        """
        if isinstance(names, (six.text_type, six.binary_type)):
            names = [names]
        val = NOT_SET
        for name in names:
            val = self.get_param_values(name=name, default=NOT_SET)
            if val is not NOT_SET:  # Once we find a valid value, continue
                break
        # If we have no valid value, then bail
        if val is NOT_SET:
            return default
        try:
            if len(val) == 1:
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
            if self.replacement_params is not None:
                try:
                    return self.replacement_params[param_name]
                except (KeyError, IndexError, TypeError):
                    pass
            try:
                return self.args[six.ensure_binary(param_name, encoding="utf-8")] or True
            except KeyError:
                pass
        return False

    has_param = has_params
    has_key = has_params

    def replace_param(self, name, value):
        """
        Flush in a "replacement" to the get querystrings
        :param name: the key of this param
        :param value: the value. Will get listified so that it simulates self.args.get() because multiple values are allowed for one key in a querystring.
        :return: self for chaining
        """
        self.replacement_params = self.replacement_params or OrderedDict()
        self.replacement_params[six.ensure_text(name, encoding="utf-8")] = [value]  # Turned into an iterable.
        return self

    def replace_params(self, *args, **kwargs):
        """
        Flush in a "replacement" to the get querystrings

        :return: self for chaining
        """
        if not kwargs:
            try:
                params_dict = args[0]
            except IndexError:
                params_dict = OrderedDict()
        else:
            params_dict = OrderedDict(kwargs)
        for k, v in params_dict.items():
            self.replace_param(k, v)
        return self

    def __getitem__(self, name):
        """
        Lazy way of getting a param list, with the fallback default being None 
        """
        return self.get_param(name)


class RaspiledControlSite(Site, object):
    """
    Site thread which initialises the RaspiledControlResource properly
    """
    ip_address = None

    def __init__(self, *args, **kwargs):
        resource = kwargs.pop("resource", RaspiledControlResource())
        super(RaspiledControlSite, self).__init__(resource=resource, requestFactory=SmartRequest, *args, **kwargs)

    def buildProtocol(self, addr):
        self.ip_address = addr
        self.resource.ip_address = addr
        return super(RaspiledControlSite, self).buildProtocol(addr)

    def setup_broadcasting(self, reactor):
        self.resource.setup_broadcasting(reactor)

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
    # Get all matching PIDs
    try:
        pids_str = check_output(["pidof", name])
    except CalledProcessError:  # No matches
        pids_str = ""
    # Process string-list into python list
    pids = pids_str.strip().split(" ")
    # Remove self if required:
    if exclude_self:
        my_pid = str(os.getpid())  # Own PID - getpid() returns integer
        try:
            pids.remove(my_pid)  # Remove my PID string:
        except ValueError:
            pass
    return pids


def checkClientAgainstWhitelist(ip, user, token):
    IPS = {
        'IP1': '127.0.0.1',
    }

    config_path = os.path.expanduser(RASPILED_DIR + '/.whitelist')
    parser = configparser.ConfigParser(defaults=IPS)

    if os.path.exists(config_path):
        parser.read(config_path)
    else:
        with open(config_path, 'w') as f:
            parser.write(f)

    connection = False
    whitelist = parser.defaults()
    for ii in whitelist.keys():
        if ip == whitelist[ii]:
            logger.info('Client registered')
            connection = True
            break
        else:
            connection = False
    return connection


def start_if_not_running():
    """
    Checks if the process is running, if not, starts it!
    """
    pids = get_matching_pids(APP_NAME, exclude_self=True)  # Will remove own PID
    pids = list(filter(bool, pids))
    if not pids:  # No match! Implies we need to fire up the listener
        logger.info("[STARTING] Raspiled Listener with PID %s" % str(os.getpid()))
        # First the web
        factory = RaspiledControlSite(timeout=8)  # 8s timeout
        try:
            pi_port = int(RESOLVED_USER_SETTINGS.get('pi_port', 9090))
        except (TypeError, ValueError):
            raise ConfigurationError("You have an invalid value for 'pi_port' in your settings. This needs to be a valid port number (integer).")
        endpoint = endpoints.TCP4ServerEndpoint(reactor, pi_port)
        endpoint.listen(factory)
        # factory.setup_broadcasting(reactor)  # Uncomment to broadcast stuff over network!
        reactor.run()
    else:
        logger.info("Raspiled Listener already running with PID %s" % ", ".join(pids))


if __name__ == "__main__":
    start_if_not_running()
