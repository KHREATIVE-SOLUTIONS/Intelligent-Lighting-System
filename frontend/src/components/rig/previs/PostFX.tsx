/**
 * Bloom for the 3D previz (docs/PREVIZ_LOOK.md): three's EffectComposer with
 * a RenderPass, an UnrealBloomPass and an OutputPass (tone mapping, exposure
 * and sRGB, from the renderer's own settings).
 *
 * Mounted only with Bloom on. Its frame callback has priority 1, which tells
 * react-three-fiber to stop rendering the scene itself, so the scene is drawn
 * once a frame, by the composer. Unmounted, r3f renders as before and bloom
 * costs nothing.
 *
 * Imported only by RigVisualizer, so the tests that import the rest of the
 * previz never load the post-processing modules.
 */
import { useEffect, useLayoutEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

/**
 * Low enough that the room is not washed out: only what is brighter than the
 * threshold before tone mapping blooms, which is the lenses (drawn at three
 * times their colour), beam cores where beams overlap, and the hottest pools.
 */
export const BLOOM_STRENGTH = 0.55;
export const BLOOM_RADIUS = 0.45;
export const BLOOM_THRESHOLD = 0.82;

export function BloomComposer({ samples }: { samples: number }) {
  const gl = useThree((state) => state.gl);
  const scene = useThree((state) => state.scene);
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const dpr = useThree((state) => state.viewport.dpr);

  const fx = useMemo(() => {
    // Half float so what is brighter than white survives to the bloom pass;
    // multisampled, since the canvas's own antialiasing does not apply to a render target.
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples });
    const composer = new EffectComposer(gl, target);
    const render = new RenderPass(scene, camera);
    const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), BLOOM_STRENGTH, BLOOM_RADIUS, BLOOM_THRESHOLD);
    const output = new OutputPass();
    composer.addPass(render);
    composer.addPass(bloom);
    composer.addPass(output);
    return { target, composer, render, bloom, output };
    // The camera is kept up to date below: a new camera must not rebuild the targets.
  }, [gl, scene, samples]);

  useEffect(() => () => {
    fx.bloom.dispose();
    fx.output.dispose();
    fx.composer.dispose();
    fx.target.dispose();
  }, [fx]);

  // Each camera button makes a new default camera.
  useLayoutEffect(() => {
    fx.render.camera = camera;
  }, [fx, camera]);

  // CSS size and pixel ratio, separately: the composer multiplies them itself.
  useLayoutEffect(() => {
    fx.composer.setPixelRatio(dpr);
    fx.composer.setSize(size.width, size.height);
  }, [fx, size.width, size.height, dpr]);

  useFrame((_, delta) => {
    fx.composer.render(delta);
  }, 1);

  return null;
}
