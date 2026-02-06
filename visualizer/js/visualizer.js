/**
 * ILS 3D Visualizer - Optimized
 * Three.js-based lighting visualization for the Intelligent Lighting System
 */

class ILSVisualizer {
    constructor() {
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;

        this.fixtures = [];
        this.dmxData = new Array(512).fill(0);
        this.audioData = null;

        this.showGrid = true;
        this.showLabels = true;
        this.testMode = false;
        this.testPhase = 0;

        this.frameCount = 0;
        this.lastFpsUpdate = 0;
        this.lastDmxUpdate = 0;

        this.ws = null;
        this.wsReconnectTimer = null;
        this.wsReconnectDelay = 1000; // BUG-029 fix: exponential backoff starting at 1s

        // BUG-028 fix: reusable color object to avoid GC pressure
        this._tempColor = new THREE.Color();

        this.init();
    }

    init() {
        // Hide loading indicator
        const loading = document.getElementById('loading');
        if (loading) loading.classList.add('hidden');

        // Scene setup - minimal fog for performance
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x0a0a0a);

        // Camera
        this.camera = new THREE.PerspectiveCamera(
            60,
            window.innerWidth / window.innerHeight,
            0.1,
            100
        );
        this.camera.position.set(0, 8, 15);
        this.camera.lookAt(0, 2, 0);

