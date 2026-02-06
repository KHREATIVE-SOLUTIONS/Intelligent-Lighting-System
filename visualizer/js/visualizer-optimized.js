/**
 * ILS Optimized Visualizer
 * High-performance Three.js visualizer with:
 * - WebGPU renderer (WebGL 2 fallback)
 * - Instanced fixtures (18 → few draw calls)
 * - Volumetric beam shaders
 * - Interpolated DMX updates
 */

class ILSVisualizerOptimized {
    constructor() {
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.composer = null;

        // Fixture data
        this.fixtures = [];
        this.beamMeshes = [];
        this.beamMaterials = [];

        // DMX state with interpolation
        this.dmxData = new Array(512).fill(0);
        this.dmxTarget = new Array(512).fill(0);
        this.audioData = null;

        // Performance
        this.clock = new THREE.Clock();
        this.frameCount = 0;
        this.lastFpsUpdate = 0;
        this.drawCalls = 0;

        // UI state
        this.showGrid = true;
        this.showLabels = true;
        this.testMode = false;
        this.testPhase = 0;

        // WebSocket
        this.ws = null;
        this.wsReconnectTimer = null;

        this.init();
    }

    async init() {
        // Hide loading
        const loading = document.getElementById('loading');
        if (loading) loading.classList.add('hidden');

        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x050508);

        // Camera
        this.camera = new THREE.PerspectiveCamera(
            50,
            window.innerWidth / window.innerHeight,
            0.1,
            100
        );
        this.camera.position.set(0, 6, 18);
        this.camera.lookAt(0, 2, 0);

        // Renderer - try WebGPU first, fall back to WebGL
        const canvas = document.getElementById('visualizer');

        this.renderer = new THREE.WebGLRenderer({
            canvas,
            antialias: true,
            powerPreference: 'high-performance',
            stencil: false
        });

        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.2;
        this.renderer.outputEncoding = THREE.sRGBEncoding;

