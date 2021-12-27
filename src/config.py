"""
Raspiled - Config
"""
import configparser
import logging
import os


logging.basicConfig(format='[%(asctime)s RASPILED] %(message)s',
                    datefmt='%H:%M:%S', level=logging.INFO)


def ordereddict_to_int(ordered_dict):
    """
    Converts an OrderedDict with str values to integers and/or floats (port and pins).
    @param ordered_dict: <OrderedDict> containg RASPILED configuration.

    @returns: <OrderedDict> with integers instead of str values.
    """
    for key,value in ordered_dict.items():
        if "." in value:
            casting_function = float
        else:
            casting_function = int
        try:
            ordered_dict[key] = casting_function(value)
        except (TypeError, ValueError):
            pass
    return ordered_dict


Odict2int = ordereddict_to_int  # ALIAS


RASPILED_DIR = os.path.dirname(os.path.realpath(__file__))  # The directory we're running in

DEFAULTS = {
    'config_path': RASPILED_DIR,
    'pi_host': 'localhost',
    'pi_port': 9090,  # the port our web server listens on (192.168.0.33:<pi_port>)
    'pig_port': 8888,  # the port pigpio daemon is listening on for pin control commands
    'latitude': 52.2053,  # If you wish to sync your sunrise/sunset to the real sun, enter your latitude as a decimal
    'longitude': 0.1218,  # If you wish to sync your sunrise/sunset to the real sun, enter your longitude as a decimal

    # Initial default values for your output pins. You can override them in your raspiled.conf file
    'red_pin': '27',
    'green_pin': '17',
    'blue_pin': '22',

    # Relative intensity correction for your colour channels
    'calibrate_r': 1.0,
    'calibrate_g': 0.63,
    'calibrate_b': 1.0,

    # Debug
    "debug": 0
}


config_path = os.path.expanduser(RASPILED_DIR + '/raspiled.conf')
parser = configparser.ConfigParser(defaults=DEFAULTS)
params = {}

if os.path.exists(config_path):
    logging.info('Using config file: {}'.format(config_path))
    parser.read(config_path)
    params = ordereddict_to_int(parser.defaults())
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
            raise RuntimeError(
                "*** You cannot have the web server running on port {} while the pigpio daemon is also running on that port! ***".format(DEFAULTS["pi_port"]))
    except RuntimeError as e:
        logging.warn(e)
    except (ValueError, TypeError):
        logging.warn("*** You have specified an invalid port number for the Raspiled web server ({}) or the Pigpio daemon ({}) ***".format(DEFAULTS["pi_port"],
                                                                                                                                           DEFAULTS[
                                                                                                                                               "pig_port"]))
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
    params = ordereddict_to_int(parser.defaults())


CONFIG = params


def get_setting(name, default=None):
    """
    Return the setting from the config. If it doesn't exist,
    will check the defaults dict, and then finally fallback
    to the default.
    :param name:
    :param default:
    :return:
    """
    return params.get(name, DEFAULTS.get(name, default))


get_settings = get_setting
get_config = get_setting


DEBUG = get_setting("debug", False)

