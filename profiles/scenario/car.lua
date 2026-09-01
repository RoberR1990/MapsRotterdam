-- Car profile

api_version = 4

Set = require('lib/set')
Sequence = require('lib/sequence')
Handlers = require("lib/way_handlers")
Relations = require("lib/relations")
Obstacles = require("lib/obstacles")
find_access_tag = require("lib/access").find_access_tag
resolve_access = require("lib/access").resolve_access
limit = require("lib/maxspeed").limit
Utils = require("lib/utils")
Measure = require("lib/measure")

function setup()
  return {
    properties = {
      max_speed_for_map_matching      = 180/3.6, -- 180kmph -> m/s
      -- For routing based on duration, but weighted for preferring certain roads
      weight_name                     = 'routability',
      -- For shortest duration without penalties for accessibility
      -- weight_name                     = 'duration',
      -- For shortest distance without penalties for accessibility
      -- weight_name                     = 'distance',
      process_call_tagless_node      = false,
      u_turn_penalty                 = 20,
      continue_straight_at_waypoint  = true,
      use_turn_restrictions          = true,
      left_hand_driving              = false,
    },

    default_mode              = mode.driving,
    default_speed             = 10,
    oneway_handling           = true,
    side_road_multiplier      = 0.8,
    turn_penalty              = 19.50,
    speed_reduction           = 0.8,
    congestion_default        = 0.95,
    congestion = {
        ["motorway"] = 0.55,
        ["motorway_link"] = 0.6,
        ["trunk"] = 0.55,
        ["trunk_link"] = 0.6,
        ["primary"] = 0.6,
        ["primary_link"] = 0.65,
        ["secondary"] = 0.65,
        ["secondary_link"] = 0.7,
        ["tertiary"] = 0.75,
        ["tertiary_link"] = 0.8,
        ["unclassified"] = 0.9,
        ["residential"] = 0.95,
        ["living_street"] = 1.0,
        ["service"] = 1.0,
    },
    turn_bias                 = 1.075,
    cardinal_directions       = false,

    -- Penalty multiplier for roads with no lane markings (lane_markings=no)
    -- Applied to bidirectional roads to prefer roads with clear lane markings
    lane_markings_penalty     = 0.75,

    -- Penalty multiplier for the disadvantaged direction on ways tagged 'priority=forward'/'priority=backward'.
    -- Applies to the per-direction rate (speed). A value < 1 reduces the disadvantaged
    -- direction's rate which increases its routing weight (weight ≈ duration / rate).
    -- This is applied to any way with a 'priority' tag; add an explicit width/lanes
    -- guard if the penalty should only target narrow or single-lane roads.
    priority_penalty          = 0.7,

    -- Size of the vehicle, to be limited by physical restriction of the way
    vehicle_height = 2.0, -- in meters, 2.0m is the height slightly above biggest SUVs
    vehicle_width = 1.9, -- in meters, ways with narrow tag are considered narrower than 2.2m

    -- Size of the vehicle, to be limited mostly by legal restriction of the way
    vehicle_length = 4.8, -- in meters, 4.8m is the length of large or family car
    vehicle_weight = 2000, -- in kilograms

    -- Optional: upper limit for all speeds (e.g., 87 for trucks)
    -- When set, no derived speed will exceed this value
    -- When nil (default), no additional capping is applied
    vehicle_max_speed = nil, -- in km/h

    -- a list of suffixes to suppress in name change instructions. The suffixes also include common substrings of each other
    suffix_list = {
      'N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW', 'North', 'South', 'West', 'East', 'Nor', 'Sou', 'We', 'Ea'
    },

    barrier_whitelist = Set {
      'cattle_grid',
      'border_control',
      'toll_booth',
      'sally_port',
      'no',
      'entrance',
      'height_restrictor',
      'arch'
    },

    access_tag_whitelist = Set {
      'yes',
      'motorcar',
      'motor_vehicle',
      'vehicle',
      'permissive',
      'designated',
      'hov'
    },

    access_tag_blacklist = Set {
      'no',
      'agricultural',
      'forestry',
      'emergency',
      'psv',
      'taxi', -- sub class of psv
      'share_taxi', -- sub class of psv
      'minibus', -- sub class of psv
      'bus', -- sub class of psv
      'foot',
      'emergency_vehicle',
      'restricted',
      'military',
      'official',
      'customers',
      'private',
      'delivery',
      'destination',
      'permit',
      'residents'
    },

    -- tags disallow access to in combination with highway=service
    service_access_tag_blacklist = Set {
        'private'
    },

    restricted_access_tag_list = Set {
      'private',
      'delivery',
      'destination',
      'customers',
      'permit',
      'residents',
      'unknown',
    },

    access_tags_hierarchy = Sequence {
      'motorcar',
      'motor_vehicle',
      'vehicle',
      'access'
    },

    service_tag_forbidden = Set {
      'emergency_access'
    },

    restrictions = Sequence {
      'motorcar',
      'motor_vehicle',
      'vehicle'
    },

    classes = Sequence {
        'toll', 'motorway', 'ferry', 'restricted', 'tunnel'
    },

    -- classes to support for exclude flags
    excludable = Sequence {
        Set {'toll'},
        Set {'motorway'},
        Set {'ferry'}
    },

    avoid = Set {
      'area',
      -- 'toll',    -- uncomment this to avoid tolls
      'reversible',
      'impassable',
      'hov_lanes',
      'steps',
      'construction',
      'proposed'
    },

    speeds = Sequence {
      highway = {
        motorway        = 90,
        motorway_link   = 45,
        trunk           = 85,
        trunk_link      = 40,
        primary         = 65,
        primary_link    = 30,
        secondary       = 55,
        secondary_link  = 25,
        tertiary        = 40,
        tertiary_link   = 20,
        unclassified    = 25,
        residential     = 25,
        living_street   = 10,
        service         = 15,
        -- winter highway types (OSM highway=winter_road / highway=ice_road)
        winter_road     = 20,
        ice_road        = 15
      }
    },

    service_penalties = {
      alley             = 0.5,
      parking           = 0.5,
      parking_aisle     = 0.5,
      driveway          = 0.5,
      ["drive-through"] = 0.5,
      ["drive-thru"] = 0.5
    },

    barrier_penalties = {
      gate      = 60,
      lift_gate = 60,
    },

    restricted_highway_whitelist = Set {
      'motorway',
      'motorway_link',
      'trunk',
      'trunk_link',
      'primary',
      'primary_link',
      'secondary',
      'secondary_link',
      'tertiary',
      'tertiary_link',
      'residential',
      'living_street',
      'unclassified',
      'service',
      'winter_road',
      'ice_road'
    },

    construction_whitelist = Set {
      'no',
      'widening',
      'minor',
    },

    route_speeds = {
      ferry = 5,
      shuttle_train = 10
    },

    bridge_speeds = {
      movable = 5
    },

    -- surface/trackype/smoothness
    -- values were estimated from looking at the photos at the relevant wiki pages

    -- max speed for surfaces
    surface_speeds = {
      asphalt = nil,    -- nil mean no limit. removing the line has the same effect
      concrete = nil,
      ["concrete:plates"] = nil,
      ["concrete:lanes"] = nil,
      paved = nil,

      cement = 80,
      compacted = 80,
      fine_gravel = 80,

      paving_stones = 60,
      metal = 60,
      bricks = 60,

      grass = 40,
      wood = 40,
      sett = 40,
      grass_paver = 40,
      gravel = 40,
      unpaved = 40,
      ground = 40,
      dirt = 40,
      pebblestone = 40,
      tartan = 40,

      cobblestone = 30,
      clay = 30,

      earth = 20,
      stone = 20,
      rocky = 20,
      sand = 20,

      laterite = 15,

      mud = 10,

      -- winter surfaces (OSM surface=ice / surface=snow)
      ice  = 20,
      snow = 30
    },

    -- max speed for tracktypes
    tracktype_speeds = {
      grade1 =  60,
      grade2 =  40,
      grade3 =  30,
      grade4 =  25,
      grade5 =  20
    },

    -- max speed for smoothnesses
    smoothness_speeds = {
      intermediate    =  80,
      bad             =  40,
      very_bad        =  20,
      horrible        =  10,
      very_horrible   =  5,
      impassable      =  0
    },

    -- http://wiki.openstreetmap.org/wiki/Speed_limits
    maxspeed_table_default = {
      urban = 50,
      rural = 90,
      trunk = 110,
      motorway = 130
    },

    -- List only exceptions
    maxspeed_table = {
      ["at:rural"] = 100,
      ["at:trunk"] = 100,
      ["ar:urban"] = 40,
      ["ar:rural"] = 110,      
      ["be:motorway"] = 120,
      ["be-bru:rural"] = 70,
      ["be-bru:urban"] = 30,
      ["be-vlg:rural"] = 70,
      ["bg:motorway"] = 140,
      ["by:urban"] = 60,
      ["by:motorway"] = 110,
      ["ca-on:rural"] = 80,
      ["ch:rural"] = 80,
      ["ch:trunk"] = 100,
      ["ch:motorway"] = 120,
      ["de:living_street"] = 7,
      ["de:rural"] = 100,
      ["de:motorway"] = 0,
      ["dk:rural"] = 80,
      ["es:trunk"] = 90,
      ["fr:rural"] = 80,
      ["gb:nsl_single"] = (60*1609)/1000,
      ["gb:nsl_dual"] = (70*1609)/1000,
      ["gb:motorway"] = (70*1609)/1000,
      ["lv:living_street"] = 20,
      ["nl:rural"] = 80,
      ["nl:trunk"] = 100,
      ['no:rural'] = 80,
      ['no:motorway'] = 110,
      ['ph:urban'] = 40,
      ['ph:rural'] = 80,
      ['ph:motorway'] = 100,
      ['pl:rural'] = 100,
      ['pl:expressway'] = 120,
      ['pl:motorway'] = 140,
      ["ro:trunk"] = 100,
      ["ru:living_street"] = 20,
      ["ru:urban"] = 60,
      ["ru:motorway"] = 110,
      ["uk:nsl_single"] = (60*1609)/1000,
      ["uk:nsl_dual"] = (70*1609)/1000,
      ["uk:motorway"] = (70*1609)/1000,
      ['za:urban'] = 60,
      ['za:rural'] = 100,
      ["none"] = 140
    },

    relation_types = Sequence {
      "route"
    },

    -- classify highway tags when necessary for turn weights
    highway_turn_classification = {
    },

    -- classify access tags when necessary for turn weights
    access_turn_classification = {
    }
  }
