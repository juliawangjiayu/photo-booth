import type { Photo } from './types';

export function filterLibraryPhotos(photos: Photo[], filter: string): Photo[] {
  if (filter !== 'featured') return photos;
  return photos.filter(photo => photo.featured);
}
