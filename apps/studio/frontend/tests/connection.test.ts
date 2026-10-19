import assert from 'node:assert/strict';
import test from 'node:test';
import { startConnectionMonitor } from '../src/connection.ts';

test('retries quietly after an initial backend connection race', async () => {
  const calls: boolean[] = [];
  let scheduled: (() => void) | undefined;
  let cleared = false;
  const clock = {
    setInterval(callback: () => void, delay: number) {
      assert.equal(delay, 5000);
      scheduled = callback;
      return 7;
    },
    clearInterval(timer: number) {
      assert.equal(timer, 7);
      cleared = true;
    },
  };
  const stop = startConnectionMonitor(async quiet => { calls.push(quiet); }, 5000, clock);
  await Promise.resolve();
  assert.deepEqual(calls, [false]);
  assert.ok(scheduled);
  scheduled();
  await Promise.resolve();
  assert.deepEqual(calls, [false, true]);
  stop();
  assert.equal(cleared, true);
});
