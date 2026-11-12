import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { Subject, of } from 'rxjs';
import { vi } from 'vitest';
import { Alert } from '../../core/api/models';
import { PointsStore } from '../../core/state/points.store';
import { AlertsStore } from '../../core/state/alerts.store';
import { AuthService } from '../../core/auth/auth.service';
import { LiveService } from '../../core/live/live.service';
import { AlertsComponent } from './alerts.component';
const alert: Alert = {id:'a',pointId:'P01',pointName:'Centro',zone:'Centro',status:'Open',level:'Alert',reason:'Water depth threshold exceeded',openedAt:'2026-11-12T00:00:00Z',closedAt:null,depthCm:40};
describe('alerts list', () => {
  let http: HttpTestingController;
  let events: Subject<Alert>;
  beforeEach(() => {
    events = new Subject();
    TestBed.configureTestingModule({providers:[provideRouter([]),provideHttpClient(),provideHttpClientTesting(),
      {provide:PointsStore,useValue:{points:signal([]),now:signal(Date.now())}},
      {provide:AlertsStore,useValue:{reload:vi.fn()}},
      {provide:AuthService,useValue:{hasRole:()=>true,loadMe:()=>of(null)}},
      {provide:LiveService,useValue:{alert$:events,reconnected$:new Subject<void>()}}]});
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(()=>http.verify());
  it('pages with explicit bounds, and prevents stale fetch from reopening live-closed alert',()=>{
    const page = TestBed.createComponent(AlertsComponent).componentInstance;
    const req = http.expectOne(r=>r.url==='/api/ops/alerts');
    expect(req.request.params.get('limit')).toBe('50'); expect(req.request.params.get('offset')).toBe('0');
    events.next({...alert,status:'Closed'}); req.flush([alert]); expect(page.visible()).toEqual([]);
    page.changePage(1); const next = http.expectOne(r=>r.params.get('offset')==='50'); next.flush([]);
  });
  it('disables duplicate close calls, sends exact PATCH and reports failures',()=>{
    const page=TestBed.createComponent(AlertsComponent).componentInstance;
    http.expectOne(r=>r.url==='/api/ops/alerts').flush([alert]);
    page.close(alert); page.close(alert);
    const req=http.expectOne('/api/ops/alerts/a'); expect(req.request.body).toEqual({status:'Closed'}); expect(page.pending().has('a')).toBe(true);
    req.flush({}, {status:500,statusText:'Error'}); expect(page.pending().size).toBe(0); expect(page.actionErrors()['a']).toContain('Intenta de nuevo');
  });
  it('removes a closed alert and announces success',()=>{
    const page=TestBed.createComponent(AlertsComponent).componentInstance;
    http.expectOne(r=>r.url==='/api/ops/alerts').flush([alert]);
    page.close(alert);
    http.expectOne('/api/ops/alerts/a').flush({...alert,status:'Closed'});
    expect(page.visible()).toEqual([]); expect(page.feedback()).toBe('Alerta cerrada.');
    expect(page.pending().size).toBe(0);
  });
  it('does not let an old filter request replace a newer page',()=>{
    const page=TestBed.createComponent(AlertsComponent).componentInstance;
    const old=http.expectOne(r=>r.url==='/api/ops/alerts');
    page.status='Closed'; page.filtersChanged();
    http.expectOne(r=>r.params.get('status')==='Closed').flush([{...alert,status:'Closed'}]);
    old.flush([alert]); expect(page.visible()[0].status).toBe('Closed');
  });

});