end

function process_node(profile, node, result, relations)
  -- parse access and barrier tags
  local access = resolve_access(find_access_tag(node, profile.access_tags_hierarchy), profile)
  if access then
    if profile.access_tag_blacklist[access] and not profile.restricted_access_tag_list[access] then
      obstacle_map:add(node, Obstacle.new(obstacle_type.barrier))
    end
  else
    local barrier = node:get_value_by_key("barrier")
    if barrier then
      --  check height restriction barriers
      local restricted_by_height = false
      if barrier == 'height_restrictor' then
         local maxheight = Measure.get_max_height(node:get_value_by_key("maxheight"), node)
         restricted_by_height = maxheight and maxheight < profile.vehicle_height
      end

      --  make an exception for rising bollard barriers
      local bollard = node:get_value_by_key("bollard")
      local rising_bollard = bollard and "rising" == bollard

      -- make an exception for lowered/flat barrier=kerb
      -- and incorrect tagging of highway crossing kerb as highway barrier
      local kerb = node:get_value_by_key("kerb")
      local highway = node:get_value_by_key("highway")
      local flat_kerb = kerb and ("lowered" == kerb or "flush" == kerb)
      local highway_crossing_kerb = barrier == "kerb" and highway and highway == "crossing"

      -- make an exception for fence with sensory=audible/audio (virtual livestock fences)
      local sensory = node:get_value_by_key("sensory")
      local audible_fence = barrier == "fence" and sensory and (sensory == "audible" or sensory == "audio")

      -- check if barrier has a configurable penalty (e.g., gates)
      local barrier_penalty = profile.barrier_penalties[barrier]

      if not profile.barrier_whitelist[barrier]
                and not rising_bollard
                and not flat_kerb
                and not highway_crossing_kerb
                and not audible_fence
                and not barrier_penalty
                or restricted_by_height then
        obstacle_map:add(node, Obstacle.new(obstacle_type.barrier))
      end

      -- apply configurable penalty to gates/lift_gates
      if barrier_penalty then
        obstacle_map:add(node, Obstacle.new(obstacle_type.gate,
                                            obstacle_direction.both, barrier_penalty, 0))
      end
    end
  end

  Obstacles.process_node(profile, node)
