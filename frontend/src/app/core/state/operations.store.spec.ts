import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Subject } from 'rxjs';
import { Alert, Me, WorkOrder } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { LiveService } from '../live/live.service';
import { AlertsStore } from './alerts.store';
import { WorkOrdersStore } from './work-orders.store';
const alert: Alert = {id: 'a', pointId: 'P01', pointName: 'Centro', zone: 'Centro', level: 'Alert', status: 'Open', openedAt: '2026-11-12T00:00:00Z', closedAt: null, reason: 'Umbral superado', depthCm: 40};
const order: WorkOrder = {id: 'o', folio: 'OT-2026-00001', pointId: 'P01', alertId: 'a', citizenReportId: null, title: 'Inspección', priority: 'High', status: 'Open', crewId: null, createdAt: alert.openedAt, slaDueAt: alert.openedAt, assignedAt: null, onSiteAt: null, resolvedAt: null, closedAt: null, cancelReason: null, version: 'version-initial'};
describe('operations stores fetch/live reconciliation', () => {
  let http: HttpTestingController;
  let alerts: Subject<Alert>;
  let orders: Subject<WorkOrder>;
  beforeEach(() => {
    alerts = new Subject(); orders = new Subject();
    TestBed.configureTestingModule({providers: [provideHttpClient(), provideHttpClientTesting(), {provide: AuthService, useValue: {me: signal<Me | null>({id: 'staff', email: 'staff@example.test', roles: ['Operator'], mfaEnabled: false})}}, {provide: LiveService, useValue: {alert$: alerts, workOrder$: orders, reconnected$: new Subject<void>()}}]});
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('does not reopen an alert closed while its snapshot was in flight', () => {
    const store = TestBed.inject(AlertsStore); TestBed.tick(); alerts.next({...alert, status: 'Closed', closedAt: '2026-11-12T00:01:00Z'});
    http.expectOne('/api/ops/alerts?status=Open').flush([alert]); expect(store.alerts()).toEqual([]);
  });
  it('retains work-order events received during snapshot fetch with opaque versions', () => {
    const store = TestBed.inject(WorkOrdersStore); TestBed.tick(); orders.next({...order, version: 'new-opaque-guid', status: 'Assigned', crewId: 'crew'});
    http.expectOne('/api/ops/work-orders').flush([order]); expect(store.orders()[0].status).toBe('Assigned'); expect(store.orders()[0].version).toBe('new-opaque-guid');
  });
  it('loads additional bounded pages and merges them with current live orders', () => {
    const store = TestBed.inject(WorkOrdersStore); TestBed.tick();
    http.expectOne('/api/ops/work-orders').flush(Array.from({length:50},(_,i) => ({...order,id:`o${i}`})));
    expect(store.hasMore()).toBe(true);
    store.loadMore();
    orders.next({...order,id:'o0',status:'Assigned',version:'live'});
    http.expectOne('/api/ops/work-orders?limit=50&offset=50').flush([{...order,id:'older'}]);
    expect(store.orders()).toHaveLength(51);
    expect(store.orders().find(item => item.id==='o0')?.version).toBe('live');
    expect(store.hasMore()).toBe(false);
  });

  it('sends board filters to the API and preserves them when loading another page', () => {
    const store = TestBed.inject(WorkOrdersStore); TestBed.tick(); http.expectOne('/api/ops/work-orders').flush([]);
    store.reload({priority:'Critical',pointId:'P05',overdue:true});
    const first=http.expectOne(request => request.url==='/api/ops/work-orders');
    expect(first.request.params.get('priority')).toBe('Critical'); expect(first.request.params.get('pointId')).toBe('P05'); expect(first.request.params.get('overdue')).toBe('true');
    first.flush(Array.from({length:50},(_,i) => ({...order,id:`filtered${i}`})));
    store.loadMore(); const next=http.expectOne(request => request.url==='/api/ops/work-orders');
    expect(next.request.params.get('pointId')).toBe('P05'); expect(next.request.params.get('offset')).toBe('50'); next.flush([]);
  });

});
