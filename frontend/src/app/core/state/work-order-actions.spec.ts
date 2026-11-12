import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { vi } from 'vitest';
import { WorkOrder } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { WorkOrdersStore } from './work-orders.store';
import { WorkOrderActions, canTransition, slaFraction, slaReference } from './work-order-actions';
const order: WorkOrder = {id:'o',folio:'OT-1',pointId:'P01',alertId:null,citizenReportId:null,title:'Revisar',status:'Open',priority:'High',crewId:null,createdAt:'2026-11-12T00:00:00Z',slaDueAt:'2026-11-12T01:00:00Z',assignedAt:null,onSiteAt:null,resolvedAt:null,closedAt:null,cancelReason:null,version:'opaque-version'};
describe('work-order rules and actions', () => {
  it('permits only documented state transitions and supervisor closure/cancellation', () => {
    expect(canTransition('Open','Assigned',true)).toBe(false);
    expect(canTransition('Assigned','InProgress',false)).toBe(true);
    expect(canTransition('InProgress','Resolved',false)).toBe(true);
    expect(canTransition('Resolved','Closed',false)).toBe(false);
    expect(canTransition('Resolved','Closed',true)).toBe(true);
    expect(canTransition('Open','Cancelled',true)).toBe(true);
    expect(canTransition('Open','Cancelled',false)).toBe(false);
    expect(canTransition('Closed','Open',true)).toBe(false);
  });
  it('clamps remaining SLA fraction and handles invalid dates', () => {
    expect(slaFraction(order,Date.parse('2026-11-12T00:30:00Z'))).toBe(.5);
    expect(slaFraction(order,Date.parse('2026-11-12T02:00:00Z'))).toBe(0);
    expect(slaFraction(order,Date.parse('2026-11-11T00:00:00Z'))).toBe(1);
    expect(slaFraction({...order,slaDueAt:'bad'},Date.now())).toBe(0);
  });
  it('freezes completed SLA at resolution and stops tracking cancelled orders', () => {
    const resolved={...order,status:'Resolved' as const,resolvedAt:'2026-11-12T00:30:00Z'};
    expect(slaReference(resolved,Date.parse('2026-11-12T02:00:00Z'))).toBe(Date.parse(resolved.resolvedAt));
    expect(slaFraction(resolved,slaReference(resolved,Date.now())!)).toBe(.5);
    expect(slaReference({...order,status:'Cancelled'},Date.now())).toBeNull();
    expect(slaReference({...order,status:'Closed'},Date.now())).toBeNull();
  });
  let http: HttpTestingController;
  let actions: WorkOrderActions;
  const store={orders:signal([order]),reload:vi.fn(),upsert:(updated:WorkOrder) => store.orders.update(items => [updated,...items.filter(item => item.id!==updated.id)])};
  beforeEach(() => {
    store.orders.set([order]); store.reload.mockClear();
    TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting(),{provide:WorkOrdersStore,useValue:store},{provide:AuthService,useValue:{hasRole:() => true}}]});
    http=TestBed.inject(HttpTestingController); actions=TestBed.inject(WorkOrderActions);
  });
  afterEach(() => http.verify());
  it('sends latest opaque version and reloads on 409 with required feedback', () => {
    store.orders.set([{...order,status:'Assigned',version:'latest-version'}]); actions.transition(order.id,'InProgress');
    const request=http.expectOne('/api/ops/work-orders/o/transition'); expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({status:'InProgress',version:'latest-version'});
    request.flush({}, {status:409,statusText:'Conflict'});
    expect(store.reload).toHaveBeenCalledOnce(); expect(actions.error()).toBe('Otra persona modificó esta orden; se recargó la información'); expect(actions.pending()).toBeNull();
  });
  it('requires cancellation reason and sends assignment version', () => {
    actions.transition('o','Cancelled','  '); http.expectNone('/api/ops/work-orders/o/transition');
    actions.assign('o','crew'); const request=http.expectOne('/api/ops/work-orders/o/assign'); expect(request.request.body).toEqual({crewId:'crew',version:order.version});
    request.flush({...order,status:'Assigned',crewId:'crew',version:'next'}); expect(store.orders()[0].version).toBe('next'); expect(actions.success()).toContain('asignada');
  });
  it('does not let operators assign or close orders', () => {
    vi.spyOn(TestBed.inject(AuthService),'hasRole').mockImplementation(role => role==='Operator');
    actions.assign('o','crew');
    store.orders.set([{...order,status:'Resolved'}]); actions.transition('o','Closed');
    http.expectNone(request => request.method==='PATCH');
  });
  it('prevents duplicate pending writes', () => { actions.assign('o','crew'); actions.assign('o','crew'); http.expectOne('/api/ops/work-orders/o/assign').flush(order); });
});
