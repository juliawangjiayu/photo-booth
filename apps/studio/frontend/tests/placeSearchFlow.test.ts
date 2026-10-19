import assert from 'node:assert/strict';
import test from 'node:test';
import {searchWithFallback} from '../src/placeSearchFlow.ts';
import type {AiPlaceInterpretation, Place} from '../src/types.ts';

const directPlace: Place = {
  id: 'direct', name: 'Yushan', formattedAddress: 'Fuzhou, Fujian, China',
  latitude: 26.075, longitude: 119.304, country: 'China', region: 'Fujian', city: 'Fuzhou', district: '',
};
const rewrittenPlace: Place = {...directPlace, id: 'rewritten', name: 'Yushan Scenic Area'};
const resolved: AiPlaceInterpretation = {
  status: 'resolved', normalized_query: 'Yushan Scenic Area, Fuzhou, Fujian', landmark: 'Yushan Scenic Area',
  locality: 'Fuzhou', region: 'Fujian', country: 'China', category: 'tourist attraction', uncertainty: '',
  confidence: 0.9, clarification: '',
};

test('direct candidates return without calling the model', async () => {
  let modelCalls = 0;
  const outcome = await searchWithFallback('于山 福州市', async query => query === '于山 福州市' ? [directPlace] : [], async () => {modelCalls += 1; return resolved;}, 'automatic');
  assert.deepEqual(outcome.places, [directPlace]);
  assert.equal(outcome.source, 'direct');
  assert.equal(outcome.modelAttempted, false);
  assert.equal(modelCalls, 0);
});

test('zero direct results trigger exactly one interpretation and one rewritten retry', async () => {
  const searched: string[] = [];
  let modelCalls = 0;
  const outcome = await searchWithFallback('比较老城区，可能是晋江', async query => {searched.push(query); return query === resolved.normalized_query ? [rewrittenPlace] : [];}, async () => {modelCalls += 1; return resolved;}, 'automatic');
  assert.deepEqual(searched, ['比较老城区，可能是晋江', resolved.normalized_query]);
  assert.equal(modelCalls, 1);
  assert.equal(outcome.source, 'interpreted');
  assert.deepEqual(outcome.places, [rewrittenPlace]);
});

test('forced mode reinterprets instead of accepting existing direct candidates', async () => {
  const searched: string[] = [];
  let modelCalls = 0;
  const outcome = await searchWithFallback('于山 福州市', async query => {searched.push(query); return query === resolved.normalized_query ? [rewrittenPlace] : [directPlace];}, async () => {modelCalls += 1; return resolved;}, 'forced');
  assert.deepEqual(searched, [resolved.normalized_query]);
  assert.equal(modelCalls, 1);
  assert.deepEqual(outcome.places, [rewrittenPlace]);
});

test('insufficient interpretation does not send a rewritten Places request', async () => {
  const searched: string[] = [];
  const insufficient: AiPlaceInterpretation = {...resolved, status: 'insufficient', normalized_query: '', clarification: 'Add a city or region.'};
  const outcome = await searchWithFallback('海边', async query => {searched.push(query); return [];}, async () => insufficient, 'automatic');
  assert.deepEqual(searched, ['海边']);
  assert.equal(outcome.source, 'insufficient');
  assert.equal(outcome.clarification, 'Add a city or region.');
});

test('model failure remains recoverable and preserves direct/manual search options', async () => {
  const outcome = await searchWithFallback('海边', async () => [], async () => {throw new Error('DeepSeek timed out');}, 'automatic');
  assert.deepEqual(outcome.places, []);
  assert.equal(outcome.source, 'direct');
  assert.equal(outcome.modelError, 'DeepSeek timed out');
});

test('an empty rewritten search does not recursively reinterpret or retry', async () => {
  let placeCalls = 0;
  let modelCalls = 0;
  const outcome = await searchWithFallback('unknown landmark', async () => {placeCalls += 1; return [];}, async () => {modelCalls += 1; return resolved;}, 'automatic');
  assert.equal(placeCalls, 2);
  assert.equal(modelCalls, 1);
  assert.equal(outcome.source, 'interpreted');
  assert.deepEqual(outcome.places, []);
});
