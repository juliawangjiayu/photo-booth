import assert from 'node:assert/strict';
import test from 'node:test';
import {
  addTag,
  advanceReviewProgress,
  canStartImport,
  completionLabel,
  normalizeReviewQueue,
  reconcileReviewProgress,
  reviewQueueFrom,
  reviewProblems,
  supportedPhotoFiles,
  type ReviewDraft,
} from '../src/reviewWorkflow.ts';
import type { Photo } from '../src/types.ts';
import * as workflow from '../src/reviewWorkflow.ts';

const draft = (overrides: Partial<ReviewDraft> = {}): ReviewDraft => ({
  taken_at: '2025-03',
  device: 'Sony a6400',
  collectionIds: ['c_1'],
  featured: false,
  guess_enabled: false,
  guess: null,
  ...overrides,
});

test('import starts only with a collection and supported files', () => {
  assert.equal(canStartImport('', 3), false);
  assert.equal(canStartImport('c_1', 0), false);
  assert.equal(canStartImport('c_1', 3), true);
});

test('review requires a month, managed device, and collection', () => {
  assert.deepEqual(reviewProblems(draft()), []);
  assert.ok(reviewProblems(draft({taken_at: '2025'})).includes('Date must include a month'));
  assert.ok(reviewProblems(draft({device: ''})).includes('Choose a camera/device'));
  assert.ok(reviewProblems(draft({collectionIds: []})).includes('Choose a Collection'));
});

test('checked Guess Where requires a confirmed named answer', () => {
  const problems = reviewProblems(draft({guess_enabled: true, guess: null}));
  assert.ok(problems.includes('Confirm the Guess Where answer Pin'));
});

test('queue drops duplicates, missing photos, and photos no longer in draft', () => {
  const photos = [
    {id: 'draft', status: 'draft'},
    {id: 'done', status: 'modified'},
  ] as Photo[];
  assert.deepEqual(
    normalizeReviewQueue(['draft', 'missing', 'done', 'draft'], photos),
    ['draft'],
  );
});

test('import keeps only supported photo filenames in selection order', () => {
  const files = [
    {name: 'a.JPG'}, {name: 'notes.txt'}, {name: 'b.HEIC'}, {name: 'c.tiff'},
  ] as File[];
  assert.deepEqual(
    supportedPhotoFiles(files).map(file => file.name),
    ['a.JPG', 'b.HEIC', 'c.tiff'],
  );
});

test('adding a tag trims input and reuses a case-insensitive existing value', () => {
  assert.deepEqual(addTag(['Street'], [], ' street '), {
    options: ['Street'], selected: ['Street'],
  });
  assert.deepEqual(addTag(['Street'], [], 'Night'), {
    options: ['Street', 'Night'], selected: ['Night'],
  });
});

test('completion button labels distinguish next, exit, and final photo', () => {
  assert.equal(completionLabel('next', 0, 3), 'Save and next');
  assert.equal(completionLabel('exit', 0, 3), 'Save and exit');
  assert.equal(completionLabel('next', 2, 3), 'Save and finish');
});

test('Needs Review can resume from a clicked draft in visible order', () => {
  const photos = [
    {id: 'first', status: 'draft'},
    {id: 'done', status: 'modified'},
    {id: 'last', status: 'draft'},
  ] as Photo[];
  assert.deepEqual(reviewQueueFrom(['first', 'done', 'last'], photos), ['first', 'last']);
  assert.deepEqual(reviewQueueFrom(['first', 'done', 'last'], photos, 'last'), ['last']);
});

test('refresh skips a queued photo that is no longer draft without losing progress', () => {
  const photos = [
    {id: 'current', status: 'modified'},
    {id: 'next', status: 'draft'},
  ] as Photo[];
  assert.deepEqual(
    reconcileReviewProgress(['completed', 'current', 'missing', 'next'], 1, photos),
    {ids: ['completed', 'next'], index: 1},
  );
});

test('saving advances exactly once and finishes cleanly on the final photo', () => {
  const photos = [
    {id: 'first', status: 'modified'},
    {id: 'second', status: 'draft'},
  ] as Photo[];
  assert.deepEqual(
    advanceReviewProgress(['first', 'second'], 0, photos),
    {ids: ['first', 'second'], index: 1, nextId: 'second'},
  );
  assert.deepEqual(
    advanceReviewProgress(['first'], 0, [{id: 'first', status: 'modified'}] as Photo[]),
    {ids: [], index: 0, nextId: null},
  );
});

test('Guess Where radius is limited to the four supported choices', () => {
  const normalize = (workflow as typeof workflow & {
    normalizeAnswerRadius?: (value: number) => number;
  }).normalizeAnswerRadius;
  assert.equal(typeof normalize, 'function');
  assert.deepEqual(workflow.ANSWER_RADIUS_OPTIONS, [1, 10, 50, 100]);
  assert.equal(normalize?.(1), 1);
  assert.equal(normalize?.(10), 10);
  assert.equal(normalize?.(50), 50);
  assert.equal(normalize?.(100), 100);
  assert.equal(normalize?.(40), 10);
});

test('map coordinates must be finite and inside latitude/longitude bounds', () => {
  const valid = (workflow as typeof workflow & {
    validCoordinates?: (latitude: number, longitude: number) => boolean;
  }).validCoordinates;
  assert.equal(typeof valid, 'function');
  assert.equal(valid?.(22.2778, 114.1592), true);
  assert.equal(valid?.(-90, -180), true);
  assert.equal(valid?.(90, 180), true);
  assert.equal(valid?.(90.0001, 0), false);
  assert.equal(valid?.(0, 180.0001), false);
  assert.equal(valid?.(Number.NaN, 0), false);
  assert.equal(valid?.(0, Number.POSITIVE_INFINITY), false);
});
