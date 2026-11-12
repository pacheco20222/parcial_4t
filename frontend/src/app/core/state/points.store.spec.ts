import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Subject } from 'rxjs';
import { PointsStore } from './points.store';
import { LiveService } from '../live/live.service';
import { PointStatusEvent, PublicPoint, ReadingEvent } from '../api/models';
const point: PublicPoint = {id: 'P01', name: 'Centro', zone: 'Centro', lat: 20.97, lon: -89.62, status: 'Normal', simulated: true, waterDepthCm: 2, updatedAt: '2026-11-12T00:00:00Z', lastUpdateAgeSeconds: 0};
describe('PointsStore', () => {
  let store: PointsStore;
  let http: HttpTestingController;
  let pointStatus: Subject<PointStatusEvent>;
  let reading: Subject<ReadingEvent>;
  let reconnected: Subject<void>;
  beforeEach(() => {
    pointStatus = new Subject(); reading = new Subject(); reconnected = new Subject();
    TestBed.configureTestingModule({providers: [provideHttpClient(), provideHttpClientTesting(), {provide: LiveService, useValue: {pointStatus$: pointStatus, reading$: reading, reconnected$: reconnected, start: vi.fn()}}]});
    store = TestBed.inject(PointsStore); http = TestBed.inject(HttpTestingController); http.expectOne('/api/telemetry/public/points').flush([point, {...point, id: 'P02', status: 'NoData', waterDepthCm: null}]);
  });
  afterEach(() => http.verify());
  it('merges by pointId and ranks Alert > Watch > NoData > Normal', () => {
    expect(store.worstStatus()).toBe('NoData'); pointStatus.next({pointId: 'P01', status: 'Watch', waterDepthCm: 22, capturedAt: '2026-11-12T00:01:00Z'}); expect(store.worstStatus()).toBe('Watch'); expect(store.counts().Watch).toBe(1);
    pointStatus.next({pointId: 'P01', status: 'Alert', waterDepthCm: 40, capturedAt: '2026-11-12T00:02:00Z'}); expect(store.worstStatus()).toBe('Alert'); expect(store.points()[1].waterDepthCm).toBeNull();
    pointStatus.next({pointId: 'P01', status: 'Normal', waterDepthCm: 0, capturedAt: '2026-11-12T00:00:30Z'}); expect(store.worstStatus()).toBe('Alert');
  });
  it('refetches on reconnect and retains fresher live readings', () => {
    reconnected.next(); reading.next({type: 'telemetry.reading', deviceId: 'device', qualityFlag: 'ok', pointId: 'P01', status: 'Alert', waterDepthCm: 40, rainMm5min: 2, capturedAt: '2026-11-12T00:02:00Z'}); http.expectOne('/api/telemetry/public/points').flush([point]); expect(store.points()[0].waterDepthCm).toBe(40);
  });
  it('refreshes threshold metadata without replacing a fresher live measurement', () => {
    store.reload();
    pointStatus.next({pointId:'P01',status:'Alert',waterDepthCm:40,capturedAt:'2026-11-12T00:02:00Z'});
    http.expectOne('/api/telemetry/public/points').flush([{...point,watchThresholdCm:18.5,alertThresholdCm:31.5}]);
    expect(store.points()[0].watchThresholdCm).toBe(18.5);
    expect(store.points()[0].alertThresholdCm).toBe(31.5);
    expect(store.points()[0].waterDepthCm).toBe(40);
    expect(store.points()[0].status).toBe('Alert');
  });

});
