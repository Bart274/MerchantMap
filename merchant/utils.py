import sys
import os
import json
import logging
import re
import time
import socket
import struct

import psutil
import subprocess
import requests
import configargparse

from s2sphere import CellId, LatLng
from requests_futures.sessions import FuturesSession
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from haversine import haversine
from pprint import pformat
from time import strftime
from timezonefinder import TimezoneFinder

log = logging.getLogger(__name__)
tf = TimezoneFinder()

LATLNG_PATTERN = re.compile(r"^(-?\d+\.\d+),?\s?(-?\d+\.\d+)$")


def memoize(function):
    memo = {}

    def wrapper(*args):
        if args in memo:
            return memo[args]
        else:
            rv = function(*args)
            memo[args] = rv
            return rv

    return wrapper


@memoize
def get_args():
    # Pre-check to see if the -cf or --config flag is used on the command line.
    # If not, we'll use the env var or default value. This prevents layering of
    # config files as well as a missing config.ini.
    defaultconfigfiles = []
    if "-cf" not in sys.argv and "--config" not in sys.argv:
        defaultconfigfiles = [
            os.getenv("MERCHANTMAP_CONFIG", os.path.join(os.path.dirname(__file__), "../config/config.ini"))
        ]
    parser = configargparse.ArgParser(default_config_files=defaultconfigfiles, auto_env_var_prefix="MERCHANTMAP_")
    parser.add_argument("-cf", "--config", is_config_file=True, help="Set configuration file")
    parser.add_argument("-scf", "--shared-config", is_config_file=True, help="Set a shared config")
    parser.add_argument("-l", "--location", help="Location, can be an address or coordinates.")
    # Default based on the average elevation of cities around the world.
    # Source: https://www.wikiwand.com/en/List_of_cities_by_elevation
    parser.add_argument("-alt", "--altitude", help="Default altitude in meters.", type=int, default=507)
    parser.add_argument("-altv", "--altitude-variance", help="Variance for --altitude in meters", type=int, default=1)
    parser.add_argument(
        "-uac",
        "--use-altitude-cache",
        help="Query the Elevation API for each step, rather than only once, and store results in the database.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-al", "--access-logs", help="Write web logs to access.log.", action="store_true", default=False
    )
    parser.add_argument("-H", "--host", help="Set web server listening host.", default="127.0.0.1")
    parser.add_argument("-P", "--port", type=int, help="Set web server listening port.", default=5000)
    parser.add_argument(
        "-eh", "--external-hostname", help="Hostname used for external requests.", default="http://127.0.0.1:5000"
    )
    parser.add_argument("-c", "--china", help="Coordinates transformer for China.", action="store_true")
    parser.add_argument(
        "-k",
        "--gmaps-key",
        help="Google Maps Javascript API Key. Required unless --map-provider is 'leaflet'.",
    )
    parser.add_argument(
        "--map-provider",
        help="Which map renderer to serve the frontend with.",
        choices=["google", "leaflet"],
        default="google",
    )
    parser.add_argument(
        "-ms",
        "--map-security",
        help="Shared Secrets that are needed to send data to the map.",
        default=[],
        action="append",
    )
    parser.add_argument("-C", "--cors", help="Enable CORS on web server.", action="store_true", default=False)
    parser.add_argument(
        "-cd",
        "--clear-db",
        help="Deletes the existing database before starting the Webserver.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-nba",
        "--no-accounts",
        help="Disables Accounts from the map (including parsing them into local db).",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-nbl",
        "--no-locations",
        help="Disables Locations from the map (including parsing them into local db).",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "-mo",
        "--map-only",
        help="Disables input endpoints from the map.",
        action="store_true",
        default=False,
    )
    parser.add_argument("-px", "--proxy", help="Proxy url (e.g. socks5://127.0.0.1:9050)", action="append")
    parser.add_argument(
        "-pxsc",
        "--proxy-skip-check",
        help="Disable checking of proxies before start.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-pxt", "--proxy-test-timeout", help="Timeout settings for proxy checker in seconds.", type=int, default=5
    )
    parser.add_argument(
        "-pxre",
        "--proxy-test-retries",
        help="Number of times to retry sending proxy test requests on failure.",
        type=int,
        default=0,
    )
    parser.add_argument(
        "-pxbf",
        "--proxy-test-backoff-factor",
        help="Factor (in seconds) by which the delay until next retry will increase.",
        type=float,
        default=0.25,
    )
    parser.add_argument("-pxc", "--proxy-test-concurrency", help="Async requests pool size.", type=int, default=0)
    parser.add_argument(
        "-pxd",
        "--proxy-display",
        help="Display info on which proxy being used (index or full). To be used with -ps.",
        type=str,
        default="index",
    )
    parser.add_argument(
        "-pxf",
        "--proxy-file",
        help="Load proxy list from text file (one proxy per line), overrides -px/--proxy.",
    )
    parser.add_argument(
        "-pxr",
        "--proxy-refresh",
        help="Period of proxy file reloading, in seconds. Works only with -pxf/--proxy-file. (0 to disable).",
        type=int,
        default=0,
    )
    parser.add_argument(
        "-pxo",
        "--proxy-rotation",
        help="Enable proxy rotation with account changing for search threads (none/round/random).",
        type=str,
        default="round",
    )
    parser.add_argument(
        "-jit",
        "--jitter",
        help="Apply jitter to coordinates for teleport scheduling",
        action="store_true",
        default=True,
    )
    parser.add_argument("-mn", "--mapname", help="Name for the map in the HTML", type=str, default="MerchantMap")
    parser.add_argument(
        "--image-base-domain", help="Domain for the image base", type=str, default="merchantthegame.com"
    )

    group = parser.add_argument_group("Database")
    group.add_argument("--db-name", help="Name of the database to be used.", required=True)
    group.add_argument("--db-user", help="Username for the database.", required=True)
    group.add_argument("--db-pass", help="Password for the database.", required=True)
    group.add_argument("--db-host", help="IP or hostname for the database.", default="127.0.0.1")
    group.add_argument("--db-port", help="Port for the database.", type=int, default=3306)
    group.add_argument(
        "--db-threads", help="Number of db threads; increase if the db queue falls behind.", type=int, default=1
    )
    group = parser.add_argument_group("Database Cleanup")
    group.add_argument(
        "-DC", "--db-cleanup", help="Enable regular database cleanup thread.", action="store_true", default=False
    )
    parser.add_argument("--ssl-certificate", help="Path to SSL certificate file.")
    parser.add_argument("--ssl-privatekey", help="Path to SSL private key file.")
    parser.add_argument(
        "-ps",
        "--print-status",
        help=(
            "Show a status screen instead of log messages. Can switch between status and "
            + "logs by pressing enter.  Optionally specify 'logs' to startup in logging mode."
        ),
        nargs="?",
        const="status",
        default=False,
        metavar="logs",
    )
    parser.add_argument(
        "-slt", "--stats-log-timer", help="In log view, list per hr stats every X seconds", type=int, default=0
    )
    parser.add_argument(
        "-odt",
        "--on-demand_timeout",
        help="Pause searching while web UI is inactive for this timeout (in seconds).",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--disable-blacklist",
        help="Disable the global anti-scraper IP blacklist.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-tp",
        "--trusted-proxies",
        default=[],
        action="append",
        help="Enables the use of X-FORWARDED-FOR headers to identify the IP of clients connecting through these trusted proxies.",
    )
    parser.add_argument(
        "--no-file-logs",
        help="Disable logging to files. Does not disable --access-logs.",
        action="store_true",
        default=False,
    )
    parser.add_argument("--log-path", help="Defines directory to save log files to.", default="logs/")
    parser.add_argument(
        "--log-filename",
        help=(
            "Defines the log filename to be saved. Allows date formatting, and replaces <SN> with the instance's status name."
            " Read the python time module docs for details. Default: %%Y%%m%%d_%%H%%M_<SN>.log."
        ),
        default="%Y%m%d_%H%M_<SN>.log",
    ),
    parser.add_argument(
        "--dump",
        help="Dump censored debug info about the environment and auto-upload to hastebin.com.",
        action="store_true",
        default=False,
    )
    verbose = parser.add_mutually_exclusive_group()
    verbose.add_argument(
        "-v",
        help="Show debug messages from MerchantMap. Can be repeated up to 3 times.",
        action="count",
        default=0,
        dest="verbose",
    )
    verbose.add_argument("--verbosity", help="Show debug messages from MerchantMap.", type=int, dest="verbose")
    parser.set_defaults(DEBUG=False)

    args = parser.parse_args()

    # Allow status name and date formatting in log filename.
    args.log_filename = strftime(args.log_filename)

    if args.location is None:
        parser.print_usage()
        print((sys.argv[0] + ": error: arguments -l/--location is required."))
        sys.exit(1)

    is_address = not LATLNG_PATTERN.match(args.location)
    needs_gmaps_key = args.map_provider == "google" or is_address
    if not args.gmaps_key and needs_gmaps_key:
        parser.print_usage()
        print(
            (
                sys.argv[0]
                + ": error: argument -k/--gmaps-key is required unless\n"
                + "--map-provider is 'leaflet' and --location is given as\n"
                + "'lat,lng' coordinates (geocoding an address still needs it)."
            )
        )
        sys.exit(1)

    args.locales_dir = "static/dist/locales"
    args.data_dir = "static/dist/data"

    return args


