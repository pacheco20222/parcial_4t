import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { Subject } from 'rxjs';
import { CitizenReport } from '../../core/api/models';
import { AuthService } from '../../core/auth/auth.service';
import { LiveService } from '../../core/live/live.service';
import { PointsStore } from '../../core/state/points.store';
import { WorkOrdersStore } from '../../core/state/work-orders.store';
import { ReportsComponent } from './reports.component';
const report:CitizenReport={id:'r',folio:'RC-1',pointId:'P01',category:'Encharcamiento',description:'Calle inundada',status:'Pending',reportedAt:'2026-11-12T00:00:00Z',linkedWorkOrderId:null};
describe('report moderation list', () => {
  let http:HttpTestingController;
  let live:Subject<CitizenReport>;
  beforeEach(() => {
    live=new Subject();
    TestBed.configureTestingModule({imports:[ReportsComponent],providers:[provideHttpClient(),provideHttpClientTesting(),provideRouter([]),{provide:AuthService,useValue:{me:signal({id:'operator'}),hasRole:() => true}},{provide:LiveService,useValue:{report$:live,reconnected$:new Subject<void>()}},{provide:PointsStore,useValue:{points:signal([])}},{provide:WorkOrdersStore,useValue:{orders:signal([]),hasMore:signal(false),error:signal(null)}}]});
    http=TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('keeps a newer live moderation event when a pending snapshot arrives', () => {
    const fixture=TestBed.createComponent(ReportsComponent);
    const request=http.expectOne('/api/ops/reports?limit=50&offset=0&status=Pending');
    live.next({...report,status:'Validated'}); request.flush([report]);
    expect(fixture.componentInstance.visible()).toEqual([]);
    expect(fixture.componentInstance.reports()[0].status).toBe('Validated');
  });
  it('disables actions while pending, then announces successful validation', () => {
    const fixture=TestBed.createComponent(ReportsComponent);
    http.expectOne('/api/ops/reports?limit=50&offset=0&status=Pending').flush([report]); fixture.detectChanges();
    const button=[...fixture.nativeElement.querySelectorAll('button')].find((item:HTMLButtonElement) => item.textContent?.trim()==='Validar') as HTMLButtonElement;
    button.click(); fixture.detectChanges(); expect(button.disabled).toBe(true);
    http.expectOne('/api/ops/reports/r/validate').flush({...report,status:'Validated'}); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=status]').textContent).toContain('Reporte validado');
    expect(fixture.componentInstance.visible()).toEqual([]);
  });
});
