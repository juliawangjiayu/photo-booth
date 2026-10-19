import type {AnswerRadius, Device, Guess, Photo} from './types';

export const ANSWER_RADIUS_OPTIONS = [1, 10, 50, 100] as const;

export function normalizeAnswerRadius(value: number): AnswerRadius {
  return ANSWER_RADIUS_OPTIONS.includes(value as AnswerRadius) ? value as AnswerRadius : 10;
}

export function validCoordinates(latitude: number, longitude: number): boolean {
  return Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && latitude >= -90
    && latitude <= 90
    && longitude >= -180
    && longitude <= 180;
}

export type ReviewDraft = {
  taken_at: string;
  device: Device;
  collectionIds: string[];
  featured: boolean;
  guess_enabled: boolean;
  guess: Omit<Guess, 'photo_id'> | null;
};

const validDate = (value: string) => {
  if (/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return true;
  if (!/^\d{4}-(0[1-9]|1[0-2])-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};

export function canStartImport(collectionId: string, fileCount: number) {
  return Boolean(collectionId) && fileCount > 0;
}

export function reviewProblems(draft: ReviewDraft): string[] {
  const problems: string[] = [];
  if (!validDate(draft.taken_at)) problems.push('Date must include a month');
  if (!draft.device) problems.push('Choose a camera/device');
  if (!draft.collectionIds.length) problems.push('Choose a Collection');
  if (draft.guess_enabled && (!draft.guess?.confirmed || !draft.guess.answer_name.trim())) {
    problems.push('Confirm the Guess Where answer Pin');
  }
  return problems;
}

export function normalizeReviewQueue(ids: string[], photos: Photo[]): string[] {
  const status = new Map(photos.map(photo => [photo.id, photo.status]));
  return [...new Set(ids)].filter(id => status.get(id) === 'draft');
}

export function reviewQueueFrom(ids: string[], photos: Photo[], startId?: string): string[] {
  const queue = normalizeReviewQueue(ids, photos);
  if (!startId) return queue;
  const start = queue.indexOf(startId);
  return start >= 0 ? queue.slice(start) : queue;
}

export function reconcileReviewProgress(ids: string[], index: number, photos: Photo[]) {
  const completed = ids.slice(0, index);
  const remaining = normalizeReviewQueue(ids.slice(index), photos);
  return {ids: [...completed, ...remaining], index: completed.length};
}

export function advanceReviewProgress(ids: string[], index: number, photos: Photo[]) {
  const completed = ids.slice(0, index + 1);
  const remaining = normalizeReviewQueue(ids.slice(index + 1), photos);
  if (!remaining.length) return {ids: [], index: 0, nextId: null};
  return {
    ids: [...completed, ...remaining],
    index: completed.length,
    nextId: remaining[0],
  };
}

export function supportedPhotoFiles<T extends {name: string}>(files: T[]): T[] {
  return files.filter(file => /\.(jpe?g|png|webp|tiff?|heic|heif)$/i.test(file.name));
}

export function addTag(options: string[], selected: string[], raw: string) {
  const value = raw.trim();
  if (!value) return {options, selected};
  const existing = options.find(option => option.toLocaleLowerCase() === value.toLocaleLowerCase());
  const tag = existing ?? value;
  const alreadySelected = selected.some(item => item.toLocaleLowerCase() === tag.toLocaleLowerCase());
  return {
    options: existing ? options : [...options, value],
    selected: alreadySelected ? selected : [...selected, tag],
  };
}

export function completionLabel(
  action: 'next'|'exit', index: number, total: number,
) {
  if (action === 'exit') return 'Save and exit';
  return index === total - 1 ? 'Save and finish' : 'Save and next';
}