def now():
    # The fact that you need this helper...
    return int(time.time())


# Gets the seconds past the hour.
def cur_sec():
    return (60 * time.gmtime().tm_min) + time.gmtime().tm_sec


# Gets the total seconds past the hour for a given date.
def date_secs(d):
    return d.minute * 60 + d.second


# Checks to see if test is between start and end accounting for hour
# wraparound.
def clock_between(start, test, end):
    return (start <= test <= end and start < end) or (not (end <= test <= start) and start > end)


# Return the s2sphere cellid token from a location.
def cellid(loc):
    return int(CellId.from_lat_lng(LatLng.from_degrees(loc[0], loc[1])).to_token(), 16)


# Return approximate distance in meters.
def distance(pos1, pos2):
    return haversine((tuple(pos1))[0:2], (tuple(pos2))[0:2])


def degrees_to_cardinal(d):
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = int((d + 11.25) / 22.5 - 0.02)
    return dirs[ix % 16]


# Return True if distance between two locs is less than distance in meters.
def in_radius(loc1, loc2, radius):
    return distance(loc1, loc2) < radius


def i8ln(word):
    if not hasattr(i8ln, "dictionary"):
        args = get_args()
        file_path = os.path.join(args.root_path, args.locales_dir, "{}.min.json".format("en"))
        if os.path.isfile(file_path):
            with open(file_path, "r") as f:
                i8ln.dictionary = json.loads(f.read())
        else:
            # If locale file is not found we set an empty dict to avoid
            # checking the file every time, we skip the warning for English as
            # it is not expected to exist.
            i8ln.dictionary = {}
    if word in i8ln.dictionary:
        return i8ln.dictionary[word]
    else:
        return word


