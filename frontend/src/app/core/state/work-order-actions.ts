import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, finalize } from 'rxjs';
import { OrderStatus, Priority, WorkOrder } from '../api/models';
import { AuthService } from '../auth/auth.service';
import { WorkOrdersStore } from './work-orders.store';

export function canTransition(from: OrderStatus, to: OrderStatus, supervisor: boolean): boolean {
  return (from === 'Assigned' && to === 'InProgress') || (from === 'InProgress' && to === 'Resolved') ||
    (supervisor && ((from === 'Resolved' && to === 'Closed') || (from === 'Open' && to === 'Cancelled')));
}
export function slaFraction(order: Pick<WorkOrder,'createdAt'|'slaDueAt'>, now: number): number {
  const start=Date.parse(order.createdAt), end=Date.parse(order.slaDueAt);
  return Number.isFinite(start) && Number.isFinite(end) && end > start ? Math.max(0,Math.min(1,(end-now)/(end-start))) : 0;
}
export function slaReference(order: Pick<WorkOrder,'status'|'resolvedAt'|'closedAt'>,now:number):number|null {
  if(order.status==='Cancelled') return null;
  if(order.status!=='Resolved' && order.status!=='Closed') return now;
  const at=Date.parse(order.resolvedAt ?? order.closedAt ?? '');
  return Number.isFinite(at)?at:null;
}
@Injectable({providedIn:'root'})
export class WorkOrderActions {
  private readonly http=inject(HttpClient);
  private readonly destroyRef=inject(DestroyRef);
  private readonly auth=inject(AuthService);
  private readonly store=inject(WorkOrdersStore);
  readonly pending=signal<string|null>(null);
  readonly error=signal<string|null>(null);
  readonly success=signal('');
  assign(id:string, crewId:string):void {
    const order=this.store.orders().find(item => item.id===id);
    if (!order || this.pending() || !this.auth.hasRole('Supervisor') || order.status!=='Open' || !crewId) return;
    this.send(id,this.http.patch<WorkOrder>(`/api/ops/work-orders/${encodeURIComponent(id)}/assign`,{crewId,version:order.version}),'Orden asignada.');
  }
  transition(id:string,status:OrderStatus,reason?:string):void {
    const order=this.store.orders().find(item => item.id===id);
    if (!order || this.pending() || !this.auth.hasRole('Operator') || !canTransition(order.status,status,this.auth.hasRole('Supervisor'))) return;
    if (status==='Cancelled' && !reason?.trim()) { this.error.set('Escribe el motivo para cancelar la orden.'); return; }
    this.send(id,this.http.patch<WorkOrder>(`/api/ops/work-orders/${encodeURIComponent(id)}/transition`,{status,version:order.version,...(status==='Cancelled'?{reason:reason?.trim()}:{})}),'Orden actualizada.');
  }
  create(input:{pointId:string;title:string;priority:Priority}):void {
    if (this.pending() || !this.auth.hasRole('Supervisor')) return;
    this.send('create',this.http.post<WorkOrder>('/api/ops/work-orders',input),'Orden creada.');
  }
  private send(id:string,request:Observable<WorkOrder>,message:string):void {
    this.pending.set(id); this.error.set(null); this.success.set('');
    request.pipe(takeUntilDestroyed(this.destroyRef),finalize(() => this.pending.set(null))).subscribe({
      next:order => { this.store.upsert(order); this.success.set(message); },
      error:(error:HttpErrorResponse) => {
        if (error.status===409) { this.error.set('Otra persona modificó esta orden; se recargó la información'); this.store.reload(); }
        else this.error.set('No pudimos guardar la orden. Revisa los datos e intenta de nuevo.');
      },
    });
  }
}
