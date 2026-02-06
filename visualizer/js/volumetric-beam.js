/**
 * Volumetric Beam Shader Material
 * Raymarched volumetric cone for realistic light beams
 */

const VolumetricBeamShader = {
    uniforms: {
        uColor: { value: new THREE.Color(1, 1, 1) },
        uIntensity: { value: 1.0 },
        uBeamLength: { value: 30.0 },
        uBeamWidth: { value: 0.5 },
        uFalloff: { value: 0.8 },
        uDensity: { value: 0.9 },
        uTime: { value: 0 }
    },

    vertexShader: `
        varying vec3 vWorldPosition;
        varying vec3 vLocalPosition;
        varying vec2 vUv;

        void main() {
            vUv = uv;
            vLocalPosition = position;
            vec4 worldPos = modelMatrix * vec4(position, 1.0);
            vWorldPosition = worldPos.xyz;
            gl_Position = projectionMatrix * viewMatrix * worldPos;
        }
    `,

    fragmentShader: `
        uniform vec3 uColor;
        uniform float uIntensity;
        uniform float uBeamLength;
        uniform float uBeamWidth;
        uniform float uFalloff;
        uniform float uDensity;
        uniform float uTime;

        varying vec3 vWorldPosition;
        varying vec3 vLocalPosition;
        varying vec2 vUv;

        void main() {
            // Distance from center axis
            float distFromAxis = length(vLocalPosition.xz);

            // Progress along beam (0 = source, 1 = end)
            float progress = clamp(-vLocalPosition.y / uBeamLength, 0.0, 1.0);

            // Narrow beam - slight spread over distance (realistic)
            float coneRadius = uBeamWidth * (0.15 + progress * 0.85);

            // Sharp edge falloff for tight beam
            float edgeFalloff = 1.0 - smoothstep(coneRadius * 0.7, coneRadius, distFromAxis);

            // Minimal distance falloff - beam stays bright all the way down
            float distanceFalloff = 1.0 - pow(progress, uFalloff) * 0.4;

            // Bright center core
            float coreIntensity = 1.0 - smoothstep(0.0, coneRadius * 0.5, distFromAxis);

            // Combine effects - strong beam throughout
            float alpha = (edgeFalloff * distanceFalloff + coreIntensity * 0.5) * uDensity * uIntensity;

            // Subtle dust particle noise
            float noise = 0.9 + 0.1 * sin(vLocalPosition.y * 3.0 + uTime * 2.0);
            alpha *= noise;

            // Keep beam visible
            alpha = min(alpha * 1.8, 1.0);

            // Hot white core blending to color
            vec3 coreColor = mix(uColor, vec3(1.0), coreIntensity * 0.7);
            vec3 finalColor = coreColor * alpha;

            gl_FragColor = vec4(finalColor, alpha * 0.9);
        }
    `
};

/**
 * Create volumetric beam material
 */
function createBeamMaterial(color = 0xffffff, intensity = 1.0) {
    return new THREE.ShaderMaterial({
        uniforms: {
            uColor: { value: new THREE.Color(color) },
            uIntensity: { value: intensity },
            uBeamLength: { value: 30.0 },
            uBeamWidth: { value: 0.5 },
            uFalloff: { value: 0.8 },
            uDensity: { value: 0.9 },
            uTime: { value: 0 }
        },
        vertexShader: VolumetricBeamShader.vertexShader,
        fragmentShader: VolumetricBeamShader.fragmentShader,
        transparent: true,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        depthWrite: false
    });
}

/**
 * Create beam cone geometry - pointing down (-Y direction)
 */
function createBeamGeometry(length = 30, segments = 24) {
    // Narrow cone (0.6 radius) for tight beam, very long to reach floor
    const geometry = new THREE.ConeGeometry(0.6, length, segments, 1, true);
    // Position so tip is at origin, cone extends downward
    geometry.translate(0, -length / 2, 0);
    return geometry;
}

/**
 * Create floor spot geometry - circle on the ground where beam hits
 */
function createFloorSpotGeometry(radius = 0.8) {
    const geometry = new THREE.CircleGeometry(radius, 32);
    geometry.rotateX(-Math.PI / 2);  // Lay flat on floor
    return geometry;
}

/**
 * Create floor spot material - bright spot where beam hits the floor
 */
function createFloorSpotMaterial(color = 0xffffff) {
    return new THREE.ShaderMaterial({
        uniforms: {
            uColor: { value: new THREE.Color(color) },
            uIntensity: { value: 0.0 },
            uTime: { value: 0 }
        },
        vertexShader: `
            varying vec2 vUv;
            void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            uniform vec3 uColor;
            uniform float uIntensity;
            uniform float uTime;
            varying vec2 vUv;

            void main() {
                // Distance from center
                vec2 center = vUv - 0.5;
                float dist = length(center) * 2.0;

                // Tight bright core with soft outer glow
                float core = 1.0 - smoothstep(0.0, 0.4, dist);
                float glow = 1.0 - smoothstep(0.2, 1.0, dist);

                // Combine for bright center, soft edge
                float alpha = (core * 0.8 + glow * 0.4) * uIntensity;

                // Hot white center blending to color
                vec3 finalColor = mix(uColor, vec3(1.0), core * 0.7);
                finalColor *= alpha * 2.0;  // Boost brightness

                gl_FragColor = vec4(finalColor, min(alpha * 1.2, 1.0));
            }
        `,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });
}