# Thread function for periodical enc list updating.
def dynamic_loading_refresher(file_list):
    # We're on a 60-second timer.
    refresh_time_sec = 60

    while True:
        # Wait (x-1) seconds before refresh, min. 1s.
        time.sleep(max(1, refresh_time_sec - 1))

        for arg_type, filename in list(file_list.items()):
            try:
                if filename:
                    # Only refresh if the file has changed.
                    current_time_sec = time.time()
                    file_modified_time_sec = os.path.getmtime(filename)
                    time_diff_sec = current_time_sec - file_modified_time_sec

                    # File has changed in the last refresh_time_sec seconds.
                    if time_diff_sec < refresh_time_sec:
                        args = get_args()
                        with open(filename) as f:
                            new_list = frozenset([int(l.strip()) for l in f])
                            setattr(args, arg_type, new_list)
                            log.info("New %s is: %s.", arg_type, new_list)
                    else:
                        log.debug("No change found in %s.", filename)
            except Exception as e:
                log.exception("Exception occurred while" + " updating %s: %s.", arg_type, e)


def dottedQuadToNum(ip):
    return struct.unpack("!L", socket.inet_aton(ip))[0]


# Get a future_requests FuturesSession that supports asynchronous workers
# and retrying requests on failure.
# Setting up a persistent session that is re-used by multiple requests can
# speed up requests to the same host, as it'll re-use the underlying TCP
# connection.
def get_async_requests_session(num_retries, backoff_factor, pool_size, status_forcelist=None):
    # Use requests & urllib3 to auto-retry.
    # If the backoff_factor is 0.1, then sleep() will sleep for [0.1s, 0.2s,
    # 0.4s, ...] between retries. It will also force a retry if the status
    # code returned is in status_forcelist.
    if status_forcelist is None:
        status_forcelist = [500, 502, 503, 504]
    session = FuturesSession(max_workers=pool_size)

    # If any regular response is generated, no retry is done. Without using
    # the status_forcelist, even a response with status 500 will not be
    # retried.
    retries = Retry(total=num_retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist)

    # Mount handler on both HTTP & HTTPS.
    session.mount("http://", HTTPAdapter(max_retries=retries, pool_connections=pool_size, pool_maxsize=pool_size))
    session.mount("https://", HTTPAdapter(max_retries=retries, pool_connections=pool_size, pool_maxsize=pool_size))

    return session