        // Renderer - optimized settings
        const canvas = document.getElementById('visualizer');
        this.renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: false,  // Disable for performance
            powerPreference: 'high-performance'
        });
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(1);  // Force 1:1 for performance
        this.renderer.shadowMap.enabled = false;  // Disable shadows

        // Controls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 5;
        this.controls.maxDistance = 40;

        // Build the scene
        this.createStage();
        this.createFixtures();
        this.createLighting();
        this.createAudioMonitor();

        // Event listeners
        window.addEventListener('resize', () => this.onResize());
        this.setupUI();

        // Connect to WebSocket
        this.connectWebSocket();

        // Start render loop
        this.animate();
    }

    createStage() {
        // Simple floor
        const floorGeometry = new THREE.PlaneGeometry(20, 16);
        const floorMaterial = new THREE.MeshBasicMaterial({ color: 0x1a1a1a });
        const floor = new THREE.Mesh(floorGeometry, floorMaterial);
        floor.rotation.x = -Math.PI / 2;
        this.scene.add(floor);

        // Grid
        this.grid = new THREE.GridHelper(20, 20, 0x333333, 0x222222);
        this.grid.position.y = 0.01;
        this.scene.add(this.grid);

        // Back wall
        const wallGeometry = new THREE.PlaneGeometry(20, 8);
        const wallMaterial = new THREE.MeshBasicMaterial({ color: 0x151515 });
        const backWall = new THREE.Mesh(wallGeometry, wallMaterial);
        backWall.position.set(0, 4, -6);
        this.scene.add(backWall);

        // Simple truss lines
        this.createTruss(-6, 4, -4, -6, 4, 4);
        this.createTruss(6, 4, -4, 6, 4, 4);
        this.createTruss(-4, 3.5, -3, -4, 3.5, 3);
        this.createTruss(4, 3.5, -3, 4, 3.5, 3);
    }

    createTruss(x1, y1, z1, x2, y2, z2) {
        const points = [
            new THREE.Vector3(x1, y1, z1),
            new THREE.Vector3(x2, y2, z2)
        ];
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const material = new THREE.LineBasicMaterial({ color: 0x444444 });
        this.scene.add(new THREE.Line(geometry, material));
    }

    createFixtures() {
        FIXTURES.forEach((fixtureDef) => {
            const fixture = this.createFixture(fixtureDef);
            this.fixtures.push({
                definition: fixtureDef,
                ...fixture
            });
        });
    }

    createFixture(def) {
        const group = new THREE.Group();
        group.position.set(def.position.x, def.position.y, def.position.z);

        // Fixture body - simple box
        const bodyGeometry = new THREE.BoxGeometry(
            def.type === FIXTURE_TYPES.LED_BAR ? 1.5 : 0.3,
            def.type === FIXTURE_TYPES.LED_BAR ? 0.15 : 0.3,
            0.3
        );
        const bodyMaterial = new THREE.MeshBasicMaterial({ color: 0x333333 });
        const body = new THREE.Mesh(bodyGeometry, bodyMaterial);
        group.add(body);

        // Light emitter (glowing part)
        let emitter, beam;

        if (def.type === FIXTURE_TYPES.LED_BAR) {
            // LED bar - horizontal emitter
            const emitterGeom = new THREE.PlaneGeometry(1.4, 0.1);
            const emitterMat = new THREE.MeshBasicMaterial({
                color: 0x000000,
                transparent: true
            });
            emitter = new THREE.Mesh(emitterGeom, emitterMat);
            emitter.position.z = 0.16;
            group.add(emitter);
        } else {
            // Moving head - create head group for pan/tilt
            const headGroup = new THREE.Group();

            // Lens/emitter
            const emitterGeom = new THREE.CircleGeometry(0.1, 8);
            const emitterMat = new THREE.MeshBasicMaterial({
                color: 0x000000,
                transparent: true
            });
            emitter = new THREE.Mesh(emitterGeom, emitterMat);
            emitter.rotation.x = -Math.PI / 2;
            emitter.position.y = -0.2;
            headGroup.add(emitter);

            // Volumetric beam cone
            const beamLength = 10;
            const beamTopRadius = 0.05;  // Small at fixture lens
            const beamBottomRadius = 1.2; // Wide at floor
            const beamGeom = new THREE.ConeGeometry(
                beamBottomRadius,  // radius at base
                beamLength,        // height
                16,                // radial segments
                1,                 // height segments
                true               // open ended
            );
            // Rotate so cone points down from fixture
            beamGeom.rotateX(Math.PI);
            beamGeom.translate(0, -beamLength / 2 - 0.2, 0);

            // Custom shader material for gradient fade
            const beamMat = new THREE.ShaderMaterial({
                uniforms: {
                    color: { value: new THREE.Color(1, 1, 1) },
                    intensity: { value: 0.0 }
                },
                vertexShader: `
                    varying float vHeight;
                    void main() {
                        vHeight = position.y;
                        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                    }
                `,
                fragmentShader: `
                    uniform vec3 color;
                    uniform float intensity;
                    varying float vHeight;
                    void main() {
                        // Gradient: bright at top (fixture), fading toward bottom (floor)
                        float normalizedHeight = clamp((vHeight + 10.2) / 10.0, 0.0, 1.0);
                        float alpha = normalizedHeight * normalizedHeight * intensity * 0.6;
                        gl_FragColor = vec4(color, alpha);
                    }
                `,
                transparent: true,
                side: THREE.DoubleSide,
                depthWrite: false,
                blending: THREE.AdditiveBlending
            });
            beam = new THREE.Mesh(beamGeom, beamMat);
            headGroup.add(beam);

            group.add(headGroup);
            group.userData.headGroup = headGroup;
        }

        this.scene.add(group);

        // Simple text label using sprite
        const label = this.createLabel(def.name);
        label.position.copy(group.position);
        label.position.y += 0.5;
        this.scene.add(label);

        return { group, body, emitter, beam, label };
    }

    createLabel(text) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 128;
        canvas.height = 32;

        ctx.fillStyle = 'rgba(0,0,0,0.5)';
        ctx.fillRect(0, 0, 128, 32);
        ctx.font = '14px Arial';
        ctx.fillStyle = '#fff';
        ctx.textAlign = 'center';
        ctx.fillText(text, 64, 20);

        const texture = new THREE.CanvasTexture(canvas);
        const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
        const sprite = new THREE.Sprite(material);
        sprite.scale.set(1, 0.25, 1);
        return sprite;
    }

    createLighting() {
        // Single ambient light only
        const ambient = new THREE.AmbientLight(0x222222);
        this.scene.add(ambient);
    }

    createAudioMonitor() {
        // Create audio monitor canvas
        this.audioCanvas = document.createElement('canvas');
        this.audioCanvas.id = 'audio-monitor';
        this.audioCanvas.width = 200;
        this.audioCanvas.height = 60;
        this.audioCanvas.style.cssText = `
            position: absolute;
            bottom: 70px;
            right: 20px;
            background: rgba(0,0,0,0.7);
            border: 1px solid #333;
            border-radius: 4px;
        `;
        document.getElementById('container').appendChild(this.audioCanvas);
        this.audioCtx = this.audioCanvas.getContext('2d');

        // Add label
        const label = document.createElement('div');
        label.style.cssText = `
            position: absolute;
            bottom: 135px;
            right: 20px;
            color: #666;
            font-size: 11px;
        `;
        label.textContent = 'Audio Input';
        document.getElementById('container').appendChild(label);
    }

    updateAudioMonitor() {
        const ctx = this.audioCtx;
        const w = this.audioCanvas.width;
        const h = this.audioCanvas.height;

        // Clear
        ctx.fillStyle = '#0a0a0a';
        ctx.fillRect(0, 0, w, h);

        if (!this.audioData || !this.audioData.spectrum) {
            // No audio data - show message
            ctx.fillStyle = '#444';
            ctx.font = '11px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('No audio data', w/2, h/2 + 4);
            return;
        }

        const spectrum = this.audioData.spectrum;
        const barCount = Math.min(spectrum.length, 32);
        const barWidth = (w - 10) / barCount;
        const maxHeight = h - 10;

        // Draw spectrum bars
        for (let i = 0; i < barCount; i++) {
            const value = spectrum[i] || 0;
            const barHeight = (value / 255) * maxHeight;

            // Color gradient based on frequency
            const hue = (i / barCount) * 120; // Green to red
            ctx.fillStyle = `hsl(${120 - hue}, 80%, 50%)`;

            ctx.fillRect(
                5 + i * barWidth,
                h - 5 - barHeight,
                barWidth - 1,
                barHeight
            );
        }

        // Draw level indicators
        if (this.audioData.rms !== undefined) {
            const rms = this.audioData.rms;
            ctx.fillStyle = '#4ade80';
            ctx.font = '10px monospace';
            ctx.textAlign = 'left';
            ctx.fillText(`RMS: ${(rms * 100).toFixed(0)}%`, 5, 12);
        }
    }

    updateFixtures() {
        const now = performance.now();

        // Throttle updates to 30fps max
        if (now - this.lastDmxUpdate < 33) return;
        this.lastDmxUpdate = now;

        this.fixtures.forEach((fixture) => {
            const def = fixture.definition;
            const dmx = this.dmxData;

            // Get fixture values
            const color = getFixtureColor(dmx, def);
            const dimmer = getFixtureDimmer(dmx, def);
            const { pan, tilt } = getFixturePanTilt(dmx, def);
            const shutterOpen = def.type === FIXTURE_TYPES.LED_BAR || isShutterOpen(dmx, def);

            const intensity = shutterOpen ? dimmer : 0;
            const r = Math.floor(color.r * 255);
            const g = Math.floor(color.g * 255);
            const b = Math.floor(color.b * 255);

            // BUG-028 fix: reuse color object instead of allocating new THREE.Color per frame
            if (fixture.emitter) {
                this._tempColor.setRGB(
                    color.r * intensity,
                    color.g * intensity,
                    color.b * intensity
                );
                fixture.emitter.material.color.copy(this._tempColor);
            }

            // Update beam for movers/washes
            if (fixture.beam && fixture.group.userData.headGroup) {
                // Update shader uniforms for volumetric beam
                if (fixture.beam.material.uniforms) {
                    fixture.beam.material.uniforms.color.value.setRGB(color.r, color.g, color.b);
                    fixture.beam.material.uniforms.intensity.value = intensity;
                } else {
                    // Fallback for non-shader material
                    fixture.beam.material.color.setRGB(color.r, color.g, color.b);
                    fixture.beam.material.opacity = intensity * 0.5;
                }

                // Apply pan/tilt
                fixture.group.userData.headGroup.rotation.y = pan;
                fixture.group.userData.headGroup.rotation.x = tilt;
            }

            // Update label visibility
            if (fixture.label) {
                fixture.label.visible = this.showLabels;
            }
        });
    }

    runTestMode() {
        if (!this.testMode) return;

        this.testPhase += 0.025;

        // Simulate beat every ~0.5 seconds (120 BPM)
        const beatPhase = (this.testPhase * 2) % 1;
        const onBeat = beatPhase < 0.1;

        // Test pattern cycles through different movement styles
        const patternCycle = Math.floor(this.testPhase / 8) % 5;

        for (let i = 0; i < FIXTURES.length; i++) {
            const fixture = FIXTURES[i];
            const baseAddr = fixture.address - 1;
            const channelMap = CHANNEL_MAPS[fixture.type];

            // More dramatic dimmer with beat pulse
            const baseDimmer = 0.7;
            const beatPulse = onBeat ? 0.3 : 0;
            const dimmerValue = Math.min(1, baseDimmer + beatPulse + Math.sin(this.testPhase + i * 0.2) * 0.15);
            this.dmxData[baseAddr + channelMap.dimmer] = Math.floor(dimmerValue * 255);

            // Vibrant color cycling
            const colorPhase = this.testPhase * 0.3 + i * 0.15;
            const hue = (colorPhase * 60) % 360;
            const rgb = this.hsvToRgb(hue, 0.9, 1);
            this.dmxData[baseAddr + channelMap.red] = Math.floor(rgb.r * 255);
            this.dmxData[baseAddr + channelMap.green] = Math.floor(rgb.g * 255);
            this.dmxData[baseAddr + channelMap.blue] = Math.floor(rgb.b * 255);

            if (fixture.type !== FIXTURE_TYPES.LED_BAR) {
                const isLeftSide = fixture.position.x < 0;
                const fixturePhase = i / FIXTURES.length;

                let pan, tilt;

                switch (patternCycle) {
                    case 0: // True Circle - all fixtures circle together
                        pan = Math.sin(this.testPhase * 1.5 + fixturePhase * Math.PI * 2) * 0.35 + 0.5;
                        tilt = Math.cos(this.testPhase * 1.5 + fixturePhase * Math.PI * 2) * 0.2 + 0.55;
                        break;

                    case 1: // Mirror sweep - left/right opposite
                        const mirrorDir = isLeftSide ? 1 : -1;
                        pan = Math.sin(this.testPhase * 1.2) * 0.4 * mirrorDir + 0.5;
                        tilt = Math.sin(this.testPhase * 0.8) * 0.15 + 0.55;
                        break;

                    case 2: // Chase wave left to right
                        const chasePhase = this.testPhase * 1.5 - (fixture.position.x + 6) / 12;
                        pan = Math.sin(chasePhase * Math.PI * 2) * 0.35 + 0.5;
                        tilt = 0.55 + Math.sin(chasePhase * Math.PI * 2) * 0.1;
                        break;

                    case 3: // Alternating odd/even
                        const oddEven = i % 2 === 0 ? 1 : -1;
                        pan = Math.sin(this.testPhase * 1.3) * 0.3 * oddEven + 0.5;
                        tilt = Math.sin(this.testPhase * 0.9) * 0.2 * oddEven + 0.55;
                        break;

                    case 4: // Ballyhoo - dramatic figure-8 with offset
                        const ballyhooPhase = this.testPhase * 0.8 + i * 0.1;
                        pan = Math.sin(ballyhooPhase) * 0.45 + 0.5;
                        tilt = Math.sin(ballyhooPhase * 2 + i * 0.2) * 0.25 + 0.55;
                        break;

                    default:
                        pan = 0.5;
                        tilt = 0.55;
                }

                // Convert 0-1 to DMX (full range for dramatic movement)
                this.dmxData[baseAddr + channelMap.pan] = Math.floor(pan * 255);
                this.dmxData[baseAddr + channelMap.tilt] = Math.floor(tilt * 255);
                this.dmxData[baseAddr + channelMap.shutter] = 255; // Full open
            }
        }

        // Enhanced audio visualization
        this.audioData = {
            spectrum: Array.from({length: 32}, (_, i) => {
                const baseLevel = Math.sin(this.testPhase * 3 + i * 0.4) * 0.4 + 0.5;
                const beatBoost = onBeat && i < 8 ? 0.3 : 0;
                return Math.floor((baseLevel + beatBoost) * 200);
            }),
            rms: Math.sin(this.testPhase * 2) * 0.25 + 0.55 + (onBeat ? 0.15 : 0)
        };
    }

    hsvToRgb(h, s, v) {
        const c = v * s;
        const x = c * (1 - Math.abs((h / 60) % 2 - 1));
        const m = v - c;
        let r, g, b;

        if (h < 60) { r = c; g = x; b = 0; }
        else if (h < 120) { r = x; g = c; b = 0; }
        else if (h < 180) { r = 0; g = c; b = x; }
        else if (h < 240) { r = 0; g = x; b = c; }
        else if (h < 300) { r = x; g = 0; b = c; }
        else { r = c; g = 0; b = x; }

        return { r: r + m, g: g + m, b: b + m };
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.updateConnectionStatus(true);
            this.wsReconnectDelay = 1000; // BUG-029 fix: reset backoff on successful connection
            if (this.wsReconnectTimer) {
                clearTimeout(this.wsReconnectTimer);
                this.wsReconnectTimer = null;
            }
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'dmx' && msg.data && !this.testMode) {
                    this.dmxData = msg.data;
                }
                if (msg.type === 'audio' && msg.data) {
                    this.audioData = msg.data;
                    console.log('Audio received, RMS:', msg.data.rms?.toFixed(3));
                }
            } catch (e) {
                console.error('WebSocket parse error:', e);
            }
        };

        this.ws.onclose = () => {
            this.updateConnectionStatus(false);
            // BUG-029 fix: exponential backoff (1s, 2s, 4s, 8s, max 30s)
            this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), this.wsReconnectDelay);
            this.wsReconnectDelay = Math.min(this.wsReconnectDelay * 2, 30000);
        };

        this.ws.onerror = () => {};
    }

    updateConnectionStatus(connected) {
        const el = document.getElementById('connection-status');
        el.textContent = connected ? 'Connected' : 'Disconnected';
        el.className = connected ? 'connected' : 'disconnected';
    }

    setupUI() {
        document.getElementById('btn-reset-camera').addEventListener('click', () => {
            this.camera.position.set(0, 8, 15);
            this.camera.lookAt(0, 2, 0);
            this.controls.target.set(0, 2, 0);
        });

        document.getElementById('btn-toggle-grid').addEventListener('click', () => {
            this.showGrid = !this.showGrid;
            this.grid.visible = this.showGrid;
        });

        document.getElementById('btn-toggle-labels').addEventListener('click', () => {
            this.showLabels = !this.showLabels;
        });

        document.getElementById('chk-test-mode').addEventListener('change', (e) => {
            this.testMode = e.target.checked;
            if (!this.testMode) {
                this.dmxData = new Array(512).fill(0);
                this.audioData = null;
            }
        });
    }

    onResize() {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
    }

    // BUG-028 fix: proper Three.js resource disposal
    dispose() {
        if (this.ws) {
            this.ws.close();
        }
        if (this.wsReconnectTimer) {
            clearTimeout(this.wsReconnectTimer);
        }
        this.scene.traverse((object) => {
            if (object.geometry) object.geometry.dispose();
            if (object.material) {
                if (object.material.map) object.material.map.dispose();
                object.material.dispose();
            }
        });
        this.renderer.dispose();
        this.controls.dispose();
    }

    animate() {
        requestAnimationFrame(() => this.animate());

        // FPS counter
        this.frameCount++;
        const now = performance.now();
        if (now - this.lastFpsUpdate > 1000) {
            document.getElementById('fps').textContent = `${this.frameCount} FPS`;
            this.frameCount = 0;
            this.lastFpsUpdate = now;
        }

        // Test mode
        this.runTestMode();

        // Update fixtures
        this.updateFixtures();

        // Update audio monitor
        this.updateAudioMonitor();

        // Update controls
        this.controls.update();

        // Render
        this.renderer.render(this.scene, this.camera);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.visualizer = new ILSVisualizer();
});
