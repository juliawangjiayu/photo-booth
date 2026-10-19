# Next.js public website placeholder

The **Photo Booth** local manager exports assets to any existing Next.js web folder that contains a `package.json`:

- `public/photos/<id>.webp`
- `public/photos/<id>-thumb.webp`
- `src/generated/photography.json`
- `src/generated/collections.json`

This folder is deliberately not a fake Next.js app. Create your real public site separately (e.g. `npx create-next-app@latest apps/web` at repo root), then point Photo Booth to that project folder.

**Guess Where answer coordinates are never exported.** Implement an authenticated admin-only D1 sync before publishing game answers.
