import calendar
import logging
import json

from datetime import datetime
from bisect import bisect_left
from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    request,
    send_from_directory,
    json,
)
from flask.json.provider import DefaultJSONProvider
from flask_compress import Compress
from urllib.parse import urlparse

from .models import (
    ScannedLocation,
    Account,
    Location,
    LocationAction,
    Settlement,
)
from .utils import get_args, now, dottedQuadToNum
from .blacklist import fingerprints


log = logging.getLogger(__name__)
compress = Compress()


def parse_data_from_url(url):
    lat = 0
    lng = 0
    uuid = ""
    scope_id = ""
    light = 0

    parsed_url = urlparse(url)
    requested_endpoint = parsed_url.path.replace("/v1/", "").replace("/", "")
    query = parsed_url.query.split("&")
    for param in query:
        if "lat=" in param:
            lat = float(param.replace("lat=", ""))
        elif "lng=" in param:
            lng = float(param.replace("lng=", ""))
        elif "uuid=" in param:
            uuid = param.replace("uuid=", "")
        elif "scope_id=" in param:
            scope_id = param.replace("scope_id=", "")
        elif "light=" in param:
            light = int(param.replace("light=", ""))

    lat = round(lat, 5)
    lng = round(lng, 5)

    return requested_endpoint, lat, lng, uuid, scope_id, light


def get_requested_data_dict(requested_data):
    result = {}

    try:
        query = requested_data.split("&")
        for param in query:
            param_split = param.split("=")
            if len(param_split) > 1:
                result[param_split[0]] = param_split[1]
    except Exception as e:
        log.info(str(e))

    return result


def _image_base_url():
    args = get_args()

    return f"https://{args.image_base_domain}.com/static/"


