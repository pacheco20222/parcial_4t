import { ChangeDetectionStrategy, Component, ElementRef, afterRenderEffect, computed, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { PublicPoint, PointStatus } from '../../core/api/models';
import { PointsStore } from '../../core/state/points.store';
import { KpisStore } from '../../core/state/kpis.store';
import { AlertsStore } from '../../core/state/alerts.store';
import { WorkOrdersStore } from '../../core/state/work-orders.store';
import { formatAge, formatDepth, formatSla, statusLabel } from '../../core/state/format';
import { pointLabel, displayText } from '../../core/state/labels';
import { IconComponent } from '../../shared/icon.component';
import { MapComponent } from '../../shared/map.component';
import { OrderPriorityComponent, OrderStateComponent } from '../../shared/order-indicators.component';
import { compareOpenWorkOrders } from '../../core/state/work-order-ordering';
import { animatePointMove, PointRowSnapshot } from '../../shared/point-flip';

type LadderEntry =
  | { kind: 'heading'; key: string; status: PointStatus; count: number }
  | { kind: 'point'; key: string; status: PointStatus; point: PublicPoint }
  | { kind: 'empty' | 'tail'; key: string; status: PointStatus; hasPoints: boolean };

@Component({
  selector: 'app-panel', imports: [RouterLink, IconComponent, MapComponent, OrderPriorityComponent, OrderStateComponent],
  templateUrl: './panel.component.html', styleUrl: './panel.component.scss', changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PanelComponent {
  private readonly router = inject(Router);
  readonly points = inject(PointsStore);
  readonly kpis = inject(KpisStore);
  readonly alerts = inject(AlertsStore);
  readonly workOrders = inject(WorkOrdersStore);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly statusLabel = statusLabel;
  readonly pointLabel = pointLabel;
  readonly displayText = displayText;
  readonly formatSla = formatSla;
  readonly depthValue = formatDepth;
  // A single keyed loop preserves each point's DOM node when it changes rung.
  readonly ladderEntries = computed<LadderEntry[]>(() => (['Alert', 'Watch', 'Normal', 'NoData'] as PointStatus[]).flatMap(status => {
    const points = this.points.points().filter(point => point.status === status);
    const entries: LadderEntry[] = [{ kind: 'heading', key: `heading-${status}`, status, count: points.length }];
    entries.push(...points.map(point => ({ kind: 'point' as const, key: point.id, status, point })));
    if (!points.length) entries.push({ kind: 'empty', key: `empty-${status}`, status, hasPoints: false });
    entries.push({ kind: 'tail', key: `tail-${status}`, status, hasPoints: points.length > 0 });
    return entries;
  }));
  readonly openOrders = computed(() => this.workOrders.orders().filter(o => !['Closed', 'Cancelled'].includes(o.status))
    .sort((a, b) => compareOpenWorkOrders(a, b, this.points.now())));
  private previousRows = new Map<string, PointRowSnapshot>();

  constructor() {
    afterRenderEffect(() => {
      // Read after Angular has moved keyed nodes; the prior pass holds pre-update geometry.
      this.ladderEntries();
      const current = new Map<string, PointRowSnapshot>();
      for (const row of this.host.nativeElement.querySelectorAll<HTMLElement>('[data-point-id]')) {
        const id = row.dataset['pointId'];
        if (!id) continue;
        const snapshot = { rect: row.getBoundingClientRect(), status: row.dataset['status'] ?? '' };
        const previous = this.previousRows.get(id);
        if (previous && previous.status !== snapshot.status) animatePointMove(row, previous.rect, snapshot.rect);
        current.set(id, snapshot);
      }
      this.previousRows = current;
    });
  }

  selectPoint(id: string): void { void this.router.navigate(['/ops/puntos', id]); }
  depth(point: PublicPoint): string { return point.status === 'NoData' || point.waterDepthCm === null ? 'sin datos' : formatDepth(point.waterDepthCm); }
  number(value: number | null | undefined): string { return value == null ? '—' : new Intl.NumberFormat('es-MX', { maximumFractionDigits: 1 }).format(value); }
  age(at: string): string { return formatAge((this.points.now() - Date.parse(at)) / 1000); }
  alertStatus(level: string): PointStatus { return level === 'DataGap' ? 'NoData' : level === 'Alert' ? 'Alert' : 'Watch'; }
  overdue(dueAt: string): boolean { return Date.parse(dueAt) < this.points.now(); }
}
