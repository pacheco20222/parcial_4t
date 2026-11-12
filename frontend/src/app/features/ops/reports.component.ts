import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable, finalize } from 'rxjs';
import { CitizenReport, WorkOrder } from '../../core/api/models';
import { LiveService } from '../../core/live/live.service';
import { AuthService } from '../../core/auth/auth.service';
import { PointsStore } from '../../core/state/points.store';
import { WorkOrdersStore } from '../../core/state/work-orders.store';
import { compareOpenWorkOrders } from '../../core/state/work-order-ordering';
import { ReportActions } from '../../core/state/report-actions';
import { displayText, pointLabel, reportStatusLabel } from '../../core/state/labels';
@Component({
  selector:'app-reports', imports:[FormsModule,RouterLink,DatePipe],
  templateUrl:'./reports.component.html',styleUrls:['./views.scss','./reports.component.scss'],changeDetection:ChangeDetectionStrategy.OnPush,
})
export class ReportsComponent {
  readonly points=inject(PointsStore);
  readonly orders=inject(WorkOrdersStore);
  readonly auth=inject(AuthService);
  private readonly http=inject(HttpClient);
  private readonly live=inject(LiveService);
  private readonly destroyRef=inject(DestroyRef);
  private readonly actions=inject(ReportActions);
  readonly reports=signal<CitizenReport[]>([]);
  readonly loading=signal(false);
  readonly error=signal('');
  readonly pending=signal<string|null>(null);
  readonly actionError=signal('');
  readonly activeAction=signal('');
  readonly success=signal('');
  readonly status=signal('Pending');
  readonly pointId=signal('');
  readonly hasMore=signal(false);
  readonly selectedOrder:Record<string,string>={};
  private generation=0;
  private offset=0;
  private readonly events=new Map<string,CitizenReport>();
  readonly pointLabel=pointLabel;
  readonly reportStatusLabel=reportStatusLabel;
  readonly displayText=displayText;
  readonly visible=computed(() => this.reports().filter(report => (!this.pointId() || report.pointId===this.pointId()) && (!this.status() || this.effectiveStatus(report)===this.status())));
  readonly detachedError=computed(() => !!this.actionError() && !this.visible().some(report => report.id===this.activeAction()));
  readonly statuses=computed(() => [...new Set(['Pending','Validated','Rejected','Linked',...this.reports().map(report => this.effectiveStatus(report))])]);
  constructor() {
    this.live.report$.pipe(takeUntilDestroyed()).subscribe(report => { if (!this.auth.me()) return; this.events.set(report.id,report); this.upsert(report); });
    this.live.reconnected$.pipe(takeUntilDestroyed()).subscribe(() => this.reload());
    this.reload();
  }
  effectiveStatus(report:CitizenReport):string { return report.linkedWorkOrderId ? 'Linked' : report.status; }
  pointName(id:string|null):string { const point=this.points.points().find(item => item.id===id); return point?pointLabel(point):id??'Sin punto asociado'; }
  categoryLabel(category:string):string { return ({Encharcamiento:'Encharcamiento',CalleIntransitable:'Calle intransitable',DrenajeTapado:'Drenaje tapado',Otro:'Otro'} as Record<string,string>)[category]??category; }
  linkableOrders(report:CitizenReport):WorkOrder[] { return this.orders.orders().filter(order => !['Resolved','Closed','Cancelled'].includes(order.status) && (!report.pointId || report.pointId===order.pointId)).sort((a,b) => compareOpenWorkOrders(a,b,this.points.now())); }
  reload():void { this.offset=0; this.fetch(false); }
  loadMore():void { if (this.hasMore() && !this.loading()) this.fetch(true); }
  private fetch(append:boolean):void {
    if (!this.auth.me()) return;
    const generation=++this.generation;
    this.events.clear(); this.loading.set(true); this.error.set('');
    const params:Record<string,string|number>={limit:50,offset:this.offset};
    if(this.status()) params['status']=this.status()==='Linked'?'Validated':this.status();
    if(this.pointId()) params['pointId']=this.pointId();
    this.http.get<CitizenReport[]>('/api/ops/reports',{params}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next:reports => {
        if(generation!==this.generation) return;
        const merged=new Map((append?[...this.reports(),...reports]:reports).map(report => [report.id,report]));
        this.events.forEach((report,id) => merged.set(id,report)); this.reports.set([...merged.values()]); this.offset+=reports.length;
        this.hasMore.set(reports.length===50); this.loading.set(false);
      },
      error:() => { if(generation!==this.generation) return; this.error.set('No pudimos cargar los reportes. Intenta de nuevo.'); this.loading.set(false); },
    });
  }
  review(report:CitizenReport,action:'validate'|'reject'):void {
    if(this.pending() || !this.auth.hasRole('Operator') || report.status!=='Pending') return;
    this.send(report.id,this.actions.review(report.id,action),action==='validate'?'Reporte validado.':'Reporte rechazado.');
  }
  link(report:CitizenReport):void {
    const id=this.selectedOrder[report.id];
    if(this.pending() || !this.auth.hasRole('Operator') || report.status!=='Validated' || report.linkedWorkOrderId || !this.linkableOrders(report).some(order => order.id===id)) return;
    this.send(report.id,this.actions.link(report.id,id),'Reporte vinculado a la orden.');
  }
  private send(id:string,request:Observable<CitizenReport>,message:string):void {
    this.pending.set(id); this.activeAction.set(id); this.actionError.set(''); this.success.set('');
    request.pipe(takeUntilDestroyed(this.destroyRef),finalize(() => this.pending.set(null))).subscribe({
      next:report => { this.events.set(report.id,report); this.upsert(report); this.success.set(message); },
      error:() => this.actionError.set('No pudimos actualizar el reporte. Actualiza la lista e intenta de nuevo.'),
    });
  }
  private upsert(report:CitizenReport):void { this.reports.update(items => [report,...items.filter(item => item.id!==report.id)]); }
}
