import logging
import sys
import gc
import time
import peewee

from functools import reduce

from peewee import (
    Check,
    SmallIntegerField,
    IntegerField,
    CharField,
    DoubleField,
    BooleanField,
    DateTimeField,
)
from playhouse.flask_utils import FlaskDB
from playhouse.migrate import migrate, MySQLMigrator
import datetime
from cachetools import TTLCache
from timeit import default_timer
import geopy

from merchant.utils import get_args, cellid, date_secs
from merchant.transform import transform_from_wgs_to_gcj, get_new_coords


log = logging.getLogger(__name__)

args = get_args()
flaskDb = FlaskDB()
cache = TTLCache(maxsize=100, ttl=60 * 5)

db_schema_version = 1

LOCATION_OFFSET = 4

# a = arid
# c = cold
# d = desert
# f = flat
# h = hill
# m = mountain
# t = tropical
# w = wet

LAND_TYPE_NAMES = {
    # Flat
    1: "Plains",
    2: "Floodplains",
    3: "Woods",
    4: "Moorland",
    5: "River",
    6: "Forest",
    7: "Scrubland",
    8: "Swamp",
    # Arid
    9: "Prairie",
    10: "Volcano",
    11: "Savannah",
    12: "Steppe",
    13: "Dunes",
    14: "Salt Flats",
    15: "Canyon",
    16: "Rocks",
    # Desert
    17: "Oasis",
    18: "Desert",
    19: "Salt Flats",
    20: "Plateau",
    21: "Savannah",
    22: "Dunes",
    23: "Scrubland",
    24: "Steppe",
    # Tropical
    25: "Rainforest",
    26: "Jungle",
    27: "Extinct Volcano",
    28: "Forested Hills",
    29: "River",
    30: "Forest",
    31: "Bushes",
    32: "Lake",
    # Wet
    33: "Wetland",
    34: "Delta",
    35: "Marsh",
    36: "Tundra",
    37: "Lake",
    38: "Moorland",
    39: "Bushes",
    40: "Swamp",
    # Cold
    41: "Arctic Tundra",
    42: "Glacier",
    43: "Dark Forest",
    44: "Mountain",
    45: "Marsh",
    46: "Tundra",
    47: "River",
    48: "Taiga",
    # Hills
    49: "Hills",
    50: "Rocky Plains",
    51: "Dark Forest",
    52: "Forested Hills",
    53: "River",
    54: "Woods",
    55: "Waterfall",
    56: "Taiga",
    # Mountain
    57: "Caves",
    58: "Peaks",
    59: "Rocks",
    60: "Canyon",
    61: "Extinct Volcano",
    62: "Waterfall",
    63: "Mountain",
    64: "Plateau",
}


# Reduction of CharField to fit max length inside 767 bytes for utf8mb4 charset
class Utf8mb4CharField(peewee.CharField):
    def __init__(self, max_length=191, *args, **kwargs):
        self.max_length = max_length
        super(CharField, self).__init__(*args, **kwargs)


class UBigIntegerField(peewee.BigIntegerField):
    field_type = "bigint unsigned"


class LongTextField(peewee.TextField):
    field_type = "LONGTEXT"


def init_database(app):
    log.info("Connecting to MySQL database on {}:{}...".format(args.db_host, args.db_port))
    db = peewee.MySQLDatabase(
        args.db_name, user=args.db_user, password=args.db_pass, host=args.db_host, port=args.db_port, charset="utf8mb4"
    )
    db.connect()

    # Using internal method as the other way would be using internal var, we
    # could use initializer but db is initialized later
    flaskDb._load_database(app, db)
    if app is not None:
        flaskDb._register_handlers(app)
    return db


class BaseModel(flaskDb.Model):

    @classmethod
    def database(cls):
        return cls._meta.database

    @classmethod
    def get_all(cls):
        return [m for m in cls.select().dicts()]


