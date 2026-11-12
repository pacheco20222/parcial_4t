import { DestroyRef, Injectable, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Priority, WorkOrder } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { LiveService } from '../live/live.service';
export interface WorkOrderFilters { priority?: Priority; pointId?: string; overdue?: boolean; }
@Injectable({providedIn: 'root'})
export class WorkOrdersStore {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);
  private fetchGeneration = 0;
  private offset = 0;
  private filters: WorkOrderFilters = {};
  readonly hasMore = signal(false);
  private readonly liveEvents = new Map<string, WorkOrder>();
  readonly orders = signal<WorkOrder[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  constructor() {
    effect(() => { if (this.auth.me()) this.reload(); else { ++this.fetchGeneration; this.orders.set([]); this.hasMore.set(false); this.loading.set(false); } });
    this.live.workOrder$.pipe(takeUntilDestroyed()).subscribe(event => {
      if (!this.auth.me()) return;
      this.upsert(event);
    });
    this.live.reconnected$.pipe(takeUntilDestroyed()).subscribe(() => this.reload());
  }
  upsert(order: WorkOrder): void {
    this.liveEvents.set(order.id, order);
    this.orders.update(items => [order, ...items.filter(item => item.id !== order.id)]);
  }
  reload(filters: WorkOrderFilters = this.filters): void { this.filters = filters; this.offset = 0; this.fetchPage(false); }
  loadMore(): void { if (this.hasMore() && !this.loading()) this.fetchPage(true); }
  private fetchPage(append: boolean): void {
    if (!this.auth.me()) return;
    const userId = this.auth.me()?.id;
    const generation = ++this.fetchGeneration;
    this.liveEvents.clear();
    this.loading.set(true); this.error.set(null);
    this.http.get<WorkOrder[]>('/api/ops/work-orders', append || Object.keys(this.filters).length ? {params:{...this.filters,limit:50,offset:this.offset}} : {}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: items => {
        if (generation !== this.fetchGeneration) return;
        if (this.auth.me()?.id === userId) {
          const merged = new Map((append ? [...this.orders(), ...items] : items).map(item => [item.id, item]));
          this.offset += items.length;
          this.hasMore.set(items.length === 50);
          this.liveEvents.forEach((event, id) => {
            merged.set(id, event);
          });
          this.orders.set([...merged.values()]);
        }
        this.loading.set(false);
      },
      error: () => { if (generation !== this.fetchGeneration) return; this.error.set('No pudimos cargar las órdenes. Intenta de nuevo.'); this.loading.set(false); },
    });
  }
}
