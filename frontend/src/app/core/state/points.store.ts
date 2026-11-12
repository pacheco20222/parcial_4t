import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { merge } from 'rxjs';
import { PointStatus, PointStatusEvent, PublicPoint } from '../api/models';
import { LiveService } from '../live/live.service';
import { STATUS_ORDER, pointAge } from './format';
@Injectable({ providedIn: 'root' })
export class PointsStore {
  private readonly http = inject(HttpClient);
  private readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);
  readonly points = signal<PublicPoint[]>([]);
  readonly now = signal(Date.now());
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly counts = computed(() => {
    const counts: Record<PointStatus, number> = { Normal: 0, Watch: 0, Alert: 0, NoData: 0 };
    this.points().forEach(point => counts[point.status]++);
    return counts;
  });
  readonly worstStatus = computed<PointStatus>(() => STATUS_ORDER.find(status => this.counts()[status] > 0) ?? 'NoData');
  constructor() {
    const timer = setInterval(() => this.now.set(Date.now()), 1000);
    this.destroyRef.onDestroy(() => clearInterval(timer));
    merge(this.live.pointStatus$, this.live.reading$).pipe(takeUntilDestroyed()).subscribe(event => this.merge(event));
    this.live.reconnected$.pipe(takeUntilDestroyed()).subscribe(() => this.reload());
    this.live.start();
    this.reload();
  }
  age(point: PublicPoint): number | null { return pointAge(point, this.now()); }
  reload(): void {
    this.loading.set(true); this.error.set(null);
    this.http.get<PublicPoint[]>('/api/telemetry/public/points').pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: points => {
        // A live event received during the fetch must not be overwritten by an older snapshot.
        const current = new Map(this.points().map(point => [point.id, point]));
        this.points.set(points.map(point => {
          const live = current.get(point.id);
          return live?.updatedAt && (!point.updatedAt || Date.parse(live.updatedAt) > Date.parse(point.updatedAt))
            ? { ...point, status: live.status, waterDepthCm: live.waterDepthCm, updatedAt: live.updatedAt, lastUpdateAgeSeconds: live.lastUpdateAgeSeconds }
            : point;
        }));
        this.loading.set(false);
      },
      error: () => { this.error.set('No pudimos cargar los puntos. Intenta de nuevo.'); this.loading.set(false); },
    });
  }
  private merge(event: PointStatusEvent): void {
    this.points.update(points => points.map(point => {
      if (point.id !== event.pointId || (point.updatedAt && Date.parse(point.updatedAt) > Date.parse(event.capturedAt))) return point;
      return { ...point, status: event.status, waterDepthCm: event.waterDepthCm, updatedAt: event.capturedAt, lastUpdateAgeSeconds: Math.max(0, (this.now() - Date.parse(event.capturedAt)) / 1000) };
    }));
  }
}
