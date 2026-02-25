/**
 * ILS Fixture Definitions
 * Defines the demo rig fixtures with their DMX addresses and channel mappings.
 */

const FIXTURE_TYPES = {
    MOVER: 'mover',
    WASH: 'wash',
    LED_BAR: 'bar'
};

const FIXTURE_ROLES = {
    BEAM: 'beam',
    SPOT: 'spot',
    EFFECT: 'effect'
};

const CAPABILITY_PROFILES = {
    beam: {
        supports_gobo: true,
        supports_prism: true,
        supports_frost: true,
        supports_zoom: false,
        supports_focus: true,
        supports_iris: false,
        movement_speed_class: 'fast'
    },
    spot: {
        supports_gobo: true,
        supports_prism: false,
        supports_frost: true,
        supports_zoom: true,
        supports_focus: true,
        supports_iris: true,
        movement_speed_class: 'medium'
    },
    effect: {
        supports_gobo: false,
        supports_prism: false,
        supports_frost: false,
        supports_zoom: false,
        supports_focus: false,
        supports_iris: false,
        movement_speed_class: 'static'
    }
};

const MOTION_LIMIT_DEFAULTS = {
    mover: {
        pan: {
            maxVelocity: 4.2,      // ~240°/s
            maxAcceleration: 10.5, // ~600°/s²
            maxJerk: 65.0          // ~3700°/s³
        },
        tilt: {
            maxVelocity: 3.5,      // ~200°/s
            maxAcceleration: 8.8,  // ~500°/s²
            maxJerk: 55.0          // ~3150°/s³
        }
    },
    wash: {
        pan: {
            maxVelocity: 3.4,
            maxAcceleration: 7.0,
            maxJerk: 38.0
        },
        tilt: {
            maxVelocity: 2.8,
            maxAcceleration: 5.9,
            maxJerk: 30.0
        }
    },
    bar: {
        pan: { maxVelocity: 0, maxAcceleration: 0, maxJerk: 0 },
        tilt: { maxVelocity: 0, maxAcceleration: 0, maxJerk: 0 }
    }
};

// Channel mappings for each fixture type
const CHANNEL_MAPS = {
    // Moving Head - 16 channels
    mover: {
        channels: 16,
        pan: 0,           // Coarse
        panFine: 1,       // Fine
        tilt: 2,          // Coarse
        tiltFine: 3,      // Fine
        speed: 4,         // Pan/Tilt speed
        dimmer: 5,
        shutter: 6,       // 0-31 closed, 32-63 open, 64-95 strobe slow-fast
        red: 7,
        green: 8,
        blue: 9,
        white: 10,
        colorWheel: 11,
        gobo: 12,
        goboRotation: 13,
        prism: 14,
        focus: 15
    },

    // Wash - 14 channels
    wash: {
        channels: 14,
        pan: 0,
        panFine: 1,
        tilt: 2,
        tiltFine: 3,
        speed: 4,
        dimmer: 5,
        shutter: 6,
        red: 7,
        green: 8,
        blue: 9,
        white: 10,
        zoom: 11,
        colorTemp: 12,
        control: 13
    },

    // LED Bar - 12 channels
    bar: {
        channels: 12,
        dimmer: 0,
        strobe: 1,
        red: 2,
        green: 3,
        blue: 4,
        white: 5,
        amber: 6,
        uv: 7,
        macro: 8,
        speed: 9,
        mode: 10,
        control: 11
    }
};

// Demo rig fixture definitions
// Positioned in a stage-like layout
const FIXTURES = [
    // Moving Heads - Left side (upstage to downstage)
    { name: "Mover L1", type: FIXTURE_TYPES.MOVER, address: 1,   position: { x: -6, y: 4, z: -4 } },
    { name: "Mover L2", type: FIXTURE_TYPES.MOVER, address: 17,  position: { x: -6, y: 4, z: -1.5 } },
    { name: "Mover L3", type: FIXTURE_TYPES.MOVER, address: 33,  position: { x: -6, y: 4, z: 1.5 } },
    { name: "Mover L4", type: FIXTURE_TYPES.MOVER, address: 49,  position: { x: -6, y: 4, z: 4 } },

    // Moving Heads - Right side (upstage to downstage)
    { name: "Mover R1", type: FIXTURE_TYPES.MOVER, address: 65,  position: { x: 6, y: 4, z: -4 } },
    { name: "Mover R2", type: FIXTURE_TYPES.MOVER, address: 81,  position: { x: 6, y: 4, z: -1.5 } },
    { name: "Mover R3", type: FIXTURE_TYPES.MOVER, address: 97,  position: { x: 6, y: 4, z: 1.5 } },
    { name: "Mover R4", type: FIXTURE_TYPES.MOVER, address: 113, position: { x: 6, y: 4, z: 4 } },

    // Washes - Left side (3 units on truss)
    { name: "Wash L1", type: FIXTURE_TYPES.WASH, address: 129, position: { x: -4, y: 3.5, z: -3 } },
    { name: "Wash L2", type: FIXTURE_TYPES.WASH, address: 143, position: { x: -4, y: 3.5, z: 0 } },
    { name: "Wash L3", type: FIXTURE_TYPES.WASH, address: 157, position: { x: -4, y: 3.5, z: 3 } },

    // Washes - Right side (3 units on truss)
    { name: "Wash R1", type: FIXTURE_TYPES.WASH, address: 171, position: { x: 4, y: 3.5, z: -3 } },
    { name: "Wash R2", type: FIXTURE_TYPES.WASH, address: 185, position: { x: 4, y: 3.5, z: 0 } },
    { name: "Wash R3", type: FIXTURE_TYPES.WASH, address: 199, position: { x: 4, y: 3.5, z: 3 } },

    // LED Bars - Back wall (left to right)
    { name: "Bar L1", type: FIXTURE_TYPES.LED_BAR, address: 213, position: { x: -3, y: 2, z: -5 }, rotation: { x: 0, y: 0, z: 0 } },
    { name: "Bar L2", type: FIXTURE_TYPES.LED_BAR, address: 225, position: { x: -1, y: 2, z: -5 }, rotation: { x: 0, y: 0, z: 0 } },
    { name: "Bar R1", type: FIXTURE_TYPES.LED_BAR, address: 237, position: { x: 1, y: 2, z: -5 }, rotation: { x: 0, y: 0, z: 0 } },
    { name: "Bar R2", type: FIXTURE_TYPES.LED_BAR, address: 249, position: { x: 3, y: 2, z: -5 }, rotation: { x: 0, y: 0, z: 0 } },
];

