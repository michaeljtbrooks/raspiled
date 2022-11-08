"""
    Raspi Seamless Project:

    A collection of base classes and utilities for the Raspberry Pi powered elements of the Seamless project.
"""
from __future__ import unicode_literals
from collections import OrderedDict
from copy import copy
import json
import logging
import os
from socket import SOL_SOCKET, SO_BROADCAST

import six
from twisted.internet import task
from twisted.internet.protocol import DatagramProtocol
from twisted.web.resource import Resource
from twisted.web.static import File

from src.config import DEBUG


RASPBERRY_PI_DIR = os.path.dirname(os.path.realpath(__file__)) #The directory we're running in


def D(item="", *args, **kwargs):
    if DEBUG:
        if args or kwargs:
            try:
                item = item.format(*args, **kwargs)
                print(item)
            except IndexError:
                item = "{} {} {}".format(item, args, kwargs)
                print("D_FORMAT_ERROR: {}".format(item))
        logging.debug(item)


class NotImplementedError(Exception):
    """
    This method is not implemented.
    """
    pass


class ConfigurationError(RuntimeError):
    """
    When someone has codged up the config
    """
    pass


class RaspberryPiWebResource(Resource):
    """
    Provides a web server and responsive JSON API.

        Actions do something and generate a Python object which will become a JSON object
        Renderers generate an HTML web page for a human being to see
    """
    PARAM_TO_INFORMATION_MAPPING = (
        ("capabilities", "capabilities"),  # Docs
        ("capability", "capabilities"),  # Docs
        ("status", "status"),  # Status
    )
    PARAM_TO_ACTION_MAPPING = (
    )
    TEMPLATE_INDEX = "index.html"
    TEMPLATES_DIRECTORY = "templates"
    STATIC_DIRECTORY = "static"  # Always at http://whatever.your.ip.is:port/static/
    BROADCAST_INTERVAL_SECONDS = 15  # Number of seconds between each broadcast
    BROADCAST_PORT = 1900  # Port to broadcast to other devices on (SSDP = 1900)
    BROADCAST_ADDR = "239.255.255.250"  # IP to broadcast to other devices

    broadcaster = None  # How we tell the world about our existence
    broadcast_task = None  # Where we store our broadcasting task (looping task)
    ip_address = None  # I can be told where I lurk!

    _cached_capabilities = None  # Saves us regenerating the resource dict every time
    _cached_json = None

    isLeaf = False  # Allows us to go into dirs
    _path = None  # If a user wants to hit a dynamic subpage, the path appears here

    def __init__(self, *args, **kwargs):
        """
        Sets this web responding engine up
        """
        Resource.__init__(self, *args, **kwargs)  # Super
        # Add in the static folder.
        static_folder = os.path.join(RASPBERRY_PI_DIR, self.STATIC_DIRECTORY)
        self.putChild(b"static", File(static_folder))  # Any requests to /static serve from the filesystem.

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

    @property
    def clean_path(self):
        """
        Provides a clean version of the path
        :return: <str>
        """
        return six.text_type(self._path or u"").rstrip("/")

    def before_action(self, *args, **kwargs):
        """
        Does something before a valid (non-documentation) action
        Override this if you want something to happen before an action is called
        """
        return None

    def after_action(self, *args, **kwargs):
        """
        Does something after a valid (non-documentation) action
        Override this if you want something to happen after an action is called (does not affect the output)
        """
        return None

    def information__capabilities(self, *args, **kwargs):
        """
        Reports this listener's capabilities
        """
        if self._cached_capabilities is None:
            status_docs = self.information__status__capability
            output_capabilities = [status_docs]
            for function_name in dir(self):
                if function_name.startswith("action__"):
                    param_name = function_name.replace("action__", "")
                    try:
                        capability_details = getattr(self, function_name).capability
                    except AttributeError:
                        capability_details = {
                            "param": param_name,
                            "description": None
                        }
                    output_capabilities.append(capability_details)
            self._cached_capabilities = output_capabilities
        return self._cached_capabilities

    def information__status(self, request, *args, **kwargs):
        """
        Reports the status of the RGB LED strip.

        By default, adds nothing to the context
        """
        out_dict = {}
        out_dict.update(kwargs)
        return out_dict
    information__status__capability = {
        "param": "status",
        "description": "Reports this device's current status.",
        "value": "",
        "returns": "<JSON> A JSON object for its status"
    }

    @classmethod
    def render_json(cls, request, context=None, http_code=200):
        """
        Renders a context object into JSON
        :param request: <SmartRequest>
        :param context: A python object to JSONify
        :param http_code: <int> The status code of the web response
        :return: rendered valid JSON in utf8
        """
        try:
            request.setHeader("Content-Type", "application/json; charset=utf-8")
            output = json.dumps(context)
        except (TypeError, ValueError):
            output = b"Raspiled generated invalid JSON data!"
            http_code = 500
        request.setResponseCode(http_code)
        return output.encode("utf-8")

    def render_json_with_status(self, request, context=None, http_code=200):
        """
        Renders output JSON, but with the current status flushed in too
        :param request: <SmartRequest>
        :param context: A python object. If a dict, will be updated with status. If not a dict, will add {"output": <Context object>} to the JSON dict
        :return: rendered valid JSON in utf8
        """
        status = self.information__status(request)
        print("Status: {}".format(status))
        original_context = copy(context)
        real_context = OrderedDict()
        try:
            real_context.update(status)
        except (ValueError, TypeError):  # Means status isn't a dict-like object
            real_context["status"] = status
        if original_context is not None:
            try:
                real_context.update(original_context)
            except (ValueError, TypeError):  # Means original_context was not dict-like
                real_context["output"] = original_context
        return self.render_json(request, context=real_context, http_code=http_code)

    @classmethod
    def render_html(cls, request, template, context=None, http_code=200):
        """
        Renders a given template with the data in context
        :param request: <SmartRequest>
        :param template: <str> The filename of the template file to render (should sit in ./templates/)
        :param context: {} a dict of variables to pass to the template
        :return: HTML, utf8 encoded
        """
        if context is None:
            context = {}

        request.setHeader("Content-Type", "text/html; charset=utf-8")
        request.setResponseCode(http_code)
        htmlstr = ""
        template_file_path = os.path.join(RASPBERRY_PI_DIR, "templates", template)

        with open(template_file_path) as html_template:
            htmlstr = html_template.read()

        return htmlstr.format(**context).encode('utf-8')

    def render_controls(self, request, context=None):
        """
        Renders the index page (controls) for this device
        :param request: <SmartRequest>
        :keyword context: {} A dict of data to push into the template file
        :return: A rendered HTML template
        """
        if context is None:
            context = {}
        latest_status_dict = self.information__status(request)
        context.update(latest_status_dict)
        return self.render_html(request, self.TEMPLATE_INDEX, context)

    def render_network(self, request, context=None):
        """
        Renders links to other devices discovered on your network
        By default, just returns your local controls

        :param request: <SmartRequest>
        :keyword context: {} A dict of data to push into the template file
        :return: A rendered HTML template
        """
        # TODO: Write this!

    def render_GET(self, request):
        """
        MAIN WEB PAGE ENTRY POINT!
        :param request:
        :return: HTML or JSON for serving via Twisted web browser
        """
        clean_path = six.text_type(self._path or u"").rstrip("/")

        # First see if we're being asked for an informational resource
        for key_name, information_name in self.PARAM_TO_INFORMATION_MAPPING:
            if request.has_param(key_name) or clean_path == key_name:
                func_name = "information__%s" % information_name
                output_context = getattr(self, func_name)(request)
                return self.render_json(request, context=output_context)

        # Next see if we're being asked for an action resource
        for key_name, action_name in self.PARAM_TO_ACTION_MAPPING:
            if request.has_param(key_name) or clean_path == key_name:
                self.before_action(action_name)  # Inheriting classes can do stuff before the action
                func_name = "action__%s" % action_name
                output_context = getattr(self, func_name)(request)  # The actual action
                self.after_action(action_name)  # Inheriting classes can do stuff after the action
                return self.render_json_with_status(request, context=output_context)

        # Finally, assume the user wants to retrieve an HTML page
        # This may be to see what's on their network
        if request.has_param("network") or clean_path == "network":
            return self.render_network(request)

        # Or it's to show the controls
        return self.render_controls(request)

    def setup_broadcasting(self, reactor):
        """
        Hooks the reactor up to a transport to permit broadcasting
        :param reactor:
        :return:
        """
        self.broadcaster = BroadcastCapabilitiesProtocol()  # For broadcasting my presence
        reactor.listenUDP(0, self.broadcaster)
        self.broadcast_task = task.LoopingCall(self.broadcast_presence)
        self.broadcast_task.start(self.BROADCAST_INTERVAL_SECONDS)

    def whoami(self):
        """
        Returns a dict saying who I am (what service I am, where I am etc)
        :return: {}
        """
        my_ip = None

    def broadcast_presence(self):
        """
        Simply announces own presence onto the network
        See scheduling tasks in twisted: https://twistedmatrix.com/documents/13.1.0/core/howto/time.html
        :return: None
        """
        try:
            cached_json = getattr(self, "_cached_json", None)
            if cached_json is None:
                whoami = "WHOAMI"
                cached_json = json.dumps(whoami)
                self._cached_json = cached_json
            self.broadcaster.broadcast_message(message_json=cached_json, broadcast_address=self.BROADCAST_ADDR, broadcast_port=self.BROADCAST_PORT)
        except Exception as e:
            print(e)


class BroadcastCapabilitiesProtocol(DatagramProtocol):
    """
    Allows a RaspberryPi resource to broadcast its presence on the network, including what it can do.
    Other protocols will use this to discover other devices on the network.
    """
    def startProtocol(self):
        """
        Sets up the broadcast protocol
        :return: None
        """
        self.transport.socket.setsockopt(SOL_SOCKET, SO_BROADCAST, True)

    def broadcast_message(self, message_json, broadcast_address="235.255.255.250", broadcast_port=1900):
        """
        Takes the WebResourceClass, tells everyone else on the network that it's here and what it can do
        :return: None
        """
        self.transport.write(message_json, (broadcast_address, broadcast_port))
        print("Broadcast: {}".format(message_json))