class LatLongModel(BaseModel):

    @classmethod
    def get_all(cls):
        results = [m for m in cls.select().dicts()]
        if args.china:
            for result in results:
                result["latitude"], result["longitude"] = transform_from_wgs_to_gcj(
                    result["latitude"], result["longitude"]
                )
        return results


class Account(LatLongModel):
    uuid = IntegerField(primary_key=True, index=True)
    username = Utf8mb4CharField(max_length=100, default="")
    latitude = DoubleField()
    longitude = DoubleField()
    call_title = Utf8mb4CharField(max_length=250, default="")
    last_scanned = DateTimeField(index=True)
    last_ip = Utf8mb4CharField()

    @staticmethod
    def get_by_id(account_id):
        with Account.database():
            query = Account.select().where(Account.uuid == account_id).dicts()

            result = (
                query[0]
                if query
                else {
                    "uuid": account_id,
                    "username": "",
                    "latitude": 0,
                    "longitude": 0,
                    "call_title": "",
                }
            )

        result["sprite"] = "static/images/markers/player.webp"

        return result

    @staticmethod
    def get_by_ip(ip):
        try:
            with Account.database():
                query = Account.select().where(Account.last_ip == ip).dicts().order_by(Account.last_scanned.desc())

                result = query[0] if query else None
        except Account.DoesNotExist:
            result = None

        return result

    @staticmethod
    def get_by_username(username):
        try:
            with Account.database():
                query = (
                    Account.select().where(Account.username == username).dicts().order_by(Account.last_scanned.desc())
                )

                result = query[0] if query else None
        except Account.DoesNotExist:
            result = None

        return result

    @staticmethod
    def get_accounts(
        sw_lat,
        sw_lng,
        ne_lat,
        ne_lng,
        playerid,
        timestamp=0,
        o_sw_lat=None,
        o_sw_lng=None,
        o_ne_lat=None,
        o_ne_lng=None,
    ):
        query = Account.select()

        if not (sw_lat and sw_lng and ne_lat and ne_lng):
            query = query.dicts()
        elif timestamp > 0:
            query = query.where(
                (Account.last_scanned > datetime.datetime.utcfromtimestamp(timestamp / 1000))
                & (Account.latitude >= sw_lat)
                & (Account.longitude >= sw_lng)
                & (Account.latitude <= ne_lat)
                & (Account.longitude <= ne_lng)
            ).dicts()
        elif o_sw_lat and o_sw_lng and o_ne_lat and o_ne_lng:
            query = query.where(
                (
                    (Account.latitude >= sw_lat)
                    & (Account.longitude >= sw_lng)
                    & (Account.latitude <= ne_lat)
                    & (Account.longitude <= ne_lng)
                )
                & ~(
                    (Account.latitude >= o_sw_lat)
                    & (Account.longitude >= o_sw_lng)
                    & (Account.latitude <= o_ne_lat)
                    & (Account.longitude <= o_ne_lng)
                )
            ).dicts()
        else:
            query = query.where(
                (Account.latitude >= sw_lat)
                & (Account.longitude >= sw_lng)
                & (Account.latitude <= ne_lat)
                & (Account.longitude <= ne_lng)
            ).dicts()

        gc.disable()

        accounts = {}

        accountfound = False
        if not playerid:
            accountfound = True

        for b in query:
            if args.china:
                b["latitude"], b["longitude"] = transform_from_wgs_to_gcj(b["latitude"], b["longitude"])
            b["latitude"] = round(b["latitude"], 5)
            b["longitude"] = round(b["longitude"], 5)

            b["sprite"] = "static/images/markers/player.webp"

            accounts[b["uuid"]] = b

            if playerid and b["uuid"] == playerid:
                accountfound = True

        if not accountfound:
            try:
                result = Account.select().where(Account.uuid == playerid).dicts()
                for b in result:
                    if args.china:
                        b["latitude"], b["longitude"] = transform_from_wgs_to_gcj(b["latitude"], b["longitude"])
                    b["latitude"] = round(b["latitude"], 5)
                    b["longitude"] = round(b["longitude"], 5)
                    b["sprite"] = "static/images/markers/player.webp"

                    accounts[b["uuid"]] = b
            except Account.DoesNotExist:
                pass

        gc.enable()

        return accounts

    @staticmethod
    def get_all_accounts():
        with Account.database():
            query = Account.select().dicts()

        return list(query)


