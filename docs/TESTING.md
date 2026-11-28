# Testing the frontend

## Running the full suite

```
cd frontend
npx vitest run
```

One file, or a few, by name:

```
npx vitest run src/__tests__/RigBuilderItems.test.tsx
npx vitest run RigBuilder
```

## Why some files have a longer timeout

The `src/__tests__/RigBuilder*.test.tsx` files render the whole RigBuilder
(router, editor store, 2D plan) for every test. Run alone, each test takes
about 1-3 s. In a full parallel run every worker thread is busy at once, and
on a loaded machine (measured on a 16-thread Windows PC, Nov 2026) 3 to 13 of
them went past vitest's 5 s default and failed with `Test timed out in
5000ms`, while the same files passed 45/45 alone.

So each of those files raises its own per-test timeout at the top:

```ts
vi.setConfig({ testTimeout: 30_000 });
```

That only gives a slow machine more time. No assertion is loosened, and a
test that hangs still fails, after 30 s rather than 5 s. The global default
in `vite.config.ts` is unchanged, so a new light test file that hangs still
fails fast.

A new test file that renders the full RigBuilder should carry the same line.

## Finding slow tests

```
npx vitest run --reporter=verbose
```

lists every test with its time. To look at one file without the rest of the
suite competing for CPU:

```
npx vitest run src/__tests__/RigBuilderWalls.test.tsx --reporter=verbose
```

If a file still times out in a full run, check first for avoidable slowness
(fake timers left running after a test, real `setTimeout` waits, rendering
more of the app than the test needs) before raising its timeout further.