end


-- Tijdvak-congestie: schaal de definitieve wegsnelheid per OSM-wegklasse.
function apply_congestion(profile, way, result, data, relations)
  local hw = way:get_value_by_key("highway")
  local f = (hw and profile.congestion[hw]) or profile.congestion_default
  if result.forward_speed and result.forward_speed > 0 then
    result.forward_speed = math.max(3, result.forward_speed * f)
  end
  if result.backward_speed and result.backward_speed > 0 then
    result.backward_speed = math.max(3, result.backward_speed * f)
  end
end


-- Scenariolaag: wegvakken vlak bij een afsluitingspunt worden onbegaanbaar
-- duur. Een grote factor in plaats van verwijderen, zodat de graaf heel blijft
-- en een zonepaar zonder alternatief nog steeds een route houdt (die we in de
-- rapportage als "geen alternatief" markeren in plaats van als reistijd).
local BLOCK_CELL = 0.004
local BLOCK_RADIUS = 50
local BLOCKS = {
  ["1114:12978"] = {{4.459969,51.91362,500}},
  ["1139:12994"] = {{4.556192,51.9761,500}},
  ["1128:12982"] = {{4.513096,51.929573,500}},
  ["1117:12997"] = {{4.4705157,51.989597,500}},
  ["1116:12967"] = {{4.46512,51.871258,500}},
  ["1157:12995"] = {{4.6306987,51.98014,500}},
  ["1141:12965"] = {{4.565614,51.863342,500}},
  ["1134:12985"] = {{4.5376782,51.942642,500},{4.538041,51.941746,1.6}},
  ["1100:12979"] = {{4.4011006,51.917816,500},{4.4007487,51.9194,500}},
  ["1160:12958"] = {{4.642079,51.83578,500}},
  ["1082:12963"] = {{4.3289695,51.85287,500}},
  ["1150:12990"] = {{4.6035852,51.963028,500}},
  ["1094:12997"] = {{4.3791785,51.99121,500}},
  ["1155:12978"] = {{4.620953,51.915707,500}},
  ["1120:12977"] = {{4.4803877,51.90979,500}},
  ["1108:12984"] = {{4.4347105,51.937477,500}},
  ["1102:12967"] = {{4.4110484,51.86942,500}},
  ["1160:12959"] = {{4.641497,51.836575,500},{4.642525,51.83694,500},{4.6409183,51.836006,500}},
  ["1119:12990"] = {{4.4797735,51.96144,500},{4.4797735,51.96144,500}},
  ["1121:12972"] = {{4.4861298,51.890793,500},{4.48646,51.8881,500}},
  ["1115:12980"] = {{4.462335,51.921288,500}},
  ["1118:12984"] = {{4.4747553,51.938374,500}},
  ["1114:12975"] = {{4.459279,51.902172,500}},
  ["1087:12968"] = {{4.349995,51.872345,500}},
  ["1120:12980"] = {{4.4826274,51.92218,500}},
  ["1078:12962"] = {{4.313766,51.84983,500}},
  ["1089:12965"] = {{4.3589654,51.862362,500}},
  ["1109:12984"] = {{4.436202,51.936066,500}},
  ["1107:12986"] = {{4.4285245,51.94564,500}},
  ["1089:12964"] = {{4.3569813,51.85948,500}},
  ["1121:12986"] = {{4.4846535,51.944508,500}},
  ["1151:12987"] = {{4.604978,51.951393,500}},
  ["1080:12958"] = {{4.320069,51.834137,500}},
  ["1116:12980"] = {{4.467972,51.922165,500}},
  ["1141:12989"] = {{4.566055,51.95983,500}},
  ["1140:12996"] = {{4.563297,51.98553,500}},
  ["1151:12993"] = {{4.606449,51.973515,500}},
  ["1093:12996"] = {{4.3745813,51.98604,500}},
  ["1115:12978"] = {{4.460046,51.912342,500}},
  ["1137:12973"] = {{4.551486,51.894047,500}},
  ["1079:12958"] = {{4.3168683,51.83277,500}},
  ["1101:12988"] = {{4.40649,51.95247,500}},
  ["1139:12969"] = {{4.5567327,51.877758,500}},
  ["1106:12965"] = {{4.4244523,51.86039,500}},
  ["1108:12982"] = {{4.4329543,51.929333,500}},
  ["1120:12990"] = {{4.4815516,51.960594,500}},
  ["1151:12991"] = {{4.6042027,51.965775,500}},
  ["1101:12980"] = {{4.4067526,51.92083,500}},
  ["1117:12982"] = {{4.47081,51.930424,500},{4.470458,51.93031,1.6},{4.4699597,51.930916,1.6}},
  ["1152:12978"] = {{4.60928,51.915398,500}},
  ["1087:12998"] = {{4.350784,51.994415,500}},
  ["1130:12969"] = {{4.5206375,51.879604,500}},
  ["1095:12977"] = {{4.3801847,51.911247,500},{4.381466,51.910583,500}},
  ["1117:12969"] = {{4.4697385,51.876602,500}},
  ["1158:12991"] = {{4.6356316,51.965717,500}},
  ["1095:12979"] = {{4.38074,51.91995,500}},
  ["1092:12999"] = {{4.3717604,51.997185,500},{4.370381,51.999744,500}},
  ["1089:12980"] = {{4.359684,51.921593,500}},
  ["1122:12999"] = {{4.488813,51.999966,500}},
  ["1121:12983"] = {{4.484895,51.933315,500}},
  ["1150:12994"] = {{4.602763,51.977978,500}},
  ["1144:12980"] = {{4.5760875,51.92078,500}},
  ["1121:12984"] = {{4.484478,51.93974,500}},
  ["1094:12963"] = {{4.3780737,51.855446,500}},
  ["1098:12979"] = {{4.393041,51.91727,500}},
  ["1128:12972"] = {{4.5127444,51.88999,500}},
  ["1139:12977"] = {{4.558623,51.911797,500}},
  ["1122:12980"] = {{4.490764,51.92009,500}},
  ["1112:12997"] = {{4.4510064,51.989628,500}},
  ["1093:12984"] = {{4.375945,51.937614,500}},
  ["1139:12972"] = {{4.558592,51.89051,500}},
  ["1143:12991"] = {{4.574651,51.964348,500}},
  ["1130:12980"] = {{4.5233383,51.920334,500}},
  ["1076:12966"] = {{4.307388,51.866634,1.6}},
  ["1160:12962"] = {{4.6426992,51.848366,1.6}},
  ["1140:12982"] = {{4.563548,51.928795,1.6}},
  ["1122:12979"] = {{4.4902196,51.91987,1.6}},
  ["1158:12983"] = {{4.634945,51.933655,1.6}},
  ["1094:12972"] = {{4.376996,51.89088,1.6}},
  ["1089:12994"] = {{4.356544,51.9783,1.6}},
  ["1111:12967"] = {{4.447354,51.868786,1.6}},
  ["1137:12963"] = {{4.5490894,51.85529,1.6}},
  ["1081:12978"] = {{4.3276615,51.912964,1.6}},
  ["1081:12963"] = {{4.327423,51.85401,1.6}},
  ["1078:12998"] = {{4.315718,51.994526,1.6}},
  ["1127:12996"] = {{4.5085387,51.98605,1.6}},
  ["1116:12978"] = {{4.4655166,51.914307,1.6}},
  ["1082:12971"] = {{4.3291993,51.884945,1.6}},
  ["1140:12989"] = {{4.561677,51.957462,1.6}},
  ["1148:12999"] = {{4.5931754,51.99954,1.6}},
  ["1101:12981"] = {{4.4074283,51.924026,1.6}},
  ["1077:12962"] = {{4.31068,51.850796,1.6}},
  ["1100:12978"] = {{4.403381,51.913784,1.6}},
  ["1151:12981"] = {{4.604979,51.925358,1.6}},
  ["1102:12966"] = {{4.409639,51.864986,1.6}},
  ["1128:12997"] = {{4.5151477,51.9908,1.6}},
  ["1105:12971"] = {{4.4237814,51.88617,1.6}},
  ["1112:12998"] = {{4.451111,51.993,1.6}},
  ["1116:12977"] = {{4.464869,51.909664,1.6}},
  ["1083:12996"] = {{4.3346424,51.984398,1.6}},
  ["1089:12979"] = {{4.358453,51.916885,1.6}}
}