class Location(LatLongModel):
    uuid = IntegerField(primary_key=True, index=True)
    latitude = DoubleField()
    longitude = DoubleField()
    land_type_id = IntegerField(default=0)
    land_type_name = CharField(default="", max_length=100, null=True)
    land_type_image = CharField(default="", max_length=100, null=True)
    district_id = IntegerField(default=0)
    occupation_id = IntegerField(default=0, null=True)
    yield_modifier = DoubleField(default=0, null=True)
    player_id = IntegerField(default=0, null=True)
    player_name = CharField(default="", max_length=100, null=True)
    name = CharField(default="", max_length=100, null=True)
    has_treasure = BooleanField(default=False)
    newly_created = BooleanField(default=False)
    population = IntegerField(default=0, null=True)
    player_relation = DoubleField(default=0, null=True)
    gentle_possible = BooleanField(default=False, null=True)
    excavate_possible = BooleanField(default=False, null=True)

    last_scanned = DateTimeField(index=True)

    @staticmethod
    def _result_to_land_type_name(location_dict):
        land_type_name = location_dict["land_type_name"]
        if not land_type_name and location_dict["land_type_id"] in LAND_TYPE_NAMES:
            land_type_name = LAND_TYPE_NAMES[location_dict["land_type_id"]]
        return land_type_name

    @staticmethod
    def _result_to_sprite(location_dict):
        sprite = f"static/images/markers/tiles/{location_dict['land_type_id']}.webp"

        if location_dict["occupation_id"]:
            sprite = f"static/images/markers/occupiers/{location_dict['occupation_id']}.webp"

        return sprite

    @staticmethod
    def _coords_offset(location_dict):
        latitude = location_dict["latitude"]
        longitude = location_dict["longitude"]
        latitude += 5 * pow(10, -1 * LOCATION_OFFSET)
        longitude += 5 * pow(10, -1 * LOCATION_OFFSET)
        latitude = round(latitude, 5)
        longitude = round(longitude, 5)
        return latitude, longitude

    @staticmethod
    def _inverse_coords_offset(location_dict):
        latitude = location_dict["latitude"]
        longitude = location_dict["longitude"]
        latitude -= 5 * pow(10, -1 * LOCATION_OFFSET)
        longitude -= 5 * pow(10, -1 * LOCATION_OFFSET)
        latitude = round(latitude, 5)
        longitude = round(longitude, 5)
        return latitude, longitude

    @staticmethod
    def _get_locations_with_occupation(playerid, min_occupation_id=0, max_occupation_id=9999):
        query = (
            Location.select()
            .where((Location.occupation_id >= min_occupation_id) & (Location.occupation_id <= max_occupation_id))
            .dicts()
        )

        gc.disable()

        locations = {}

        account_uuid = None
        acc_lat = 0
        acc_lng = 0
        if playerid:
            account_res = Account.get_by_id(playerid)
            if account_res is not None:
                account_uuid = playerid
                acc_lat = account_res.get("latitude", 0)
                acc_lng = account_res.get("longitude", 0)

        if not account_uuid:
            return locations

        location_uuids = []
        for b in query:
            location_uuids.append(b["uuid"])

        db_location_actions = (
            LocationAction.select()
            .where(LocationAction.location_id << location_uuids)
            .where(LocationAction.player_id == account_uuid)
            .distinct()
            .dicts()
        )
        location_actions = {}
        for b in db_location_actions:
            location_actions[b["location_id"]] = b

        for b in query:
            if args.china:
                b["latitude"], b["longitude"] = transform_from_wgs_to_gcj(b["latitude"], b["longitude"])
            b["latitude"] = round(b["latitude"], 5)
            b["longitude"] = round(b["longitude"], 5)

            latitude, longitude = Location._coords_offset(b)
            b["latitude"] = latitude
            b["longitude"] = longitude

            b["sprite"] = Location._result_to_sprite(b)
            b["land_type_name"] = Location._result_to_land_type_name(b)

            b["actions_known"] = b["uuid"] in location_actions
            b["actions"] = location_actions.get(
                b["uuid"],
                {
                    "gentle_done": False,
                    "excavate_done": False,
                },
            )

            if b["occupation_id"] == 20:
                b["name"] = "Donkeys"
            elif b["occupation_id"] == 21:
                b["name"] = "Horses"
            elif b["occupation_id"] == 22:
                b["name"] = "Camels"
            elif b["occupation_id"] == 23:
                b["name"] = "Elephants"
            elif b["occupation_id"] == 30:
                b["name"] = "Pyramids"
            elif b["occupation_id"] == 31:
                b["name"] = "Abandoned Cavern"
            elif b["occupation_id"] == 32:
                b["name"] = "Frozen Mammoth"
            elif b["occupation_id"] == 33:
                b["name"] = "Tomb"
            elif b["occupation_id"] == 34:
                b["name"] = "Ruined Temple"
            elif b["occupation_id"] == 35:
                b["name"] = "Ruined Treasury"
            elif b["occupation_id"] == 36:
                b["name"] = "Shipwreck"
            elif b["occupation_id"] == 37:
                b["name"] = "Standing Stones"

            dd_lat = b["latitude"]
            dd_lng = b["longitude"]
            distance = round(geopy.distance.geodesic((acc_lat, acc_lng), (dd_lat, dd_lng)).km * 1000)
            b["distance"] = distance

            locations[b["uuid"]] = b

        gc.enable()

        return locations

    @staticmethod
    def get_herds(playerid):
        return Location._get_locations_with_occupation(playerid, 20, 23)

    @staticmethod
    def get_ruines(playerid):
        return Location._get_locations_with_occupation(playerid, 30, 37)

    @staticmethod
    def get_by_id(location_id, account):
        try:
            result = Location.select().where(Location.uuid == location_id).dicts().get()
        except Location.DoesNotExist:
            return None

        account_uuid = None
        if account:
            account_res = Account.get_by_username(account)
            if account_res is not None:
                account_uuid = account_res["uuid"]

        if result:
            owned_map_user = False
            if account_uuid and result["player_id"] == account_uuid:
                owned_map_user = True
            result["owned"] = owned_map_user

            result["sprite"] = Location._result_to_sprite(result)
            result["land_type_name"] = Location._result_to_land_type_name(result)

            latitude, longitude = Location._coords_offset(result)
            result["latitude"] = latitude
            result["longitude"] = longitude

        return result

    @staticmethod
    def get_locations(
        sw_lat,
        sw_lng,
        ne_lat,
        ne_lng,
        playerid,
        exclude=None,
        timestamp=0,
        o_sw_lat=None,
        o_sw_lng=None,
        o_ne_lat=None,
        o_ne_lng=None,
    ):
        query = Location.select()

        if exclude:
            query = query.where(Location.occupation_id.not_in(list(exclude)))

        if not (sw_lat and sw_lng and ne_lat and ne_lng):
            query = query.dicts()
        elif timestamp > 0:
            query = query.where(
                (Location.last_scanned > datetime.datetime.utcfromtimestamp(timestamp / 1000))
                & (Location.latitude >= sw_lat)
                & (Location.longitude >= sw_lng)
                & (Location.latitude <= ne_lat)
                & (Location.longitude <= ne_lng)
            ).dicts()
        elif o_sw_lat and o_sw_lng and o_ne_lat and o_ne_lng:
            query = query.where(
                (
                    (Location.latitude >= sw_lat)
                    & (Location.longitude >= sw_lng)
                    & (Location.latitude <= ne_lat)
                    & (Location.longitude <= ne_lng)
                )
                & ~(
                    (Location.latitude >= o_sw_lat)
                    & (Location.longitude >= o_sw_lng)
                    & (Location.latitude <= o_ne_lat)
                    & (Location.longitude <= o_ne_lng)
                )
            ).dicts()
        else:
            query = query.where(
                (Location.latitude >= sw_lat)
                & (Location.longitude >= sw_lng)
                & (Location.latitude <= ne_lat)
                & (Location.longitude <= ne_lng)
            ).dicts()

        gc.disable()

        locations = {}

        for b in query:
            if args.china:
                b["latitude"], b["longitude"] = transform_from_wgs_to_gcj(b["latitude"], b["longitude"])
            b["latitude"] = round(b["latitude"], 5)
            b["longitude"] = round(b["longitude"], 5)

            latitude, longitude = Location._coords_offset(b)
            b["latitude"] = latitude
            b["longitude"] = longitude

            owned_map_user = False
            if playerid and b["player_id"] == playerid:
                owned_map_user = True
            b["owned"] = owned_map_user

            b["sprite"] = Location._result_to_sprite(b)
            b["land_type_name"] = Location._result_to_land_type_name(b)

            locations[b["uuid"]] = b

        gc.enable()

        return locations


