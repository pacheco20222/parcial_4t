import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Crew, OrderStatus, Priority, WorkOrder } from '../../core/api/models';
import { AuthService } from '../../core/auth/auth.service';
import { PointsStore } from '../../core/state/points.store';
import { WorkOrderFilters, WorkOrdersStore } from '../../core/state/work-orders.store';
import { WorkOrderActions, canTransition, slaFraction, slaReference } from '../../core/state/work-order-actions';
import { displayText, orderStatusLabel, pointLabel, priorityLabel } from '../../core/state/labels';
import { formatSla } from '../../core/state/format';
import { OrderPriorityComponent, OrderStateComponent } from '../../shared/order-indicators.component';
import { compareOpenWorkOrders } from '../../core/state/work-order-ordering';
@Component({
  selector:'app-work-orders', imports:[FormsModule, RouterLink, DatePipe, NgTemplateOutlet, OrderPriorityComponent, OrderStateComponent], providers:[WorkOrderActions,WorkOrdersStore],
  templateUrl:'./work-orders.component.html', styleUrls:['./views.scss','./work-orders.component.scss'],changeDetection:ChangeDetectionStrategy.OnPush,
})
export class WorkOrdersComponent {
  readonly auth=inject(AuthService);
  readonly points=inject(PointsStore);
  readonly store=inject(WorkOrdersStore);
  readonly actions=inject(WorkOrderActions);
  private readonly http=inject(HttpClient);
  private readonly destroyRef=inject(DestroyRef);
  readonly crews=signal<Crew[]>([]);
  readonly availableCrews=computed(() => this.crews().filter(crew => crew.available));
  readonly crewsLoading=signal(false);
  readonly crewsError=signal('');
  readonly moreCrews=signal(false);
  readonly priority=signal('');
  readonly pointId=signal(inject(ActivatedRoute).snapshot.queryParamMap.get('pointId') ?? '');
  readonly overdueOnly=signal(false);
  readonly mobileStatus=signal<OrderStatus>('Open');
  readonly compact=signal(false);
  readonly activeAction=signal('');
  readonly columns:OrderStatus[]=['Open','Assigned','InProgress','Resolved'];
  readonly priorities:Priority[]=['Critical','High','Medium','Low'];
  readonly selectedCrew:Record<string,string>={};
  readonly cancelReason:Record<string,string>={};
  readonly pointLabel=pointLabel;
  readonly orderStatusLabel=orderStatusLabel;
  readonly priorityLabel=priorityLabel;
  readonly displayText=displayText;
  readonly formatSla=formatSla;
  readonly slaFraction=slaFraction;
  slaTime(order:WorkOrder):number|null { return slaReference(order,this.points.now()); }
  slaSummary(order:WorkOrder):string { const at=this.slaTime(order); if(at===null) return 'Sin plazo disponible'; return ['Resolved','Closed'].includes(order.status) ? `Plazo al ${order.resolvedAt?'resolver':'cerrar'}: ${Math.round(slaFraction(order,at)*100)} % disponible` : formatSla(order.slaDueAt,at); }
  newPoint=''; newTitle=''; newPriority:Priority='Medium';
  readonly createError=signal('');
  readonly filtered=computed(() => this.store.orders().filter(order => (!this.priority() || order.priority===this.priority()) && (!this.pointId() || order.pointId===this.pointId()) && (!this.overdueOnly() || this.overdue(order))));
  readonly closed=computed(() => this.filtered().filter(order => ['Closed','Cancelled'].includes(order.status)));
  constructor() {
    if(typeof matchMedia==='function') {
      const media=matchMedia('(max-width:640px)');
      this.compact.set(media.matches);
      const update=(event:MediaQueryListEvent) => this.compact.set(event.matches);
      media.addEventListener('change',update);
      this.destroyRef.onDestroy(() => media.removeEventListener('change',update));
    }
    if (this.auth.hasRole('Supervisor')) this.loadCrews(); if(this.pointId()) this.applyFilters();
  }
  applyFilters():void { const filters:WorkOrderFilters={}; if(this.priority()) filters.priority=this.priority() as Priority; if(this.pointId()) filters.pointId=this.pointId(); if(this.overdueOnly()) filters.overdue=true; this.store.reload(filters); }
  readonly detachedError=computed(() => { const order=this.filtered().find(item => item.id===this.activeAction()); return !!this.actions.error() && this.activeAction()!=='create' && (!order || order.status!==this.mobileStatus()); });
  rows(status:OrderStatus):WorkOrder[] { return this.filtered().filter(order => order.status===status).sort((a,b) => compareOpenWorkOrders(a,b,this.points.now())); }
  pointName(id:string):string { const point=this.points.points().find(item => item.id===id); return point ? pointLabel(point) : id; }
  crewName(id:string|null):string { return id ? this.crews().find(crew => crew.id===id)?.name ?? `Cuadrilla ${id}` : 'Sin asignar'; }
  overdue(order:WorkOrder):boolean { return !['Resolved','Closed','Cancelled'].includes(order.status) && Date.parse(order.slaDueAt)<this.points.now(); }
  can(order:WorkOrder,to:OrderStatus):boolean { return this.auth.hasRole('Operator') && canTransition(order.status,to,this.auth.hasRole('Supervisor')); }
  assign(order:WorkOrder):void { this.activeAction.set(order.id); this.actions.assign(order.id,this.selectedCrew[order.id]); }
  transition(order:WorkOrder,to:OrderStatus):void { this.activeAction.set(order.id); this.actions.transition(order.id,to,this.cancelReason[order.id]); }
  create():void {
    this.createError.set('');
    if (!this.newPoint || !this.newTitle.trim() || this.newTitle.trim().length>200) { this.createError.set('Selecciona un punto y escribe un título de hasta 200 caracteres.'); return; }
    this.activeAction.set('create'); this.actions.create({pointId:this.newPoint,title:this.newTitle.trim(),priority:this.newPriority});
  }
  loadCrews(append=false):void {
    if (!this.auth.hasRole('Supervisor') || this.crewsLoading()) return;
    this.crewsLoading.set(true); this.crewsError.set('');
    this.http.get<Crew[]>('/api/ops/crews',{params:{limit:100,offset:append?this.crews().length:0}}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next:crews => { this.crews.set(append?[...this.crews(),...crews]:crews); this.moreCrews.set(crews.length===100); this.crewsLoading.set(false); },
      error:() => { this.crewsError.set('No pudimos cargar las cuadrillas. Intenta de nuevo.'); this.crewsLoading.set(false); },
    });
  }
}
