import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject } from 'rxjs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Alert, PublicPoint, ReadingEvent, WorkOrder } from '../../core/api/models';
import { AuthService } from '../../core/auth/auth.service';
import { LiveService } from '../../core/live/live.service';
import { PointsStore } from '../../core/state/points.store';
import { PointDetailComponent } from './point-detail.component';

describe('PointDetailComponent', () => {
  const point: PublicPoint = {id: 'P01', name: 'Punto simulado P01 — Centro', zone: 'Centro', lat: 21, lon: -89, status: 'Normal', simulated: true, waterDepthCm: 2, updatedAt: null, lastUpdateAgeSeconds: 2, watchThresholdCm: 20, alertThresholdCm: 40};
  function setup(supervisor = true, flushActivity = true) {
    const points = {points: signal([point]), now: signal(Date.now()), loading: signal(false), error: signal(null), age: () => 2, reload: vi.fn()};
    const reading$ = new Subject<ReadingEvent>();
    const alert$ = new Subject<Alert>(); const workOrder$ = new Subject<WorkOrder>();
    TestBed.configureTestingModule({imports: [PointDetailComponent], providers: [
      provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
      {provide: ActivatedRoute, useValue: {paramMap: new BehaviorSubject(convertToParamMap({id: 'P01'}))}},
      {provide: AuthService, useValue: {hasRole: () => supervisor}},
      {provide: PointsStore, useValue: points},
      {provide: LiveService, useValue: {reading$, alert$, workOrder$, reconnected$: new Subject<void>()}},
    ]});
    const fixture = TestBed.createComponent(PointDetailComponent);
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const initial = http.expectOne(request => request.url === '/api/telemetry/points/P01/readings');
    expect(initial.request.params.get('bucket')).toBe('5m');
    initial.flush([]);
    http.expectOne('/api/telemetry/points/P01/forecast').flush([]);
    if (flushActivity) {
      http.expectOne(request => request.url === '/api/ops/alerts' && request.params.get('pointId') === 'P01' && request.params.get('status') === 'Open').flush([]);
      for (const status of ['Open', 'Assigned', 'InProgress', 'Resolved']) {
        const request = http.expectOne(request => request.url === '/api/ops/work-orders' && request.params.get('status') === status && request.params.get('pointId') === 'P01');
        expect(request.request.params.get('limit')).toBe('50'); request.flush([]);
      }
    }
    return {form: fixture.componentInstance, fixture, http, points, reading$, alert$, workOrder$};
  }
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('renders chart axes as HTML labels at every width', () => {
    const {fixture} = setup();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelectorAll('.chart-frame svg text')).toHaveLength(0);
    expect(element.querySelectorAll('.chart-axis.y-left span')).toHaveLength(3);
    expect(element.querySelectorAll('.chart-axis.y-right span')).toHaveLength(3);
    expect(element.querySelectorAll('.chart-times span')).toHaveLength(3);
  });
  it('sends validated decimal thresholds, then refreshes public point values', () => {
    const {form, http, points} = setup();
    form.watchThreshold = 12.5; form.alertThreshold = 30;
    form.saveThresholds(); form.saveThresholds();
    const request = http.expectOne('/api/telemetry/points/P01/thresholds');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({watchThresholdCm: 12.5, alertThresholdCm: 30});
    expect(form.savingThresholds()).toBe(true);
    request.flush({});
    expect(points.reload).toHaveBeenCalledOnce();
    expect(form.thresholdFeedback()).toContain('guardados');
  });
  it('blocks invalid thresholds and operator edits without an API write', () => {
    const {form, http} = setup(false);
    form.watchThreshold = 20; form.alertThreshold = 40; form.saveThresholds();
    http.expectNone('/api/telemetry/points/P01/thresholds');
  });
  it('leaves values editable and shows generic errors after failed threshold save', () => {
    const {form, http} = setup();
    form.watchThreshold = 15; form.alertThreshold = 30; form.saveThresholds();
    http.expectOne('/api/telemetry/points/P01/thresholds').flush({detail: 'private exception'}, {status: 500, statusText: 'Error'});
    expect(form.savingThresholds()).toBe(false);
    expect(form.thresholdError()).toContain('Intenta de nuevo');
    expect(form.thresholdError()).not.toContain('private exception');
  });
  it('requests the selected time range with its matching bucket', () => {
    const {form, http} = setup();
    form.selectRange(24);
    const request = http.expectOne(request => request.url === '/api/telemetry/points/P01/readings');
    expect(request.request.params.get('bucket')).toBe('15m');
    expect(Date.parse(request.request.params.get('to') ?? '') - Date.parse(request.request.params.get('from') ?? '')).toBe(24 * 3600000);
    request.flush([]);
  });
  it('does not send invalid values even when submitted programmatically', () => {
    const {form, http} = setup();
    for (const [watch, alert] of [[0, 20], [30, 20], [20, 151], [null, 30]]) {
      form.watchThreshold = watch; form.alertThreshold = alert; form.saveThresholds();
    }
    http.expectNone('/api/telemetry/points/P01/thresholds');
  });
  it('refreshes bucketed chart data only for this point live events', async () => {
    vi.useFakeTimers();
    try {
      const {form, http, reading$} = setup();
      const event: ReadingEvent = {type: 'reading', deviceId: 'd', pointId: 'P02', capturedAt: new Date().toISOString(), waterDepthCm: 4, rainMm5min: 1, qualityFlag: 'ok', status: 'Normal'};
      reading$.next(event); await vi.advanceTimersByTimeAsync(250);
      http.expectNone(request => request.url.endsWith('/readings'));
      reading$.next({...event, pointId: 'P01'}); await vi.advanceTimersByTimeAsync(250);
      http.expectOne(request => request.url.endsWith('/P01/readings')).flush([event]);
      expect(form.readings()).toHaveLength(1);
    } finally { vi.useRealTimers(); }
  });
  it('keeps an alert closed during its point snapshot from being reopened', () => {
    const {form, http, alert$} = setup(true, false);
    const alert: Alert = {id: 'a', pointId: 'P01', pointName: point.name, zone: point.zone, level: 'Watch', status: 'Open', openedAt: new Date().toISOString(), closedAt: null, reason: 'Water depth threshold exceeded', depthCm: 25};
    alert$.next({...alert, status: 'Closed'});
    http.expectOne(request => request.url === '/api/ops/alerts').flush([alert]);
    http.match(request => request.url === '/api/ops/work-orders').forEach(request => request.flush([]));
    expect(form.openAlerts()).toEqual([]);
  });
  it('ignores stale work-order snapshots after changing the activity page', () => {
    const {form, http} = setup(true, false);
    const previous = http.match(request => request.url === '/api/ops/work-orders');
    form.loadOrders(50);
    const next = http.match(request => request.url === '/api/ops/work-orders');
    expect(next).toHaveLength(4);
    next.forEach(request => { expect(request.request.params.get('offset')).toBe('50'); request.flush([]); });
    previous.forEach(request => request.flush([]));
    http.expectOne(request => request.url === '/api/ops/alerts').flush([]);
    expect(form.orderOffset()).toBe(50);
  });
});