class LocationAction(LatLongModel):
    uuid = CharField(primary_key=True, max_length=100, index=True)
    location_id = IntegerField()
    player_id = IntegerField()
    gentle_done = BooleanField(default=False)
    excavate_done = BooleanField(default=False)


class ScannedLocation(LatLongModel):
    cellid = UBigIntegerField(primary_key=True)
    latitude = DoubleField()
    longitude = DoubleField()
    last_modified = DateTimeField(index=True, default=datetime.datetime.utcnow, null=True)
    done = BooleanField(default=False)

    band1 = SmallIntegerField(default=-1)
    band2 = SmallIntegerField(default=-1)
    band3 = SmallIntegerField(default=-1)
    band4 = SmallIntegerField(default=-1)
    band5 = SmallIntegerField(default=-1)

    midpoint = SmallIntegerField(default=0)

    width = SmallIntegerField(default=0)

    icon_size = SmallIntegerField(default=150)

    fortradius = UBigIntegerField(default=450)
    monradius = UBigIntegerField(default=70)
    scanningforts = SmallIntegerField(default=0)

    class Meta:
        indexes = ((("latitude", "longitude"), False),)
        constraints = [
            Check("band1 >= -1"),
            Check("band1 < 3600"),
            Check("band2 >= -1"),
            Check("band2 < 3600"),
            Check("band3 >= -1"),
            Check("band3 < 3600"),
            Check("band4 >= -1"),
            Check("band4 < 3600"),
            Check("band5 >= -1"),
            Check("band5 < 3600"),
            Check("midpoint >= -130"),
            Check("midpoint <= 130"),
            Check("width >= 0"),
            Check("width <= 130"),
        ]

    @staticmethod
    def get_recent(
        sw_lat, sw_lng, ne_lat, ne_lng, timestamp=0, o_sw_lat=None, o_sw_lng=None, o_ne_lat=None, o_ne_lng=None
    ):
        active_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
        if timestamp > 0:
            query = (
                ScannedLocation.select()
                .where(
                    (ScannedLocation.last_modified >= datetime.datetime.utcfromtimestamp(timestamp / 1000))
                    & (ScannedLocation.latitude >= sw_lat)
                    & (ScannedLocation.longitude >= sw_lng)
                    & (ScannedLocation.latitude <= ne_lat)
                    & (ScannedLocation.longitude <= ne_lng)
                )
                .dicts()
            )
        elif o_sw_lat and o_sw_lng and o_ne_lat and o_ne_lng:
            query = (
                ScannedLocation.select()
                .where(
                    (
                        (ScannedLocation.last_modified >= active_time)
                        & (ScannedLocation.latitude >= sw_lat)
                        & (ScannedLocation.longitude >= sw_lng)
                        & (ScannedLocation.latitude <= ne_lat)
                        & (ScannedLocation.longitude <= ne_lng)
                    )
                    & ~(
                        (ScannedLocation.last_modified >= active_time)
                        & (ScannedLocation.latitude >= o_sw_lat)
                        & (ScannedLocation.longitude >= o_sw_lng)
                        & (ScannedLocation.latitude <= o_ne_lat)
                        & (ScannedLocation.longitude <= o_ne_lng)
                    )
                )
                .dicts()
            )
        else:
            query = (
                ScannedLocation.select()
                .where(
                    (ScannedLocation.last_modified >= active_time)
                    & (ScannedLocation.latitude >= sw_lat)
                    & (ScannedLocation.longitude >= sw_lng)
                    & (ScannedLocation.latitude <= ne_lat)
                    & (ScannedLocation.longitude <= ne_lng)
                )
                .order_by(ScannedLocation.last_modified.asc())
                .dicts()
            )

        if args.china:
            for result in query:
                result["latitude"], result["longitude"] = transform_from_wgs_to_gcj(
                    result["latitude"], result["longitude"]
                )
                result["latitude"] = round(result["latitude"], 5)
                result["longitude"] = round(result["longitude"], 5)
        return list(query)

    @staticmethod
    def new_loc(loc):
        return {
            "cellid": cellid(loc),
            "latitude": loc[0],
            "longitude": loc[1],
            "done": False,
            "band1": -1,
            "band2": -1,
            "band3": -1,
            "band4": -1,
            "band5": -1,
            "width": 0,
            "midpoint": 0,
            "icon_size": 150,
            "fortradius": 450,
            "monradius": 70,
            "scanningforts": 0,
            "last_modified": None,
        }

    @staticmethod
    def db_format(scan, band, nowms):
        scan.update({"band" + str(band): nowms})
        scan["done"] = reduce(lambda x, y: x and (scan["band" + str(y)] > -1), list(range(1, 6)), True)
        return scan

    @staticmethod
    def _q_init(scan, start, end, kind, sp_id=None):
        return {
            "loc": scan["loc"],
            "kind": kind,
            "start": start,
            "end": end,
            "step": scan["step"],
            "sp": sp_id,
        }

    @staticmethod
    def get_by_cellids(cellids):
        d = {}
        with ScannedLocation.database():
            query = ScannedLocation.select().where(ScannedLocation.cellid << cellids).dicts()

            for sl in list(query):
                key = "{}".format(sl["cellid"])
                d[key] = sl
        return d

    @staticmethod
    def find_in_locs(loc, locs):
        key = "{}".format(cellid(loc))
        return locs[key] if key in locs else ScannedLocation.new_loc(loc)

    @staticmethod
    def get_by_loc(loc):
        with ScannedLocation.database():
            query = ScannedLocation.select().where(ScannedLocation.cellid == cellid(loc)).dicts()
            result = query[0] if len(list(query)) else ScannedLocation.new_loc(loc)
        return result

    @staticmethod
    def get_times(scan, now_date, scanned_locations):
        s = ScannedLocation.find_in_locs(scan["loc"], scanned_locations)
        if s["done"]:
            return []

        max_val = 3600 * 2 + 250  # Greater than maximum possible value.
        min_val = {"end": max_val}

        nowms = date_secs(now_date)
        if s["band1"] == -1:
            return [ScannedLocation._q_init(scan, nowms, nowms + 3599, "band")]

        # Find next window.
        basems = s["band1"]
        for i in range(2, 6):
            ms = s["band" + str(i)]

            # Skip bands already done.
            if ms > -1:
                continue

            radius = 120 - s["width"] / 2
            end = (basems + s["midpoint"] + radius + (i - 1) * 720 - 10) % 3600
            end = end if end >= nowms else end + 3600

            if end < min_val["end"]:
                min_val = ScannedLocation._q_init(scan, end - radius * 2 + 10, end, "band")

        return [min_val] if min_val["end"] < max_val else []

    @staticmethod
    def update_band(scan, now_date):
        scan["last_modified"] = now_date

        if scan["done"]:
            return scan

        now_secs = date_secs(now_date)
        if scan["band1"] == -1:
            return ScannedLocation.db_format(scan, 1, now_secs)

        basems = scan["band1"]
        delta = (now_secs - basems - scan["midpoint"]) % 3600
        band = int(round(delta / 12 / 60.0) % 5) + 1

        if scan["band" + str(band)] > -1:
            return scan

        offset = (delta + 1080) % 720 - 360
        if abs(offset) > 120 - scan["width"] / 2:
            return scan

        scan = ScannedLocation.db_format(scan, band, now_secs)
        bts = [scan["band" + str(i)] for i in range(1, 6)]
        bts = [ms for ms in bts if ms > -1]
        bts_delta = list([(ms - basems) % 3600 for ms in bts])
        bts_offsets = list([(ms + 1080) % 720 - 360 for ms in bts_delta])
        min_scan = min(bts_offsets)
        max_scan = max(bts_offsets)
        scan["width"] = max_scan - min_scan
        scan["midpoint"] = (max_scan + min_scan) / 2

        return scan

    @staticmethod
    def reset_bands(scan_loc):
        scan_loc["done"] = False
        scan_loc["last_modified"] = datetime.datetime.utcnow()
        for i in range(1, 6):
            scan_loc["band" + str(i)] = -1

    @staticmethod
    def select_in_hex(locs):
        cells = []
        for i, e in enumerate(locs):
            cells.append(cellid(e[1]))

        in_hex = []
        return in_hex


