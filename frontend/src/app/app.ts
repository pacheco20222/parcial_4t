import { ChangeDetectionStrategy, Component, DestroyRef, effect, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from './core/auth/auth.service';
import { PointsStore } from './core/state/points.store';
import { pointLabel } from './core/state/labels';
import { statusLabel } from './core/state/format';
@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  protected readonly announcement = signal('');
  constructor() {
    const auth = inject(AuthService);
    const points = inject(PointsStore);
    const destroyRef = inject(DestroyRef);
    auth.loadMe().pipe(takeUntilDestroyed(destroyRef)).subscribe({ error: () => this.announcement.set('No se pudo comprobar la sesión. Reintenta al iniciar sesión.') });
    const previous = new Map<string, string>();
    effect(() => {
      for (const point of points.points()) {
        const status = previous.get(point.id);
        if (status && status !== point.status) this.announcement.set(`${pointLabel(point)} pasó a ${statusLabel(point.status)}`);
        previous.set(point.id, point.status);
      }
    });
  }
}
