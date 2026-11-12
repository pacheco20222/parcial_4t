import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ReportActions } from './report-actions';
describe('report moderation calls', () => {
  let http:HttpTestingController;
  let actions:ReportActions;
  beforeEach(() => { TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting()]}); http=TestBed.inject(HttpTestingController); actions=TestBed.inject(ReportActions); });
  afterEach(() => http.verify());
  it.each(['validate','reject'] as const)('PATCHes %s',action => { actions.review('report',action).subscribe(); const request=http.expectOne('/api/ops/reports/report/'+action); expect(request.request.method).toBe('PATCH'); expect(request.request.body).toEqual({}); request.flush({}); });
  it('links using exactly workOrderId', () => { actions.link('report','order').subscribe(); const request=http.expectOne('/api/ops/reports/report/link'); expect(request.request.method).toBe('PATCH'); expect(request.request.body).toEqual({workOrderId:'order'}); request.flush({}); });
});