class Versions(BaseModel):
    key = Utf8mb4CharField()
    val = SmallIntegerField()

    class Meta:
        primary_key = False


def hex_bounds(center, steps=None, radius=None):
    sp_dist = 0.07 * (2 * steps + 1) if steps else radius
    n = get_new_coords(center, sp_dist, 0)[0]
    e = get_new_coords(center, sp_dist, 90)[1]
    s = get_new_coords(center, sp_dist, 180)[0]
    w = get_new_coords(center, sp_dist, 270)[1]
    return n, e, s, w


def db_updater(q, db):
    while True:
        try:
            while True:
                model, data = q.get()

                start_timer = default_timer()
                bulk_upsert(model, data, db)
                q.task_done()

                log.debug(
                    "Upserted to %s, %d records (upsert queue remaining: %d) in %.6f seconds.",
                    model.__name__,
                    len(data),
                    q.qsize(),
                    default_timer() - start_timer,
                )

                # Helping out the GC.
                del model
                del data

                if q.qsize() > 50:
                    log.warning("DB queue is > 50 (@%d); try increasing --db-threads.", q.qsize())
        except Exception as e:
            log.exception("Exception in db_updater: %s", repr(e))
            time.sleep(5)


def clean_db_loop(args):
    regular_cleanup_secs = 60
    full_cleanup_timer = default_timer()
    full_cleanup_secs = 600
    while True:
        try:
            db_cleanup_regular()

            now = default_timer()
            if now - full_cleanup_timer > full_cleanup_secs:
                if args.db_cleanup_account > 0:
                    db_clean_accounts(args.db_cleanup_account)

                log.info("Full database cleanup completed.")
                full_cleanup_timer = now

            time.sleep(regular_cleanup_secs)
        except Exception as e:
            log.exception("Database cleanup failed: %s.", e)


