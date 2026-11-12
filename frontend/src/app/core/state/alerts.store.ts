import { DestroyRef, Injectable, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Alert } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { LiveService } from '../live/live.service';
@Injectable({providedIn: 'root'})
export class AlertsStore {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);
  private fetchGeneration = 0;
  private readonly liveEvents = new Map<string, Alert>();
  readonly alerts = signal<Alert[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  constructor() {
    effect(() => { if (this.auth.me()) this.reload(); else this.alerts.set([]); });
    this.live.alert$.pipe(takeUntilDestroyed()).subscribe(event => {
      if (!this.auth.me()) return;
      this.liveEvents.set(event.id, event);
      this.alerts.update(items => event.status === 'Closed' ? items.filter(item => item.id !== event.id) : [event, ...items.filter(item => item.id !== event.id)].sort((a, b) => b.openedAt.localeCompare(a.openedAt)));
    });
    this.live.reconnected$.pipe(takeUntilDestroyed()).subscribe(() => this.reload());
  }
  reload(): void {
    if (!this.auth.me()) return;
    const userId = this.auth.me()?.id;
    const generation = ++this.fetchGeneration;
    this.liveEvents.clear();
    this.loading.set(true); this.error.set(null);
    this.http.get<Alert[]>('/api/ops/alerts?status=Open').pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: items => {
        if (generation !== this.fetchGeneration) return;
        if (this.auth.me()?.id === userId) {
          const merged = new Map(items.map(item => [item.id, item]));
          this.liveEvents.forEach((event, id) => merged.set(id, event));
          this.alerts.set([...merged.values()].filter(item => item.status === 'Open').sort((a, b) => b.openedAt.localeCompare(a.openedAt)));
        }
        this.loading.set(false);
      },
      error: () => { this.error.set('No pudimos cargar las alertas. Intenta de nuevo.'); this.loading.set(false); },
    });
  }
}
