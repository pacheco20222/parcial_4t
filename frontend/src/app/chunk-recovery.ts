import { DOCUMENT } from '@angular/common';
import { inject } from '@angular/core';
import { NavigationError } from '@angular/router';

const RELOAD_GUARD = 'flood.chunk-reload-attempted';

export function isChunkLoadError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false;
  if ('name' in error && error.name === 'ChunkLoadError') return true;
  return 'message' in error && typeof error.message === 'string' &&
    /Failed to fetch dynamically imported module|error loading dynamically imported module/i.test(error.message);
}

export function recoverChunkNavigation(
  error: unknown,
  target: string,
  storage: Pick<Storage, 'getItem' | 'setItem'>,
  reload: (url: string) => void,
): boolean {
  if (!isChunkLoadError(error) || !target.startsWith('/')) return false;
  try {
    // Parse as the browser will: backslashes and control characters can disguise remote URLs.
    if (new URL(target, 'https://flood.invalid').origin !== 'https://flood.invalid') return false;
    if (storage.getItem(RELOAD_GUARD) !== null) return false;
    // Persist before leaving the page; a second chunk failure must not create a reload loop.
    storage.setItem(RELOAD_GUARD, '1');
  } catch {
    // Without a persistent guard, reloading could loop when storage is disabled.
    return false;
  }
  reload(target);
  return true;
}

export function handleChunkNavigationError(event: NavigationError): void {
  const browser = inject(DOCUMENT).defaultView;
  if (!browser || !isChunkLoadError(event.error)) return;
  let storage: Storage;
  try {
    storage = browser.sessionStorage;
  } catch {
    // Accessing sessionStorage itself can throw when browser storage is blocked.
    return;
  }
  recoverChunkNavigation(event.error, event.url, storage,
    (target) => browser.location.assign(target));
}