/**
 * Get DMX channel value for a fixture
 */
function getChannelValue(dmxData, fixture, channelName) {
    const channelMap = CHANNEL_MAPS[fixture.type];
    if (!channelMap || channelMap[channelName] === undefined) {
        return 0;
    }
    const channelOffset = channelMap[channelName];
    const address = fixture.address - 1 + channelOffset; // DMX is 1-indexed
    return dmxData[address] || 0;
}

/**
 * Get color from fixture DMX values
 */
function getFixtureColor(dmxData, fixture) {
    const r = getChannelValue(dmxData, fixture, 'red') / 255;
    const g = getChannelValue(dmxData, fixture, 'green') / 255;
    const b = getChannelValue(dmxData, fixture, 'blue') / 255;
    return { r, g, b };
}

/**
 * Get dimmer value (0-1) from fixture
 */
function getFixtureDimmer(dmxData, fixture) {
    return getChannelValue(dmxData, fixture, 'dimmer') / 255;
}

/**
 * Get pan/tilt angles for moving fixtures (in radians)
 */
function getFixturePanTilt(dmxData, fixture) {
    if (fixture.type === FIXTURE_TYPES.LED_BAR) {
        return { pan: 0, tilt: 0 };
    }

    // Get coarse and fine values
    const panCoarse = getChannelValue(dmxData, fixture, 'pan');
    const panFine = getChannelValue(dmxData, fixture, 'panFine');
    const tiltCoarse = getChannelValue(dmxData, fixture, 'tilt');
    const tiltFine = getChannelValue(dmxData, fixture, 'tiltFine');

    // Combine coarse and fine (16-bit resolution)
    const panValue = (panCoarse * 256 + panFine) / 65535;
    const tiltValue = (tiltCoarse * 256 + tiltFine) / 65535;

    // Convert to radians (540 degree pan, 270 degree tilt typical)
    const pan = (panValue - 0.5) * Math.PI * 3;   // -270 to +270 degrees
    const tilt = (tiltValue - 0.5) * Math.PI * 1.5; // -135 to +135 degrees

    return { pan, tilt };
}

/**
 * Check if fixture shutter is open
 */
function isShutterOpen(dmxData, fixture) {
    const shutter = getChannelValue(dmxData, fixture, 'shutter');
    // Typically: 0-31 closed, 32+ open (with strobe effects at higher values)
    return shutter >= 32;
}

/**
 * Get semantic fixture role for look logic.
 * Beam and spot are role groupings, not strict hardware limits.
 */
function getFixtureRole(fixture) {
    if (fixture.type === FIXTURE_TYPES.MOVER) return FIXTURE_ROLES.BEAM;
    if (fixture.type === FIXTURE_TYPES.WASH) return FIXTURE_ROLES.SPOT;
    return FIXTURE_ROLES.EFFECT;
}

function getFixtureCapabilities(fixture) {
    const role = getFixtureRole(fixture);
    return CAPABILITY_PROFILES[role] || CAPABILITY_PROFILES.effect;
}

function getFixtureMotionLimits(fixture) {
    const defaults = MOTION_LIMIT_DEFAULTS[fixture.type] || MOTION_LIMIT_DEFAULTS.bar;
    const custom = fixture.motion_limits || {};

    return {
        pan: {
            ...defaults.pan,
            ...(custom.pan || {})
        },
        tilt: {
            ...defaults.tilt,
            ...(custom.tilt || {})
        }
    };
}
