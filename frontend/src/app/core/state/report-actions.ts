import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { CitizenReport } from '../api/models';
@Injectable({providedIn:'root'})
export class ReportActions {
  private readonly http=inject(HttpClient);
  review(id:string,action:'validate'|'reject'):Observable<CitizenReport> { return this.http.patch<CitizenReport>(`/api/ops/reports/${encodeURIComponent(id)}/${action}`,{}); }
  link(id:string,workOrderId:string):Observable<CitizenReport> { return this.http.patch<CitizenReport>(`/api/ops/reports/${encodeURIComponent(id)}/link`,{workOrderId}); }
}
