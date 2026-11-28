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
(router, editor store, 2D plan) for every test. Run alone, the four heaviest
(Items, RoomAdjust, RoomCarry, Walls) pass 45/45 in about 70-130 s. In a full
parallel run every worker thread is busy at once, and
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

The `RoomShell*Dialog*.test.tsx` and `RoomScan*Dialog*.test.tsx` files render
the full RoomShellEditDialog / RoomScanDialog and carry the same line: in a
later full run `RoomShellRaisedDialog.test.tsx` failed one test with `Test
timed out in 5000ms`.

A new test file that renders the full RigBuilder or one of those dialogs
should carry the same line.

## Testing Library wait timeout

With the test timeout raised, Testing Library's own 1000 ms default for
`findBy*` / `waitFor` was the next limit hit under load: the same run failed a
second `RoomShellRaisedDialog` test with `Unable to find an element with the
text ...`. `src/setupTests.ts` (listed in `test.setupFiles` in
`vite.config.ts`) raises it for every file:

```ts
configure({ asyncUtilTimeout: 5000 });
```

This only waits longer for an element to appear. A `findBy*` that would have
passed still passes as soon as the element shows up, and one whose element
never appears still fails, after 5 s.

## Worker cap

Vitest 1.x runs test files in worker threads, by default one per core.
`vite.config.ts` caps that at about half of a 16-thread machine:

```ts
poolOptions: { threads: { maxThreads: 8, minThreads: 1 } },
```

Fewer files run at once, so each gets more CPU. On a machine with fewer cores,
or to try a different cap for one run, pass `--poolOptions.threads.maxThreads=N`
on the command line.

## Finding slow tests

```
npx vitest run --reporter=verbose
```

lists every test with its time. To look at one file without the rest of the
suite competing for CPU:

```
npx vitest run src/__tests__/RigBuilderWalls.test.tsx --reporter=verbose
```

A failure from the Testing Library wait reads `Unable to find ...`; one from
the test timeout reads `Test timed out`.

If a file still times out in a full run, check first for avoidable slowness
(fake timers left running after a test, real `setTimeout` waits, rendering
more of the app than the test needs) before raising its timeout further.
