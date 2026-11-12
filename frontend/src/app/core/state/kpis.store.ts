import { DestroyRef, Injectable, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime, forkJoin, merge } from 'rxjs';
import { OpsKpis, TelemetryKpis } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { LiveService } from '../live/live.service';
@Injectable({ providedIn: 'root' })
export class KpisStore {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);
  readonly telemetry = signal<TelemetryKpis | null>(null);
  readonly ops = signal<OpsKpis | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  constructor() {
    effect(() => { if (this.auth.me()) this.reload(); else { this.telemetry.set(null); this.ops.set(null); } });
    merge(this.live.pointStatus$, this.live.reading$, this.live.alert$, this.live.workOrder$, this.live.report$).pipe(debounceTime(2000), takeUntilDestroyed()).subscribe(() => this.reload());
    this.live.reconnected$.pipe(takeUntilDestroyed()).subscribe(() => this.reload());
  }
  reload(): void {
    if (!this.auth.me()) return;
    const userId = this.auth.me()?.id;
    this.loading.set(true); this.error.set(null);
    forkJoin({
      telemetry: this.http.get<TelemetryKpis>('/api/telemetry/kpis'),
      ops: this.http.get<OpsKpis>('/api/ops/kpis'),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => {
        if (this.auth.me()?.id === userId) { this.telemetry.set(value.telemetry); this.ops.set(value.ops); }
        this.loading.set(false);
      },
      error: () => { this.error.set('No pudimos cargar los indicadores. Intenta de nuevo.'); this.loading.set(false); },
    });
  }
}
