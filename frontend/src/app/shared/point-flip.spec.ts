import { animatePointMove } from './point-flip';

describe('point FLIP motion', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('keeps status changes instant under reduced motion', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
    const row = document.createElement('a');
    row.animate = vi.fn();
    animatePointMove(row, new DOMRect(10, 20, 200, 44), new DOMRect(10, 300, 200, 44));
    expect(row.animate).not.toHaveBeenCalled();
  });

  it('inverts the old position and briefly highlights with opacity', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
    const row = document.createElement('a');
    row.innerHTML = '<span class="point-highlight"></span>';
    const highlight = row.firstElementChild as HTMLElement;
    row.animate = vi.fn();
    highlight.animate = vi.fn();
    animatePointMove(row, new DOMRect(10, 20, 200, 44), new DOMRect(15, 300, 200, 44));
    expect(row.animate).toHaveBeenCalledWith([
      { transform: 'translate(-5px, -280px)', opacity: .55 },
      { transform: 'translate(0, 0)', opacity: 1 },
    ], { duration: 180, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' });
    expect(highlight.animate).toHaveBeenCalledWith([{ opacity: .35 }, { opacity: 0 }],
      { duration: 180, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' });
  });
});
