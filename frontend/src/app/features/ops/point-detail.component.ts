import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime, filter, forkJoin } from 'rxjs';
import { Alert, Forecast, PointStatus, Reading, WorkOrder } from '../../core/api/models';
import { AuthService } from '../../core/auth/auth.service';
import { LiveService } from '../../core/live/live.service';
import { PointsStore } from '../../core/state/points.store';
import { formatAge, formatDepth, formatSla, statusLabel } from '../../core/state/format';
import { alertLevelLabel, displayText, orderStatusLabel, pointLabel, priorityLabel } from '../../core/state/labels';
import { compareOpenWorkOrders } from '../../core/state/work-order-ordering';
import { OrderPriorityComponent, OrderStateComponent } from '../../shared/order-indicators.component';
import { IconComponent } from '../../shared/icon.component';
import { CHART_BOTTOM, axisMaximum, chartX, chartY, depthPath, validThresholds } from './point-detail.helpers';

@Component({
  selector: 'app-point-detail', imports: [FormsModule, RouterLink, IconComponent, OrderPriorityComponent, OrderStateComponent],
  templateUrl: './point-detail.component.html', styleUrl: './point-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PointDetailComponent {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  private readonly live = inject(LiveService);
  private readonly destroyRef = inject(DestroyRef);
  readonly auth = inject(AuthService);
  readonly points = inject(PointsStore);
  readonly alerts = {alerts: signal<Alert[]>([]), loading: signal(false), error: signal('')};
  readonly orders = {orders: signal<WorkOrder[]>([]), loading: signal(false), error: signal('')};
  readonly alertOffset = signal(0);
  readonly orderOffset = signal(0);
  readonly moreAlerts = signal(false);
  readonly moreOrders = signal(false);
  private alertGeneration = 0;
  private orderGeneration = 0;
  private readonly alertEvents = new Map<string, Alert>();
  private readonly orderEvents = new Map<string, WorkOrder>();
  readonly id = signal('');
  readonly point = computed(() => this.points.points().find(point => point.id === this.id()));
  readonly openAlerts = computed(() => this.alerts.alerts().filter(alert => alert.pointId === this.id() && alert.status === 'Open'));
  readonly openOrders = computed(() => this.orders.orders().filter(order => order.pointId === this.id() && !['Closed', 'Cancelled'].includes(order.status)).sort((a,b) => compareOpenWorkOrders(a,b,this.points.now())));
  readonly range = signal<1 | 6 | 24>(6);
  readonly readings = signal<Reading[]>([]);
  readonly forecast = signal<Forecast[]>([]);
  readonly loading = signal(true);
  readonly forecastLoading = signal(true);
  readonly readingError = signal('');
  readonly forecastError = signal('');
  readonly from = signal(Date.now() - 6 * 3600000);
  readonly to = signal(Date.now());
  readonly forecastFrom = signal(Date.now());
  readonly depthMaximum = computed(() => axisMaximum([...this.readings().map(row => row.waterDepthCm), this.point()?.watchThresholdCm, this.point()?.alertThresholdCm]));
  readonly rainMaximum = computed(() => axisMaximum(this.readings().map(row => row.rainMm5min)));
  readonly forecastMaximum = computed(() => axisMaximum(this.forecast().map(row => row.precipMm)));
  readonly path = computed(() => depthPath(this.readings(), this.from(), this.to(), this.depthMaximum()));
  readonly depthDots = computed(() => this.readings().filter(row => row.waterDepthCm != null && Number.isFinite(row.waterDepthCm)).map(row => ({
    at: row.capturedAt, value: row.waterDepthCm,
    x: chartX(Date.parse(row.capturedAt), this.from(), this.to()),
    y: chartY(row.waterDepthCm ?? 0, this.depthMaximum()),
  })));
  readonly depthTicks = computed(() => [0, this.depthMaximum() / 2, this.depthMaximum()]);
  readonly timeTicks = computed(() => [this.from(), (this.from() + this.to()) / 2, this.to()]);
  readonly rainBars = computed(() => this.readings().filter(row => row.rainMm5min != null && Number.isFinite(row.rainMm5min)).map(row => ({
    at: row.capturedAt, value: row.rainMm5min ?? 0,
    x: chartX(Date.parse(row.capturedAt), this.from(), this.to()),
    y: chartY(row.rainMm5min ?? 0, this.rainMaximum()),
  })));
  readonly forecastBars = computed(() => this.forecast().map(row => ({
    at: row.forecastFor, value: row.precipMm,
    x: chartX(Date.parse(row.forecastFor), this.forecastFrom(), this.forecastFrom() + 24 * 3600000),
    y: chartY(row.precipMm, this.forecastMaximum()),
  })));
  readonly chartSummary = computed(() => `${pointLabel(this.point() ?? {id: this.id(), zone: ''})}: tirante en centímetros y lluvia en milímetros durante las últimas ${this.range()} horas; ${this.readings().length} lecturas. ${this.point()?.status === 'NoData' ? 'Sensor sin datos actuales.' : ''}`);
  readonly savingThresholds = signal(false);
  readonly thresholdFeedback = signal('');
  readonly thresholdError = signal('');
  readonly thresholdSubmitted = signal(false);
  watchThreshold: number | null = null;
  alertThreshold: number | null = null;
  private readingGeneration = 0;
  private forecastGeneration = 0;
  private initializedThresholdPoint = '';
  readonly pointLabel = pointLabel;
  readonly displayText = displayText;
  readonly statusLabel = statusLabel;
  readonly alertLevelLabel = alertLevelLabel;
  readonly orderStatusLabel = orderStatusLabel;
  readonly priorityLabel = priorityLabel;
  readonly formatSla = formatSla;
  readonly formatAge = formatAge;
  readonly formatDepth = formatDepth;
  readonly validThresholds = validThresholds;
  readonly chartY = chartY;
  readonly chartX = chartX;
  readonly baseline = CHART_BOTTOM;

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe(params => {
      this.id.set(params.get('id') ?? '');
      this.readings.set([]); this.forecast.set([]);
      this.thresholdFeedback.set(''); this.thresholdError.set(''); this.thresholdSubmitted.set(false);
      this.alertOffset.set(0); this.orderOffset.set(0);
      this.alerts.alerts.set([]); this.orders.orders.set([]);
      this.loadReadings(); this.loadForecast(); this.loadAlerts(); this.loadOrders();
    });
    effect(() => {
      const point = this.point();
      if (point && point.id !== this.initializedThresholdPoint) {
        this.watchThreshold = point.watchThresholdCm ?? null;
        this.alertThreshold = point.alertThresholdCm ?? null;
        this.initializedThresholdPoint = point.id;
      }
    });
    this.live.reading$.pipe(filter(event => event.pointId === this.id()), debounceTime(250), takeUntilDestroyed()).subscribe(() => this.loadReadings());
    this.live.alert$.pipe(takeUntilDestroyed()).subscribe(event => {
      if (event.pointId !== this.id()) return;
      this.alertEvents.set(event.id, event);
      const items = new Map(this.alerts.alerts().map(item => [item.id, item]));
      items.set(event.id, event); this.setAlerts([...items.values()]);
    });
    this.live.workOrder$.pipe(takeUntilDestroyed()).subscribe(event => {
      if (event.pointId !== this.id()) return;
      this.orderEvents.set(event.id, event);
      const items = new Map(this.orders.orders().map(item => [item.id, item]));
      items.set(event.id, event); this.setOrders([...items.values()]);
    });
    this.live.reconnected$.pipe(takeUntilDestroyed()).subscribe(() => { this.loadReadings(); this.loadForecast(); this.loadAlerts(); this.loadOrders(); });
  }

  selectRange(range: 1 | 6 | 24): void { if (range !== this.range()) { this.range.set(range); this.loadReadings(); } }
  loadAlerts(offset = this.alertOffset()): void {
    const generation = ++this.alertGeneration;
    this.alertEvents.clear(); this.alerts.loading.set(true); this.alerts.error.set('');
    this.http.get<Alert[]>('/api/ops/alerts', {params: {pointId: this.id(), status: 'Open', limit: 50, offset}}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: items => {
        if (generation !== this.alertGeneration) return;
        const merged = new Map(items.map(item => [item.id, item]));
        this.alertEvents.forEach((event, id) => merged.set(id, event));
        this.setAlerts([...merged.values()]); this.moreAlerts.set(items.length === 50);
        this.alertOffset.set(offset); this.alerts.loading.set(false);
      },
      error: () => { if (generation === this.alertGeneration) { this.alerts.error.set('No pudimos cargar las alertas. Intenta de nuevo.'); this.alerts.loading.set(false); } },
    });
  }
  loadOrders(offset = this.orderOffset()): void {
    const generation = ++this.orderGeneration;
    this.orderEvents.clear(); this.orders.loading.set(true); this.orders.error.set('');
    const requests = (['Open', 'Assigned', 'InProgress', 'Resolved'] as const).map(status => this.http.get<WorkOrder[]>('/api/ops/work-orders', {params: {pointId: this.id(), status, limit: 50, offset}}));
    forkJoin(requests).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: pages => {
        if (generation !== this.orderGeneration) return;
        const merged = new Map(pages.flat().map(item => [item.id, item]));
        this.orderEvents.forEach((event, id) => merged.set(id, event));
        this.setOrders([...merged.values()]); this.moreOrders.set(pages.some(items => items.length === 50));
        this.orderOffset.set(offset); this.orders.loading.set(false);
      },
      error: () => { if (generation === this.orderGeneration) { this.orders.error.set('No pudimos cargar las órdenes. Intenta de nuevo.'); this.orders.loading.set(false); } },
    });
  }
  private setAlerts(items: Alert[]): void { this.alerts.alerts.set(items.filter(item => item.pointId === this.id() && item.status === 'Open').sort((a, b) => b.openedAt.localeCompare(a.openedAt)).slice(0, 50)); }
  private setOrders(items: WorkOrder[]): void { this.orders.orders.set(items.filter(item => item.pointId === this.id() && !['Closed', 'Cancelled'].includes(item.status)).sort((a, b) => compareOpenWorkOrders(a,b,this.points.now())).slice(0, 200)); }
  loadReadings(): void {
    const id = this.id();
    if (!id) return;
    const generation = ++this.readingGeneration;
    const to = Date.now(); const from = to - this.range() * 3600000;
    this.loading.set(true); this.readingError.set('');
    this.http.get<Reading[]>(`/api/telemetry/points/${encodeURIComponent(id)}/readings`, {params: {
      bucket: {1: '1m', 6: '5m', 24: '15m'}[this.range()], from: new Date(from).toISOString(), to: new Date(to).toISOString(),
    }}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => {
        if (generation !== this.readingGeneration) return;
        this.readings.set(rows.filter(row => { const at = Date.parse(row.capturedAt); return at >= from && at <= to; }).sort((a, b) => a.capturedAt.localeCompare(b.capturedAt)));
        this.from.set(from); this.to.set(to); this.loading.set(false);
      },
      error: () => { if (generation === this.readingGeneration) { this.loading.set(false); this.readingError.set('No pudimos cargar las lecturas. Intenta de nuevo.'); } },
    });
  }
  loadForecast(): void {
    const id = this.id(); if (!id) return;
    const generation = ++this.forecastGeneration;
    const from = Date.now();
    this.forecastLoading.set(true); this.forecastError.set('');
    this.http.get<Forecast[]>(`/api/telemetry/points/${encodeURIComponent(id)}/forecast`).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => {
        if (generation !== this.forecastGeneration) return;
        this.forecast.set(rows.filter(row => { const at = Date.parse(row.forecastFor); return at >= from && at <= from + 24 * 3600000 && Number.isFinite(row.precipMm) && row.precipMm >= 0; }).sort((a, b) => a.forecastFor.localeCompare(b.forecastFor)));
        this.forecastFrom.set(from); this.forecastLoading.set(false);
      },
      error: () => { if (generation === this.forecastGeneration) { this.forecastLoading.set(false); this.forecastError.set('No pudimos cargar el pronóstico. Intenta de nuevo.'); } },
    });
  }
  saveThresholds(): void {
    if (!this.auth.hasRole('Supervisor') || this.savingThresholds()) return;
    this.thresholdSubmitted.set(true); this.thresholdError.set(''); this.thresholdFeedback.set('');
    if (!validThresholds(this.watchThreshold, this.alertThreshold)) return;
    this.savingThresholds.set(true);
    const id = this.id();
    this.http.patch(`/api/telemetry/points/${encodeURIComponent(id)}/thresholds`, {watchThresholdCm: this.watchThreshold, alertThresholdCm: this.alertThreshold}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.savingThresholds.set(false); this.points.reload();
        if (this.id() === id) this.thresholdFeedback.set('Umbrales guardados.');
      },
      error: () => {
        this.savingThresholds.set(false);
        if (this.id() === id) this.thresholdError.set('No pudimos guardar los umbrales. Intenta de nuevo.');
      },
    });
  }
  alertStatus(level: string): PointStatus { return level === 'DataGap' ? 'NoData' : level === 'Alert' ? 'Alert' : 'Watch'; }
  time(at: number | string): string { return new Intl.DateTimeFormat('es-MX', {hour: '2-digit', minute: '2-digit'}).format(new Date(at)); }
  date(at: string): string { return new Intl.DateTimeFormat('es-MX', {dateStyle: 'short', timeStyle: 'short'}).format(new Date(at)); }
  number(value: number | null): string { return value == null ? 'Sin datos' : new Intl.NumberFormat('es-MX', {maximumFractionDigits: 1}).format(value); }
}
