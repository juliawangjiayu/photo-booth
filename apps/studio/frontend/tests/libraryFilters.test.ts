import assert from 'node:assert/strict';
import test from 'node:test';
import type { Photo } from '../src/types.ts';

const filters = await import('../src/libraryFilters.ts').catch(() => ({}));

test('Featured on homepage filter keeps only photos selected for the homepage', () => {
  const filterLibraryPhotos = (filters as {
    filterLibraryPhotos?: (photos: Photo[], filter: string) => Photo[];
  }).filterLibraryPhotos;

  assert.equal(typeof filterLibraryPhotos, 'function');
  if (!filterLibraryPhotos) return;

  const photos = [
    {id: 'featured', featured: true},
    {id: 'ordinary', featured: false},
  ] as Photo[];

  assert.deepEqual(
    filterLibraryPhotos(photos, 'featured').map(photo => photo.id),
    ['featured'],
  );
});
