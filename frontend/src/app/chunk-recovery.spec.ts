import { isChunkLoadError, recoverChunkNavigation } from './chunk-recovery';

describe('stale chunk recovery', () => {
  const failure = new TypeError('Failed to fetch dynamically imported module: /chunk-old.js');

  it.each([
    Object.assign(new Error('Loading chunk 42 failed.'), { name: 'ChunkLoadError' }),
    new TypeError('Failed to fetch dynamically imported module: /chunk-old.js'),
    new TypeError('error loading dynamically imported module: /chunk-old.js'),
    { name: 'ChunkLoadError', message: 'Loading chunk 42 failed.' },
  ])('recognizes dynamic import failure %s', (error) => {
    expect(isChunkLoadError(error)).toBe(true);
  });

  it.each([new Error('Access denied'), new TypeError('Failed to fetch'), null, undefined, 42, {}])(
    'leaves unrelated navigation errors alone: %s', (error) => {
      expect(isChunkLoadError(error)).toBe(false);
    },
  );

  it('reloads once to the target with query and fragment, including across new handler calls', () => {
    const storage = new Map<string, string>();
    const session = { getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => { storage.set(key, value); } };
    const reload = vi.fn();
    expect(recoverChunkNavigation(failure, '/ops/reports?status=New#reports', session, reload)).toBe(true);
    expect(reload).toHaveBeenCalledExactlyOnceWith('/ops/reports?status=New#reports');
    expect(recoverChunkNavigation(failure, '/ops/reports?status=New#reports', session, reload)).toBe(false);
    expect(recoverChunkNavigation(failure, '/ops/alerts', session, reload)).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('does not consume the reload attempt for an unrelated error', () => {
    const session = { getItem: vi.fn(), setItem: vi.fn() };
    const reload = vi.fn();
    expect(recoverChunkNavigation(new Error('Access denied'), '/ops', session, reload)).toBe(false);
    expect(session.setItem).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it.each(['getItem', 'setItem'] as const)('avoids loops when storage %s throws', (method) => {
    const session = { getItem: vi.fn().mockReturnValue(null), setItem: vi.fn() };
    session[method].mockImplementation(() => { throw new Error('Storage blocked'); });
    const reload = vi.fn();
    expect(recoverChunkNavigation(failure, '/ops', session, reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  it.each(['https://example.com', '//example.com', '/\\example.com', '/\n/example.com', 'ops/reports'])(
    'rejects nonlocal target %s', (target) => {
      const session = { getItem: vi.fn().mockReturnValue(null), setItem: vi.fn() };
      const reload = vi.fn();
      expect(recoverChunkNavigation(failure, target, session, reload)).toBe(false);
      expect(reload).not.toHaveBeenCalled();
    },
  );
});