def db_clean_accounts(age_hours):
    log.debug("Beginning cleanup of old account data.")
    start_timer = default_timer()

    account_info_timeout = datetime.datetime.utcnow() - datetime.timedelta(hours=age_hours)

    with Account.database().execution_context():
        query = Account.delete().where(Account.last_scanned < account_info_timeout)
        rows = query.execute()
        log.debug("Deleted %d old Account entries.", rows)

    time_diff = default_timer() - start_timer
    log.debug("Completed cleanup of old Account data in %.6f seconds.", time_diff)


def db_cleanup_regular():
    log.debug("Regular database cleanup started.")
    start_timer = default_timer()

    time_diff = default_timer() - start_timer
    log.debug("Completed regular cleanup in %.6f seconds.", time_diff)


def bulk_upsert(model, data, db):
    rows = data.values()

    if db.is_closed():
        db.connect()
        log.debug("Database connection is closed, connect again")

    with db.atomic():
        for row in rows:
            log.debug("Inserting items info: {}".format(model.__name__))
            model.insert(row).on_conflict(update=row).execute()
    return True


def create_tables(db):
    tables = [
        Account,
        Location,
        LocationAction,
        ScannedLocation,
    ]
    with db:
        for table in tables:
            if not table.table_exists():
                log.info("Creating table: %s", table.__name__)
                db.create_tables([table], safe=True)
            else:
                log.debug("Skipping table %s, it already exists.", table.__name__)