# Get common usage stats.
def resource_usage():
    platform = sys.platform
    proc = psutil.Process()

    with proc.oneshot():
        cpu_usage = psutil.cpu_times_percent()
        mem_usage = psutil.virtual_memory()
        net_usage = psutil.net_io_counters()

        usage = {
            "platform": platform,
            "PID": proc.pid,
            "MEM": {
                "total": mem_usage.total,
                "available": mem_usage.available,
                "used": mem_usage.used,
                "free": mem_usage.free,
                "percent_used": mem_usage.percent,
                "process_percent_used": proc.memory_percent(),
            },
            "CPU": {
                "user": cpu_usage.user,
                "system": cpu_usage.system,
                "idle": cpu_usage.idle,
                "process_percent_used": proc.cpu_percent(interval=1),
            },
            "NET": {
                "bytes_sent": net_usage.bytes_sent,
                "bytes_recv": net_usage.bytes_recv,
                "packets_sent": net_usage.packets_sent,
                "packets_recv": net_usage.packets_recv,
                "errin": net_usage.errin,
                "errout": net_usage.errout,
                "dropin": net_usage.dropin,
                "dropout": net_usage.dropout,
            },
            "connections": {"ipv4": len(proc.connections("inet4")), "ipv6": len(proc.connections("inet6"))},
            "thread_count": proc.num_threads(),
            "process_count": len(psutil.pids()),
        }

        # Linux only.
        if platform == "linux" or platform == "linux2":
            usage["sensors"] = {"temperatures": psutil.sensors_temperatures(), "fans": psutil.sensors_fans()}
            usage["connections"]["unix"] = len(proc.connections("unix"))
            usage["num_handles"] = proc.num_fds()
        elif platform == "win32":
            usage["num_handles"] = proc.num_handles()

    return usage


# Log resource usage to any logger.
def log_resource_usage(log_method):
    usage = resource_usage()
    log_method("Resource usage: %s.", usage)


# Generic method to support periodic background tasks. Thread sleep could be
# replaced by a tiny sleep, and time measuring, but we're using sleep() for
# now to keep resource overhead to an absolute minimum.
def periodic_loop(f, loop_delay_ms):
    while True:
        # Do the thing.
        f()
        # zZz :bed:
        time.sleep(loop_delay_ms / 1000)