local function cellkey(lon, lat)
  return math.floor(lon / BLOCK_CELL) .. ":" .. math.floor(lat / BLOCK_CELL)
end

function process_segment(profile, segment)
  local mlon = (segment.source.lon + segment.target.lon) * 0.5
  local mlat = (segment.source.lat + segment.target.lat) * 0.5
  local gx = math.floor(mlon / BLOCK_CELL)
  local gy = math.floor(mlat / BLOCK_CELL)
  local kx = math.cos(mlat * math.pi / 180) * 111320
  for dx = -1, 1 do
    for dy = -1, 1 do
      local bucket = BLOCKS[(gx + dx) .. ":" .. (gy + dy)]
      if bucket then
        for i = 1, #bucket do
          local p = bucket[i]
          local ddx = (p[1] - mlon) * kx
          local ddy = (p[2] - mlat) * 110540
          if ddx * ddx + ddy * ddy <= BLOCK_RADIUS * BLOCK_RADIUS then
            segment.weight = segment.weight * p[3]
            segment.duration = segment.duration * p[3]
            return
          end
        end
      end
    end
  end
end

function process_way(profile, way, result, relations)
  -- the intial filtering of ways based on presence of tags
  -- affects processing times significantly, because all ways
  -- have to be checked.
  -- to increase performance, prefetching and intial tag check
  -- is done in directly instead of via a handler.

  -- in general we should  try to abort as soon as
  -- possible if the way is not routable, to avoid doing
  -- unnecessary work. this implies we should check things that
  -- commonly forbids access early, and handle edge cases later.

  -- data table for storing intermediate values during processing
  local data = {
    -- prefetch tags
    highway = way:get_value_by_key('highway'),
    bridge = way:get_value_by_key('bridge'),
    route = way:get_value_by_key('route')
  }

  -- perform an quick initial check and abort if the way is
  -- obviously not routable.
  -- highway or route tags must be in data table, bridge is optional
  if (not data.highway or data.highway == '') and
  (not data.route or data.route == '')
  then
    return
  end

  handlers = Sequence {
    -- set the default mode for this profile. if can be changed later
    -- in case it turns we're e.g. on a ferry
    WayHandlers.default_mode,

    -- check various tags that could indicate that the way is not
    -- routable. this includes things like status=impassable,
    -- toll=yes and oneway=reversible
    WayHandlers.blocked_ways,
    WayHandlers.avoid_ways,
    WayHandlers.handle_height,
    WayHandlers.handle_width,
    WayHandlers.handle_length,
    WayHandlers.handle_weight,

    -- determine access status by checking our hierarchy of
    -- access tags, e.g: motorcar, motor_vehicle, vehicle
    WayHandlers.access,

    -- check whether forward/backward directions are routable
    WayHandlers.oneway,

    -- check a road's destination
    WayHandlers.destinations,

    -- check whether we're using a special transport mode
    WayHandlers.ferries,
    WayHandlers.movables,

    -- handle service road restrictions
    WayHandlers.service,

    -- handle hov
    WayHandlers.hov,

    -- compute speed taking into account way type, maxspeed tags, etc.
    WayHandlers.speed,
    WayHandlers.maxspeed,
    WayHandlers.surface,

    -- apply vehicle-specific maximum speed cap before calculating rates
    WayHandlers.vehicle_speed_cap,

    WayHandlers.penalties,

    -- compute class labels
    WayHandlers.classes,

    -- handle turn lanes and road classification, used for guidance
    WayHandlers.turn_lanes,
    WayHandlers.classification,

    -- handle various other flags
    WayHandlers.roundabouts,
    WayHandlers.startpoint,
    WayHandlers.driving_side,

    -- set name, ref and pronunciation
    WayHandlers.names,

    -- set weight properties of the way
    apply_congestion,

    WayHandlers.weights,

    -- set classification of ways relevant for turns
    WayHandlers.way_classification_for_turn
  }

  WayHandlers.run(profile, way, result, data, handlers, relations)

  if profile.cardinal_directions then
      Relations.process_way_refs(way, relations, result)
  end