class MerchantApp(Flask):

    def __init__(self, import_name, **kwargs):
        self.db_update_queue = kwargs.get("db_update_queue")
        kwargs.pop("db_update_queue")
        super(MerchantApp, self).__init__(import_name, **kwargs)
        compress.init_app(self)

        self.control_flags = None
        self.heartbeat = None
        self.current_location = None

        args = get_args()

        self.blacklist = []
        self.blacklist_keys = []

        # Routes
        self.json = CustomJSONProvider(self)
        self.route("/", methods=["GET"])(self.fullmap)
        self.route("/raw_data", methods=["GET"])(self.raw_data)
        self.route("/account_data", methods=["GET"])(self.get_accountdata)
        self.route("/location_data", methods=["GET"])(self.get_locationdata)

        self.route("/settlements", methods=["GET"])(self.settlementview)
        self.route("/raw_settlements", methods=["POST"])(self.raw_settlements)

        self.route("/herds", methods=["GET"])(self.herdview)
        self.route("/raw_herds", methods=["POST"])(self.raw_herds)

        self.route("/ruines", methods=["GET"])(self.ruineview)
        self.route("/raw_ruines", methods=["POST"])(self.raw_ruines)

        if not args.map_only:
            self.route("/game_webhook", methods=["GET", "POST"])(self.game_webhook)

        self.route("/search_control", methods=["GET"])(self.get_search_control)
        self.route("/search_control", methods=["POST"])(self.post_search_control)
        self.route("/robots.txt", methods=["GET"])(self.render_robots_txt)
        self.route("/serviceWorker.min.js", methods=["GET"])(self.render_service_worker_js)

        self.accounts = {}

    def render_robots_txt(self):
        return render_template("robots.txt")

    def render_service_worker_js(self):
        return send_from_directory("static/dist/js", "serviceWorker.min.js")

    def _get_account(self, ip=None, uuid=None):
        # log.info("Trying to get account with ip: '%s' and uuid: '%s'" % (ip, uuid))
        account = None
        if uuid:
            account = Account.get_by_id(uuid)
            if account:
                self.accounts[account["ip"]] = account
        elif ip:
            account = Account.get_by_ip(ip)
            if account:
                self.accounts[ip] = account

        # log.info("Found account: %s" % account["username"])

        return account

    def game_webhook(self):
        if request.method == "GET":
            request_json = request.args
        else:
            request_json = request.get_json()

        log.info("Request_json from ip %s: %s" % (request.remote_addr, json.dumps(request_json)))

        ip = request.remote_addr
        data = request_json

        if data:
            return self.parse_map_game_data(data, ip)

        return "wrong"

    def parse_map_game_data(self, data, ip):
        now_date = datetime.utcnow()

        accounts = {}
        locations = {}
        location_actions = {}
        settlements = {}

        center = data.get("center", {})
        player = data.get("player", {})
        locations_dict = data.get("locations", [])
        realms_dict = data.get("realm", [])
        if not center or not player or not locations_dict:
            return "error"

        lat = center.get("lat", 0)
        lng = center.get("lng", 0)

        player_id = player.get("id", 0)
        call_title = player.get("call_title", "")
        player_username = call_title

        player = Account.get_by_id(player_id)
        if player["username"]:
            player_username = player["username"]

        account_data = {
            "uuid": player_id,
            "username": player_username,
            "latitude": round(lat, 5),
            "longitude": round(lng, 5),
            "call_title": call_title,
            "last_scanned": now_date,
            "last_ip": ip,
        }
        accounts[player_id] = account_data

        for location_dict in locations_dict:
            uuid = location_dict.get("id", "")
            coordinates = location_dict.get("coordinates", {})
            latitude = coordinates.get("lat", 0)
            longitude = coordinates.get("lng", 0)
            land_type_id = location_dict.get("land_type_id", 0)
            district_id = location_dict.get("district_id", 0)
            occupation_id = location_dict.get("occupation_id", 0)
            location_player_id = location_dict.get("player_id", None)
            player_name = location_dict.get("player_name", None)
            name = location_dict.get("name", None)
            has_treasure = location_dict.get("has_treasure", False)
            newly_created = location_dict.get("newly_created", False)

            location_data = {
                "uuid": uuid,
                "latitude": round(latitude, 5),
                "longitude": round(longitude, 5),
                "land_type_id": land_type_id,
                "district_id": district_id,
                "occupation_id": occupation_id,
                "player_id": location_player_id,
                "player_name": player_name,
                "name": name,
                "has_treasure": has_treasure,
                "newly_created": newly_created,
                "last_scanned": now_date,
            }

            if "population" in location_dict:
                location_data["population"] = location_dict["population"]
            if "player_relation" in location_dict:
                location_data["player_relation"] = location_dict["player_relation"]
            if 20 <= occupation_id <= 23:
                location_data["gentle_possible"] = True
            if 30 <= occupation_id <= 37:
                location_data["excavate_possible"] = True

            if (20 <= occupation_id <= 23) or (30 <= occupation_id <= 37):
                location_action_uuid = f"{uuid}_{player_id}"
                location_action_data = {
                    "uuid": location_action_uuid,
                    "location_id": uuid,
                    "player_id": player_id,
                    "gentle_done": location_dict.get("gentle_done", False),
                    "excavate_done": location_dict.get("excavate_done", False),
                }
                location_actions[location_action_uuid] = location_action_data

            locations[uuid] = location_data

        settlement_uuids = []
        for realm_dict in realms_dict:
            uuid = realm_dict.get("id", 0)
            location_id = realm_dict.get("location_id", 0)
            name = realm_dict.get("name", "")
            settlement_type = realm_dict.get("type", "")
            settlement_type_id = realm_dict.get("type_id", 0)
            coordinates = realm_dict.get("coordinates", {})
            latitude = coordinates.get("lat", 0)
            longitude = coordinates.get("lng", 0)
            population = realm_dict.get("population", 0)
            max_population = realm_dict.get("max_population", 0)
            cultural_score = realm_dict.get("cultural_score", 0)
            daily_gold = realm_dict.get("daily_gold", 0)
            stock_count = realm_dict.get("stock_count", 0)
            max_storage = realm_dict.get("max_storage", 0)
            corruption_days = realm_dict.get("corruption_days", 0)
            corruption_cost = realm_dict.get("corruption_cost", 0)

            location_data = {
                "uuid": location_id,
                "latitude": round(latitude, 5),
                "longitude": round(longitude, 5),
                "player_id": player_id,
                "name": name,
                "last_scanned": now_date,
            }
            visited = True
            if location_id not in locations:
                locations[location_id] = location_data
                visited = False

            settlement_data = {
                "uuid": uuid,
                "location_id": location_id,
                "player_id": player_id,
                "name": name,
                "settlement_type": settlement_type,
                "settlement_type_id": settlement_type_id,
                "population": population,
                "max_population": max_population,
                "cultural_score": cultural_score,
                "daily_gold": daily_gold,
                "stock_count": stock_count,
                "max_storage": max_storage,
                "corruption_days": corruption_days,
                "corruption_cost": corruption_cost,
                "last_scanned": now_date,
            }
            if visited:
                settlement_data["last_visited"] = now_date
            settlements[uuid] = settlement_data
            settlement_uuids.append(uuid)

        if settlement_uuids:
            with Settlement.database():
                Settlement.delete().where(
                    (~(Settlement.uuid << settlement_uuids)) & (Settlement.player_id == player_id)
                ).execute()

        if lat != 0 and lng != 0:
            scan_location = ScannedLocation.get_by_loc([lat, lng])
            scan_location["icon_size"] = 150
            ScannedLocation.update_band(scan_location, now_date)
            self.db_update_queue.put((ScannedLocation, {0: scan_location}))

        if accounts:
            self.db_update_queue.put((Account, accounts))

        if locations:
            self.db_update_queue.put((Location, locations))

        if location_actions:
            self.db_update_queue.put((LocationAction, location_actions))

        if settlements:
            self.db_update_queue.put((Settlement, settlements))

        return "ok"

    def validate_request(self):
        args = get_args()

        # Get real IP behind trusted reverse proxy.
        ip_addr = request.remote_addr
        if ip_addr in args.trusted_proxies:
            ip_addr = request.headers.get("X-Forwarded-For", ip_addr)

        # Make sure IP isn't blacklisted.
        if self._ip_is_blacklisted(ip_addr):
            log.debug("Denied access to %s: blacklisted IP.", ip_addr)
            abort(403)

        return

    def _ip_is_blacklisted(self, ip):
        if not self.blacklist:
            return False

        # Get the nearest IP range
        pos = max(bisect_left(self.blacklist_keys, int(dottedQuadToNum(ip))) - 1, 0)
        ip_range = self.blacklist[pos]

        start = dottedQuadToNum(ip_range[0])
        end = dottedQuadToNum(ip_range[1])

        return start <= dottedQuadToNum(ip) <= end

    def set_control_flags(self, control):
        self.control_flags = control

    def set_heartbeat_control(self, heartb):
        self.heartbeat = heartb

    def set_current_location(self, location):
        self.current_location = location

    def get_search_control(self):
        return jsonify({"status": not self.control_flags["search_control"].is_set()})

    def post_search_control(self):
        args = get_args()
        if not args.search_control or args.on_demand_timeout > 0:
            return "Search control is disabled", 403
        action = request.args.get("action", "none")
        if action == "on":
            self.control_flags["search_control"].clear()
            log.info("Search thread resumed")
        elif action == "off":
            self.control_flags["search_control"].set()
            log.info("Search thread paused")
        else:
            return jsonify({"message": "invalid use of api"})
        return self.get_search_control()

    def fullmap(self):
        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        search_display = False
        scan_display = False

        visibility_flags = {
            "accounts": not args.no_accounts,
            "locations": not args.no_locations,
            "scan_display": scan_display,
            "search_display": search_display,
            "fixed_display": True,
            "custom_css": args.custom_css,
            "custom_js": args.custom_js,
        }

        full_path = request.full_path

        map_lat = self.current_location[0]
        map_lng = self.current_location[1]

        playerid = request.args.get("playerid", "")
        if playerid:
            account = Account.get_by_id(playerid)
            if account:
                map_lat = account.get("latitude", self.current_location[0])
                map_lng = account.get("longitude", self.current_location[1])

        return render_template(
            "map.html",
            lat=map_lat,
            lng=map_lng,
            gmaps_key=args.gmaps_key,
            map_provider=args.map_provider,
            lang="en",
            show=visibility_flags,
            mapname=args.mapname,
            full_path=str(full_path),
        )

    def settlementview(self):
        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        map_lat = self.current_location[0]
        map_lng = self.current_location[1]

        playerid = request.args.get("playerid", "")
        if playerid:
            account = Account.get_by_id(playerid)
            if account:
                map_lat = account.get("latitude", self.current_location[0])
                map_lng = account.get("longitude", self.current_location[1])

        return render_template(
            "settlements.html",
            lat=map_lat,
            lng=map_lng,
            gmaps_key=args.gmaps_key,
            lang="en",
            mapname=args.mapname,
        )

    def herdview(self):
        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        map_lat = self.current_location[0]
        map_lng = self.current_location[1]

        playerid = request.args.get("playerid", "")
        if playerid:
            account = Account.get_by_id(playerid)
            if account:
                map_lat = account.get("latitude", self.current_location[0])
                map_lng = account.get("longitude", self.current_location[1])

        return render_template(
            "herds.html",
            lat=map_lat,
            lng=map_lng,
            gmaps_key=args.gmaps_key,
            lang="en",
            mapname=args.mapname,
        )

    def ruineview(self):
        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        map_lat = self.current_location[0]
        map_lng = self.current_location[1]

        playerid = request.args.get("playerid", "")
        if playerid:
            account = Account.get_by_id(playerid)
            if account:
                map_lat = account.get("latitude", self.current_location[0])
                map_lng = account.get("longitude", self.current_location[1])

        return render_template(
            "ruines.html",
            lat=map_lat,
            lng=map_lng,
            gmaps_key=args.gmaps_key,
            lang="en",
            mapname=args.mapname,
        )

    def raw_data(self):
        # Make sure fingerprint isn't blacklisted.
        fingerprint_blacklisted = any([fingerprints["no_referrer"](request), fingerprints["iPokeGo"](request)])

        if fingerprint_blacklisted:
            log.debug("User denied access: blacklisted fingerprint.")
            abort(403)

        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        d = {"timestamp": datetime.utcnow()}

        # Request time of previous request.
        if request.args.get("timestamp"):
            timestamp = int(request.args.get("timestamp"))
            timestamp -= 1000  # Overlap, for rounding errors.
        else:
            timestamp = 0

        sw_lat = request.args.get("swLat")
        sw_lng = request.args.get("swLng")
        ne_lat = request.args.get("neLat")
        ne_lng = request.args.get("neLng")

        o_sw_lat = request.args.get("oSwLat")
        o_sw_lng = request.args.get("oSwLng")
        o_ne_lat = request.args.get("oNeLat")
        o_ne_lng = request.args.get("oNeLng")

        lastslocs = request.args.get("lastslocs")
        lastaccounts = request.args.get("lastaccounts")
        lastlocations = request.args.get("lastlocations")

        playerid = request.args.get("playerid", "")

        if request.args.get("scanned", "true") == "true":
            d["lastslocs"] = request.args.get("scanned", "true")
        if request.args.get("accounts", "true") == "true":
            d["lastaccounts"] = request.args.get("accounts", "true")
        if request.args.get("locations", "true") == "true":
            d["lastlocations"] = request.args.get("locations", "true")

        # If old coords are not equal to current coords we have moved/zoomed!
        if o_sw_lng is None or o_sw_lat is None or o_ne_lat is None or o_ne_lng is None:
            new_area = True
        elif o_sw_lng < sw_lng and o_sw_lat < sw_lat and o_ne_lat > ne_lat and o_ne_lng > ne_lng:
            new_area = False  # We zoomed in no new area uncovered.
        elif not (o_sw_lat == sw_lat and o_sw_lng == sw_lng and o_ne_lat == ne_lat and o_ne_lng == ne_lng):
            new_area = True
        else:
            new_area = False

        # Pass current coords as old coords.
        d["oSwLat"] = sw_lat
        d["oSwLng"] = sw_lng
        d["oNeLat"] = ne_lat
        d["oNeLng"] = ne_lng

        if request.args.get("scanned", "true") == "true":
            if lastslocs != "true":
                d["scanned"] = ScannedLocation.get_recent(sw_lat, sw_lng, ne_lat, ne_lng)
            else:
                d["scanned"] = ScannedLocation.get_recent(sw_lat, sw_lng, ne_lat, ne_lng, timestamp=timestamp)
                if new_area:
                    d["scanned"] = d["scanned"] + ScannedLocation.get_recent(
                        sw_lat,
                        sw_lng,
                        ne_lat,
                        ne_lng,
                        o_sw_lat=o_sw_lat,
                        o_sw_lng=o_sw_lng,
                        o_ne_lat=o_ne_lat,
                        o_ne_lng=o_ne_lng,
                    )

        if request.args.get("accounts", "true") == "true" and not args.no_accounts:
            if lastaccounts != "true":
                d["accounts"] = Account.get_accounts(sw_lat, sw_lng, ne_lat, ne_lng, playerid)
            else:
                d["accounts"] = Account.get_accounts(sw_lat, sw_lng, ne_lat, ne_lng, playerid, timestamp=timestamp)
                if new_area:
                    d["accounts"].update(
                        Account.get_accounts(
                            sw_lat,
                            sw_lng,
                            ne_lat,
                            ne_lng,
                            playerid,
                            o_sw_lat=o_sw_lat,
                            o_sw_lng=o_sw_lng,
                            o_ne_lat=o_ne_lat,
                            o_ne_lng=o_ne_lng,
                        )
                    )

            all_accounts = Account.get_accounts(sw_lat, sw_lng, ne_lat, ne_lng, playerid)
            account_ids = []
            for uuid, acc in all_accounts.items():
                account_ids.append(uuid)

        if request.args.get("locations", "true") == "true" and not args.no_locations:
            # Exclude ids of Occupation IDS that are hidden.
            eids_locations = []
            request_eids = request.args.get("eids_locations")
            if request_eids:
                eids_locations = {int(i) for i in request_eids.split(",")}

            if lastlocations != "true":
                d["locations"] = Location.get_locations(
                    sw_lat, sw_lng, ne_lat, ne_lng, playerid, exclude=eids_locations
                )
            else:
                d["locations"] = Location.get_locations(
                    sw_lat, sw_lng, ne_lat, ne_lng, playerid, exclude=eids_locations, timestamp=timestamp
                )
                if new_area:
                    d["locations"].update(
                        Location.get_locations(
                            sw_lat,
                            sw_lng,
                            ne_lat,
                            ne_lng,
                            playerid,
                            exclude=eids_locations,
                            o_sw_lat=o_sw_lat,
                            o_sw_lng=o_sw_lng,
                            o_ne_lat=o_ne_lat,
                            o_ne_lng=o_ne_lng,
                        )
                    )

        return jsonify(d)

    def raw_settlements(self):
        # log.info("Raw settlement request received")
        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        playerid = request.form.get("playerid", "")

        d = {"timestamp": datetime.utcnow()}

        log.info(f"Loading the settlements with account {playerid}")

        settlement_dict = Settlement.get_settlements(playerid)

        log.info("Found %s settlements" % len(settlement_dict))

        d["settlements"] = []
        for udid, settlement in settlement_dict.items():
            d["settlements"].append(settlement)

        return jsonify(d)

    def raw_herds(self):
        # log.info("Raw herd request received")
        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        playerid = request.form.get("playerid", "")

        d = {"timestamp": datetime.utcnow()}

        log.info(f"Loading the herds with account {playerid}")

        herd_dict = Location.get_herds(playerid)

        log.info("Found %s herds" % len(herd_dict))

        d["herds"] = []
        for udid, herd in herd_dict.items():
            d["herds"].append(herd)

        return jsonify(d)

    def raw_ruines(self):
        # log.info("Raw ruine request received")
        self.heartbeat[0] = now()
        args = get_args()
        if args.on_demand_timeout > 0:
            self.control_flags["on_demand"].clear()

        playerid = request.form.get("playerid", "")

        d = {"timestamp": datetime.utcnow()}

        log.info(f"Loading the ruines with account {playerid}")

        ruine_dict = Location.get_ruines(playerid)

        log.info("Found %s ruines" % len(ruine_dict))

        d["ruines"] = []
        for udid, ruine in ruine_dict.items():
            d["ruines"].append(ruine)

        return jsonify(d)

    def get_accountdata(self):
        uuid = request.args.get("id")
        account = Account.get_by_id(uuid)

        return jsonify(account)

    def get_locationdata(self):
        account = request.args.get("account", "")
        playerid = request.args.get("playerid", "")
        if playerid and not account:
            account_db = Account.get_by_id(playerid)
            if account_db:
                account = account_db["username"]
        uuid = request.args.get("id")
        location = Location.get_by_id(uuid, account)

        return jsonify(location)


class CustomJSONProvider(DefaultJSONProvider):

    @staticmethod
    def default(obj):
        try:
            if isinstance(obj, datetime):
                if obj.utcoffset() is not None:
                    obj = obj - obj.utcoffset()
                millis = int(calendar.timegm(obj.timetuple()) * 1000 + obj.microsecond / 1000)
                return millis
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return DefaultJSONProvider.default(obj)