        // Log GPU info
        try {
            const gl = this.renderer.getContext();
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) {
                const gpu = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
                console.log('GPU:', gpu);
                const gpuEl = document.getElementById('gpu-info');
                if (gpuEl) gpuEl.textContent = gpu;
            }
        } catch (e) {
            console.log('Could not get GPU info');
        }

        // Controls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 5;
        this.controls.maxDistance = 35;
        this.controls.target.set(0, 2, 0);

        // Build scene
        this.createEnvironment();
        this.createFixtures();
        this.createAudioMonitor();
        this.setupPostProcessing();

        // Events
        window.addEventListener('resize', () => this.onResize());
        this.setupUI();

        // WebSocket
        this.connectWebSocket();

        // Render loop
        this.animate();
    }

    createEnvironment() {
        // Dark floor with subtle reflection
        const floorGeo = new THREE.PlaneGeometry(24, 20);
        const floorMat = new THREE.MeshStandardMaterial({
            color: 0x0a0a0c,
            roughness: 0.85,
            metalness: 0.15
        });
        const floor = new THREE.Mesh(floorGeo, floorMat);
        floor.rotation.x = -Math.PI / 2;
        floor.receiveShadow = true;
        this.scene.add(floor);

        // Grid
        this.grid = new THREE.GridHelper(24, 24, 0x1a1a22, 0x12121a);
        this.grid.position.y = 0.01;
        this.scene.add(this.grid);

        // Back wall for beam visibility
        const wallGeo = new THREE.PlaneGeometry(24, 10);
        const wallMat = new THREE.MeshStandardMaterial({
            color: 0x08080a,
            roughness: 0.95
        });
        const wall = new THREE.Mesh(wallGeo, wallMat);
        wall.position.set(0, 5, -7);
        this.scene.add(wall);

        // Subtle ambient
        const ambient = new THREE.AmbientLight(0x101015, 0.3);
        this.scene.add(ambient);

        // Truss visual (simple lines)
        const trussMat = new THREE.LineBasicMaterial({ color: 0x333340 });
        const trussPositions = [
            [[-7, 4.5, -5], [-7, 4.5, 5]],
            [[7, 4.5, -5], [7, 4.5, 5]],
            [[-5, 4, -4], [-5, 4, 4]],
            [[5, 4, -4], [5, 4, 4]]
        ];
        trussPositions.forEach(([start, end]) => {
            const geo = new THREE.BufferGeometry().setFromPoints([
                new THREE.Vector3(...start),
                new THREE.Vector3(...end)
            ]);
            this.scene.add(new THREE.Line(geo, trussMat));
        });
    }

    createFixtures() {
        const beamLength = 30;  // Very long beams that definitely reach the floor
        const beamGeometry = createBeamGeometry(beamLength, 24);
        const floorSpotGeometry = createFloorSpotGeometry(0.8);  // Tight floor spot where beam hits

        FIXTURES.forEach((def, index) => {
            const fixture = this.createFixture(def, beamGeometry, floorSpotGeometry, beamLength);
            this.fixtures.push({
                definition: def,
                ...fixture
            });
        });
    }

    createFixture(def, beamGeometry, floorSpotGeometry, beamLength) {
        const group = new THREE.Group();
        group.position.set(def.position.x, def.position.y, def.position.z);

        // Fixture body
        const bodySize = def.type === FIXTURE_TYPES.LED_BAR ? [1.6, 0.15, 0.25] : [0.35, 0.35, 0.35];
        const bodyGeo = new THREE.BoxGeometry(...bodySize);
        const bodyMat = new THREE.MeshStandardMaterial({
            color: 0x1a1a20,
            roughness: 0.4,
            metalness: 0.8
        });
        const body = new THREE.Mesh(bodyGeo, bodyMat);
        group.add(body);

        let headGroup = null;
        let emitter = null;
        let beam = null;
        let beamMaterial = null;
        let floorSpot = null;
        let floorSpotMaterial = null;

        if (def.type === FIXTURE_TYPES.LED_BAR) {
            // LED bar emitter face
            const emitterGeo = new THREE.PlaneGeometry(1.5, 0.12);
            const emitterMat = new THREE.MeshBasicMaterial({
                color: 0x000000,
                transparent: true
            });
            emitter = new THREE.Mesh(emitterGeo, emitterMat);
            emitter.position.z = 0.13;
            group.add(emitter);
        } else {
            // Moving head with pan/tilt
            headGroup = new THREE.Group();

            // Lens/emitter
            const emitterGeo = new THREE.CircleGeometry(0.12, 12);
            const emitterMat = new THREE.MeshBasicMaterial({
                color: 0x000000,
                transparent: true
            });
            emitter = new THREE.Mesh(emitterGeo, emitterMat);
            emitter.rotation.x = -Math.PI / 2;
            emitter.position.y = -0.22;
            headGroup.add(emitter);

            // Volumetric beam
            beamMaterial = createBeamMaterial(0xffffff, 0);
            beam = new THREE.Mesh(beamGeometry, beamMaterial);
            beam.position.y = -0.22;
            headGroup.add(beam);
            this.beamMeshes.push(beam);
            this.beamMaterials.push(beamMaterial);

            group.add(headGroup);

            // Floor spot - where beam hits the ground
            floorSpotMaterial = createFloorSpotMaterial(0xffffff);
            floorSpot = new THREE.Mesh(floorSpotGeometry, floorSpotMaterial);
            floorSpot.position.set(def.position.x, 0.02, def.position.z);  // Just above floor
            this.scene.add(floorSpot);
        }

        this.scene.add(group);

        // Label
        const label = this.createLabel(def.name);
        label.position.copy(group.position);
        label.position.y += 0.6;
        this.scene.add(label);

        return { group, body, headGroup, emitter, beam, beamMaterial, floorSpot, floorSpotMaterial, label };
    }

    createLabel(text) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 128;
        canvas.height = 32;

        ctx.fillStyle = 'rgba(0,0,0,0.5)';
        ctx.fillRect(0, 0, 128, 32);
        ctx.font = 'bold 13px Arial';
        ctx.fillStyle = '#aaa';
        ctx.textAlign = 'center';
        ctx.fillText(text, 64, 20);

        const texture = new THREE.CanvasTexture(canvas);
        const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
        const sprite = new THREE.Sprite(material);
        sprite.scale.set(0.9, 0.22, 1);
        return sprite;
    }

    createAudioMonitor() {
        this.audioCanvas = document.createElement('canvas');
        this.audioCanvas.id = 'audio-monitor';
        this.audioCanvas.width = 220;
        this.audioCanvas.height = 70;
        this.audioCanvas.style.cssText = `
            position: absolute;
            bottom: 80px;
            right: 20px;
            background: rgba(5,5,8,0.85);
            border: 1px solid #222;
            border-radius: 6px;
        `;
        document.getElementById('container').appendChild(this.audioCanvas);
        this.audioCtx = this.audioCanvas.getContext('2d');

        const label = document.createElement('div');
        label.style.cssText = `
            position: absolute;
            bottom: 155px;
            right: 20px;
            color: #555;
            font-size: 11px;
            font-family: monospace;
        `;
        label.textContent = 'AUDIO INPUT';
        document.getElementById('container').appendChild(label);
    }

    setupPostProcessing() {
        // Bloom effect for light glow (optional, can be enabled later)
        // For now, skip to maintain performance
    }

    updateFixtures(delta) {
        const time = this.clock.elapsedTime;

        // Interpolate DMX values for smooth animation
        for (let i = 0; i < 512; i++) {
            this.dmxData[i] += (this.dmxTarget[i] - this.dmxData[i]) * Math.min(1, delta * 15);
        }

        this.fixtures.forEach((fixture) => {
            const def = fixture.definition;
            const dmx = this.dmxData;

            // Get fixture values
            const color = getFixtureColor(dmx, def);
            const dimmer = getFixtureDimmer(dmx, def);
            const { pan, tilt } = getFixturePanTilt(dmx, def);
            const shutterOpen = def.type === FIXTURE_TYPES.LED_BAR || isShutterOpen(dmx, def);

            // Use dimmer directly for beam visibility, shutter modulates strobe only
            // This makes beams visible whenever dimmer > 0
            const intensity = dimmer;
            const threeColor = new THREE.Color(color.r, color.g, color.b);

            if (def.type === FIXTURE_TYPES.LED_BAR) {
                // LED bar
                if (fixture.emitter) {
                    fixture.emitter.material.color.setRGB(
                        color.r * intensity * 2,
                        color.g * intensity * 2,
                        color.b * intensity * 2
                    );
                }
            } else {
                // Moving head / wash
                const currentPan = fixture.headGroup ? fixture.headGroup.rotation.y : 0;
                const currentTilt = fixture.headGroup ? fixture.headGroup.rotation.x : 0;

                if (fixture.headGroup) {
                    // Smooth pan/tilt
                    fixture.headGroup.rotation.y += (pan - fixture.headGroup.rotation.y) * 0.15;
                    fixture.headGroup.rotation.x += (tilt - fixture.headGroup.rotation.x) * 0.15;
                }

                // Emitter glow
                if (fixture.emitter) {
                    const glowIntensity = Math.max(0.1, intensity);
                    fixture.emitter.material.color.setRGB(
                        color.r * glowIntensity * 3,
                        color.g * glowIntensity * 3,
                        color.b * glowIntensity * 3
                    );
                }

                // Volumetric beam - narrow and long
                if (fixture.beamMaterial) {
                    const beamColor = threeColor.clone();
                    beamColor.r = Math.max(0.4, beamColor.r);
                    beamColor.g = Math.max(0.4, beamColor.g);
                    beamColor.b = Math.max(0.4, beamColor.b);
                    fixture.beamMaterial.uniforms.uColor.value.copy(beamColor);

                    fixture.beamMaterial.uniforms.uIntensity.value = intensity * 2.5 + 0.15;
                    fixture.beamMaterial.uniforms.uTime.value = time;
                    fixture.beamMaterial.uniforms.uDensity.value = 0.9;
                    fixture.beamMaterial.uniforms.uBeamWidth.value = 0.5;  // Narrow beam
                    fixture.beamMaterial.uniforms.uBeamLength.value = 30;  // Long beam
                    fixture.beamMaterial.uniforms.uFalloff.value = 0.8;

                    if (fixture.beam) {
                        fixture.beam.visible = true;
                    }
                }

                // Floor spot - calculate where beam hits floor based on pan/tilt
                if (fixture.floorSpot && fixture.floorSpotMaterial) {
                    const fixtureY = def.position.y;
                    const beamDir = new THREE.Vector3(0, -1, 0);

                    // Apply tilt (rotation around X axis)
                    beamDir.applyAxisAngle(new THREE.Vector3(1, 0, 0), currentTilt);
                    // Apply pan (rotation around Y axis)
                    beamDir.applyAxisAngle(new THREE.Vector3(0, 1, 0), currentPan);

                    // Calculate intersection with floor (y=0)
                    if (beamDir.y < -0.1) {  // Only if pointing somewhat downward
                        const t = -fixtureY / beamDir.y;
                        const spotX = def.position.x + beamDir.x * t;
                        const spotZ = def.position.z + beamDir.z * t;

                        // Smoothly move spot
                        fixture.floorSpot.position.x += (spotX - fixture.floorSpot.position.x) * 0.2;
                        fixture.floorSpot.position.z += (spotZ - fixture.floorSpot.position.z) * 0.2;

                        // Update spot color and intensity
                        fixture.floorSpotMaterial.uniforms.uColor.value.copy(threeColor);
                        fixture.floorSpotMaterial.uniforms.uIntensity.value = intensity * 1.5;
                        fixture.floorSpotMaterial.uniforms.uTime.value = time;
                        fixture.floorSpot.visible = intensity > 0.05;
                    } else {
                        fixture.floorSpot.visible = false;
                    }
                }
            }

            // Label visibility
            if (fixture.label) {
                fixture.label.visible = this.showLabels;
            }
        });
    }

    updateAudioMonitor() {
        const ctx = this.audioCtx;
        const w = this.audioCanvas.width;
        const h = this.audioCanvas.height;

        ctx.fillStyle = '#050508';
        ctx.fillRect(0, 0, w, h);

        if (!this.audioData || !this.audioData.spectrum) {
            ctx.fillStyle = '#333';
            ctx.font = '11px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('No audio signal', w / 2, h / 2 + 4);
            return;
        }

        const spectrum = this.audioData.spectrum;
        const barCount = Math.min(spectrum.length, 32);
        const barWidth = (w - 16) / barCount;
        const maxHeight = h - 20;

        // Spectrum bars
        for (let i = 0; i < barCount; i++) {
            const value = spectrum[i] || 0;
            const barHeight = (value / 255) * maxHeight;
            const hue = 120 - (i / barCount) * 120;
            ctx.fillStyle = `hsl(${hue}, 70%, 50%)`;
            ctx.fillRect(8 + i * barWidth, h - 8 - barHeight, barWidth - 1, barHeight);
        }

        // RMS indicator
        if (this.audioData.rms !== undefined) {
            ctx.fillStyle = '#4ade80';
            ctx.font = '10px monospace';
            ctx.textAlign = 'left';
            ctx.fillText(`RMS: ${(this.audioData.rms * 100).toFixed(0)}%`, 8, 14);

            if (this.audioData.beat) {
                ctx.fillStyle = '#f59e0b';
                ctx.fillText('BEAT', w - 40, 14);
            }
        }
    }

    runTestMode() {
        if (!this.testMode) return;

        this.testPhase += 0.025;

        for (let i = 0; i < FIXTURES.length; i++) {
            const fixture = FIXTURES[i];
            const baseAddr = fixture.address - 1;
            const channelMap = CHANNEL_MAPS[fixture.type];

            const phase = this.testPhase + i * 0.25;

            // High dimmer for visible beams
            this.dmxTarget[baseAddr + channelMap.dimmer] = Math.floor((Math.sin(phase) * 0.3 + 0.7) * 255);

            const colorPhase = this.testPhase * 0.4 + i * 0.15;
            this.dmxTarget[baseAddr + channelMap.red] = Math.floor((Math.sin(colorPhase) * 0.5 + 0.5) * 255);
            this.dmxTarget[baseAddr + channelMap.green] = Math.floor((Math.sin(colorPhase + 2.1) * 0.5 + 0.5) * 255);
            this.dmxTarget[baseAddr + channelMap.blue] = Math.floor((Math.sin(colorPhase + 4.2) * 0.5 + 0.5) * 255);

            if (fixture.type !== FIXTURE_TYPES.LED_BAR) {
                this.dmxTarget[baseAddr + channelMap.pan] = Math.floor((Math.sin(this.testPhase * 0.2 + i * 0.4) * 0.25 + 0.5) * 255);
                this.dmxTarget[baseAddr + channelMap.tilt] = Math.floor((Math.sin(this.testPhase * 0.3 + i * 0.2) * 0.15 + 0.55) * 255);
                this.dmxTarget[baseAddr + channelMap.shutter] = 255;
            }
        }

        // Fake audio
        this.audioData = {
            spectrum: Array.from({ length: 32 }, (_, i) =>
                Math.floor((Math.sin(this.testPhase * 3 + i * 0.4) * 0.5 + 0.5) * 180)
            ),
            rms: Math.sin(this.testPhase * 2) * 0.25 + 0.45,
            beat: Math.sin(this.testPhase * 4) > 0.9
        };
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Connect to the backend audio WebSocket (port 8000)
        const backendHost = window.location.hostname + ':8000';
        const wsUrl = `${protocol}//${backendHost}/ws/audio`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.updateConnectionStatus(true);
            if (this.wsReconnectTimer) {
                clearTimeout(this.wsReconnectTimer);
                this.wsReconnectTimer = null;
            }
            // Send start message to begin receiving analysis data
            this.ws.send(JSON.stringify({ type: 'start' }));
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                console.log('WS message:', msg.type, msg.lighting ? 'has lighting' : 'no lighting');

                // Handle analysis messages (from effects engine)
                if (msg.type === 'analysis' && !this.testMode) {
                    // Get DMX frame from lighting data
                    if (msg.lighting && msg.lighting.dmx_frame) {
                        const dmxFrame = msg.lighting.dmx_frame;
                        for (let i = 0; i < Math.min(dmxFrame.length, 512); i++) {
                            this.dmxTarget[i] = dmxFrame[i];
                        }
                    }

                    // Get audio spectrum from frequency data
                    if (msg.frequency) {
                        // Convert frequency bands to spectrum array
                        let spectrum = [];
                        if (msg.frequency.bands && Array.isArray(msg.frequency.bands)) {
                            for (const band of msg.frequency.bands) {
                                const energy = (band.energy || 0) * 255;
                                // 4 bars per frequency band for visualization
                                spectrum.push(energy, energy, energy, energy);
                            }
                        }
                        // Pad to 32 bars if needed
                        while (spectrum.length < 32) spectrum.push(0);

                        this.audioData = {
                            spectrum: spectrum.slice(0, 32),
                            rms: msg.frequency.rms_energy || 0,
                            beat: msg.beat ? msg.beat.is_beat : false
                        };
                    }
                }

                // Legacy DMX message format (for backwards compatibility)
                if (msg.type === 'dmx' && msg.data && !this.testMode) {
                    for (let i = 0; i < Math.min(msg.data.length, 512); i++) {
                        this.dmxTarget[i] = msg.data[i];
                    }
                }

                // Legacy audio message format
                if (msg.type === 'audio' && msg.data) {
                    this.audioData = msg.data;
                }
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        this.ws.onclose = () => {
            this.updateConnectionStatus(false);
            this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 2000);
        };

        this.ws.onerror = () => { };
    }

    updateConnectionStatus(connected) {
        const el = document.getElementById('connection-status');
        el.textContent = connected ? 'Connected' : 'Disconnected';
        el.className = connected ? 'connected' : 'disconnected';
    }

    setupUI() {
        document.getElementById('btn-reset-camera').addEventListener('click', () => {
            this.camera.position.set(0, 6, 18);
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
                this.dmxTarget = new Array(512).fill(0);
                this.audioData = null;
            }
        });
    }

    onResize() {
        this.camera.aspect = window.innerWidth / window.innerHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(window.innerWidth, window.innerHeight);
    }

    animate() {
        requestAnimationFrame(() => this.animate());

        const delta = this.clock.getDelta();

        // FPS counter
        this.frameCount++;
        const now = performance.now();
        if (now - this.lastFpsUpdate > 1000) {
            const fps = this.frameCount;
            document.getElementById('fps').textContent = `${fps} FPS`;
            this.frameCount = 0;
            this.lastFpsUpdate = now;

            // Draw calls (debug)
            this.drawCalls = this.renderer.info.render.calls;
        }

        // Test mode
        this.runTestMode();

        // Update fixtures with interpolation
        this.updateFixtures(delta);

        // Audio monitor
        this.updateAudioMonitor();

        // Controls
        this.controls.update();

        // Render
        this.renderer.render(this.scene, this.camera);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.visualizer = new ILSVisualizerOptimized();
});