# Periodically log resource usage every 'loop_delay_ms' ms.
def log_resource_usage_loop(loop_delay_ms=60000):
    # Helper method to log to specific log level.
    def log_resource_usage_to_debug():
        log_resource_usage(log.debug)

    periodic_loop(log_resource_usage_to_debug, loop_delay_ms)


# Return shell call output as string, replacing any errors with the
# error's string representation.
def check_output_catch(command):
    try:
        result = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
    except Exception as ex:
        result = "ERROR: " + ex.output.replace(os.linesep, " ")
    finally:
        return result.strip()


# Automatically censor all necessary fields. Lists will return their
# length, all other items will return 'empty_tag' if they're empty
# or 'censored_tag' if not.
def _censor_args_namespace(args, censored_tag, empty_tag):
    fields_to_censor = [
        "proxy",
        "config",
        "db",
        "proxy_file",
        "log_path",
        "log_filename",
        "encrypt_lib",
        "ssl_certificate",
        "ssl_privatekey",
        "location",
        "external_hostname",
        "host",
        "port",
        "gmaps_key",
        "db_name",
        "db_user",
        "db_pass",
        "db_host",
        "db_port",
        "trusted_proxies",
        "data_dir",
        "locales_dir",
        "shared_config",
    ]

    for field in fields_to_censor:
        # Do we have the field?
        if field in args:
            value = args[field]

            # Replace with length of list or censored tag.
            if isinstance(value, list):
                args[field] = len(value)
            else:
                if args[field]:
                    args[field] = censored_tag
                else:
                    args[field] = empty_tag

    return args


# Get censored debug info about the environment we're running in.
def get_censored_debug_info():
    CENSORED_TAG = "<censored>"
    EMPTY_TAG = "<empty>"
    args = _censor_args_namespace(vars(get_args()), CENSORED_TAG, EMPTY_TAG)

    # Get git status.
    status = check_output_catch("git status")
    log = check_output_catch("git log -1")
    remotes = check_output_catch("git remote -v")

    # Python, pip, node, npm.
    python = sys.version.replace(os.linesep, " ").strip()
    pip = check_output_catch("pip -V")
    node = check_output_catch("node -v")
    npm = check_output_catch("npm -v")

    return {
        "args": args,
        "git": {"status": status, "log": log, "remotes": remotes},
        "versions": {"python": python, "pip": pip, "node": node, "npm": npm},
    }


# Post a string of text to a hasteb.in and retrieve the URL.
def upload_to_hastebin(text):
    log.info("Uploading info to hastebin.com...")
    response = requests.post("https://hastebin.com/documents", data=text)
    return response.json()["key"]


# Get censored debug info & auto-upload to hasteb.in.
def get_debug_dump_link():
    debug = get_censored_debug_info()
    args = debug["args"]
    git = debug["git"]
    versions = debug["versions"]

    # Format debug info for text upload.
    result = """#######################
### MerchantMap debug ###
#######################

## Versions:
"""

    # Versions first, for readability.
    result += "- Python: " + versions["python"] + "\n"
    result += "- pip: " + versions["pip"] + "\n"
    result += "- Node.js: " + versions["node"] + "\n"
    result += "- npm: " + versions["npm"] + "\n"

    # Next up is git.
    result += "\n\n" + "## Git:" + "\n"
    result += git["status"] + "\n"
    result += "\n\n" + git["remotes"] + "\n"
    result += "\n\n" + git["log"] + "\n"

    # And finally, our censored args.
    result += "\n\n" + "## Settings:" + "\n"
    result += pformat(args, width=1)

    # Upload to hasteb.in.
    return upload_to_hastebin(result)


def point_is_scheduled(key, scheduled_points):
    found = False
    for point in scheduled_points:
        if key == point[2]:
            found = True
            break
    return found


# Translate peewee model class attribute to database column name.
def peewee_attr_to_col(cls, field):
    field_column = getattr(cls, field)

    # Only try to do it on populated fields.
    if field_column is not None:
        field_column = field_column.db_column
    else:
        field_column = field

    return field_column
