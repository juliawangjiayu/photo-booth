import type { ChangeEvent } from 'react';
import type { AboutPhotoSetting } from './types';
import './AboutPhotoSettings.css';

type AboutPhotoSettingsProps = {
  photo: AboutPhotoSetting | null;
  busy: boolean;
  onUpload: (file: File) => void;
};

export default function AboutPhotoSettings({ photo, busy, onUpload }: AboutPhotoSettingsProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (file) onUpload(file);
  };

  return (
    <section className="settings-page about-photo-settings">
      <div className="settings-card about-photo-card">
        <div className="about-photo-card__copy">
          <h2>About page portrait</h2>
          <p>This is a standalone image for your About page. It will not be added to Library, Collections, the homepage, or Guess Where.</p>
          <p className="small muted">The original stays in Photo Booth’s private local storage. It appears on the website only after you export the site.</p>
          <label className="outline-btn about-photo-upload">
            {busy ? 'Saving…' : photo?.available ? 'Replace portrait' : 'Upload portrait'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,image/tiff,image/heic,.jpg,.jpeg,.png,.webp,.tif,.tiff,.heic,.heif"
              disabled={busy}
              onChange={handleChange}
            />
          </label>
        </div>
        <div className="about-photo-preview" aria-live="polite">
          {photo?.available ? (
            <>
              <img src={photo.url} alt="Current About page portrait" />
              <span>{photo.name}</span>
            </>
          ) : (
            <span>No standalone portrait uploaded</span>
          )}
        </div>
      </div>
    </section>
  );
}