def drop_tables(db):
    tables = [
        Account,
        Location,
        LocationAction,
        ScannedLocation,
        Versions,
    ]
    with db:
        db.execute_sql("SET FOREIGN_KEY_CHECKS=0;")
        for table in tables:
            if table.table_exists():
                log.info("Dropping table: %s", table.__name__)
                db.drop_tables([table], safe=True)

        db.execute_sql("SET FOREIGN_KEY_CHECKS=1;")


def verify_table_encoding(db):
    with db:
        cmd_sql = (
            """
            SELECT table_name FROM information_schema.tables WHERE
            table_collation != 'utf8mb4_unicode_ci'
            AND table_schema = '%s';
            """
            % args.db_name
        )
        change_tables = db.execute_sql(cmd_sql)

        cmd_sql = "SHOW tables;"
        tables = db.execute_sql(cmd_sql)

        if change_tables.rowcount > 0:
            log.info("Changing collation and charset on %s tables.", change_tables.rowcount)

            if change_tables.rowcount == tables.rowcount:
                log.info("Changing whole database, this might a take while.")

            db.execute_sql("SET FOREIGN_KEY_CHECKS=0;")
            for table in change_tables:
                log.debug("Changing collation and charset on table %s.", table[0])
                cmd_sql = """ALTER TABLE %s CONVERT TO CHARACTER SET utf8mb4
                            COLLATE utf8mb4_unicode_ci;""" % str(
                    table[0]
                )
                db.execute_sql(cmd_sql)
            db.execute_sql("SET FOREIGN_KEY_CHECKS=1;")