end

function process_turn(profile, turn)
  -- Use a sigmoid function to return a penalty that maxes out at turn_penalty
  -- over the space of 0-180 degrees.  Values here were chosen by fitting
  -- the function to some turn penalty samples from real driving.
  local turn_penalty = profile.turn_penalty
  local turn_bias = turn.is_left_hand_driving and 1. / profile.turn_bias or profile.turn_bias

  for _, obs in pairs(obstacle_map:get(turn.from, turn.via)) do
    -- disregard a minor stop if entering by the major road
    -- rationale: if a stop sign is tagged at the center of the intersection with stop=minor
    -- it should only penalize the minor roads entering the intersection
    if obs.type == obstacle_type.stop_minor and not Obstacles.entering_by_minor_road(turn) then
        goto skip
    end
    -- heuristic to infer the direction of a stop without an explicit direction tag
    -- rationale: a stop sign should not be placed farther than 20m from the intersection
    if turn.number_of_roads == 2
        and obs.type == obstacle_type.stop
        and obs.direction == obstacle_direction.none
        and turn.source_road.distance < 20
        and turn.target_road.distance > 20 then
            goto skip
    end
    turn.duration = turn.duration + obs.duration
    ::skip::
  end

  if turn.number_of_roads > 2 or turn.source_mode ~= turn.target_mode or turn.is_u_turn then
    if turn.angle >= 0 then
      turn.duration = turn.duration + turn_penalty / (1 + math.exp( -((13 / turn_bias) *  turn.angle/180 - 6.5*turn_bias)))
    else
      turn.duration = turn.duration + turn_penalty / (1 + math.exp( -((13 * turn_bias) * -turn.angle/180 - 6.5/turn_bias)))
    end

    if turn.is_u_turn then
      turn.duration = turn.duration + profile.properties.u_turn_penalty
    end
  end

  -- for distance based routing we don't want to have penalties based on turn angle
  if profile.properties.weight_name == 'distance' then
     turn.weight = 0
  else
     turn.weight = turn.duration
  end

  if profile.properties.weight_name == 'routability' then
      -- penalize turns from non-local access only segments onto local access only tags
      if not turn.source_restricted and turn.target_restricted then
          turn.weight = constants.max_turn_weight
      end
  end
end

return {
  setup = setup,
  process_way = process_way,
  process_node = process_node,
  process_segment = process_segment,
  process_turn = process_turn
}
