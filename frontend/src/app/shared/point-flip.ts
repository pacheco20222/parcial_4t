export interface PointRowSnapshot { rect: DOMRect; status: string; }

/** Animate only a changed point; geometry is measured by the panel after render. */
export function animatePointMove(row: HTMLElement, before: DOMRect, after: DOMRect): void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || typeof row.animate !== 'function') return;
  row.animate([
    { transform: `translate(${before.x - after.x}px, ${before.y - after.y}px)`, opacity: .55 },
    { transform: 'translate(0, 0)', opacity: 1 },
  ], { duration: 180, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' });
  // The existing overlay highlights the new rung without changing layout.
  row.querySelector<HTMLElement>('.point-highlight')?.animate(
    [{ opacity: .35 }, { opacity: 0 }],
    { duration: 180, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
  );
}