def verify_database_schema(db):
    if not Versions.table_exists():
        db.create_tables([Versions])

        if ScannedLocation.table_exists():
            # Versions table doesn't exist, but there are tables. This must
            # mean the user is coming from a database that existed before we
            # started tracking the schema version. Perform a full upgrade.
            Versions.insert({Versions.key: "schema_version", Versions.val: 0}).execute()
            database_migrate(db, 0)
        else:
            Versions.insert({Versions.key: "schema_version", Versions.val: db_schema_version}).execute()

    else:
        db_ver = Versions.get(Versions.key == "schema_version").val

        if db_ver < db_schema_version:
            if not database_migrate(db, db_ver):
                log.error("Error migrating database")
                sys.exit(1)

        elif db_ver > db_schema_version:
            log.error(
                "Your database version (%i) appears to be newer than the code supports (%i).", db_ver, db_schema_version
            )
            log.error("Please upgrade your code base or drop all tables in your database.")
            sys.exit(1)
    db.close()


def database_migrate(db, old_ver):
    # Update database schema version.
    Versions.update(val=db_schema_version).where(Versions.key == "schema_version").execute()

    log.info("Detected database version %i, updating to %i...", old_ver, db_schema_version)

    # Perform migrations here.
    migrator = MySQLMigrator(db)

    if old_ver < 1:
        create_tables(db)

    log.info("Schema upgrade complete.")
    return True
