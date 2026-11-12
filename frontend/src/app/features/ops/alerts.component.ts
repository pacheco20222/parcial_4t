import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Alert, PointStatus } from '../../core/api/models';
import { PointsStore } from '../../core/state/points.store';
import { AlertsStore } from '../../core/state/alerts.store';
import { LiveService } from '../../core/live/live.service';
import { AuthService } from '../../core/auth/auth.service';
import { alertLevelLabel, alertStatusLabel, displayText, pointLabel } from '../../core/state/labels';
import { formatDepth } from '../../core/state/format';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-alerts', imports:[FormsModule, RouterLink, DatePipe, IconComponent],
  templateUrl:'./alerts.component.html', styleUrl:'./views.scss', changeDetection:ChangeDetectionStrategy.OnPush,
})
export class AlertsComponent {
  private readonly http=inject(HttpClient);
  private readonly route=inject(ActivatedRoute);
  private readonly destroyRef=inject(DestroyRef);
  private readonly live=inject(LiveService);
  private readonly shared=inject(AlertsStore);
  readonly auth=inject(AuthService);
  readonly points=inject(PointsStore);
  readonly items=signal<Alert[]>([]);
  readonly loading=signal(false);
  readonly error=signal('');
  readonly feedback=signal('');
  readonly pending=signal(new Set<string>());
  readonly actionErrors=signal<Record<string,string>>({});
  readonly offset=signal(0);
  readonly hasNext=signal(false);
  readonly level=signal('');
  readonly visible=computed(()=>this.items().filter(a=>!this.level()||a.level===this.level()));
  readonly pointLabel=pointLabel;
  readonly alertLevelLabel=alertLevelLabel;
  readonly alertStatusLabel=alertStatusLabel;
  readonly displayText=displayText;
  readonly formatDepth=formatDepth;
  status='Open';
  pointId='';
  private generation=0;
  private readonly events=new Map<string,Alert>();
  constructor() {
    this.pointId=this.route.snapshot.queryParamMap.get('pointId') ?? '';
    this.live.alert$.pipe(takeUntilDestroyed()).subscribe(event=>{
      this.events.set(event.id,event);
      // A new event belongs on the newest page; existing rows update on any page.
      if(this.offset()===0 || this.items().some(a=>a.id===event.id)) this.merge(event);
    });
    this.live.reconnected$.pipe(takeUntilDestroyed()).subscribe(()=>this.reload());
    this.reload();
  }
  shape(level:string):PointStatus { return level==='DataGap'?'NoData':level==='Alert'?'Alert':'Watch'; }
  filtersChanged():void { this.offset.set(0); this.reload(); }
  changePage(direction:number):void { this.offset.update(v=>Math.max(0,v+direction*50)); this.reload(); }
  reload():void {
    const generation=++this.generation;
    this.events.clear(); this.loading.set(true); this.error.set('');
    let params=new HttpParams().set('limit',50).set('offset',this.offset());
    if(this.status) params=params.set('status',this.status);
    if(this.pointId) params=params.set('pointId',this.pointId);
    this.http.get<Alert[]>('/api/ops/alerts',{params}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next:items=>{
        if(generation!==this.generation)return;
        this.hasNext.set(items.length===50);
        const merged=new Map(items.map(a=>[a.id,a]));
        this.events.forEach((event,id)=>{if(this.offset()===0||merged.has(id))merged.set(id,event);});
        this.items.set([...merged.values()].filter(a=>this.matches(a)).sort((a,b)=>b.openedAt.localeCompare(a.openedAt)).slice(0,50));
        this.loading.set(false);
      },
      error:()=>{if(generation!==this.generation)return;this.loading.set(false);this.error.set('No pudimos cargar las alertas. Intenta de nuevo.');},
    });
  }
  close(alert:Alert):void {
    if(!this.auth.hasRole('Operator')||alert.status!=='Open'||this.pending().has(alert.id))return;
    this.pending.update(ids=>new Set([...ids,alert.id]));
    this.actionErrors.update(errors=>({...errors,[alert.id]:''})); this.feedback.set('');
    this.http.patch<Alert>(`/api/ops/alerts/${encodeURIComponent(alert.id)}`,{status:'Closed'}).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next:closed=>{this.events.set(closed.id,closed);this.merge(closed);this.finish(alert.id);this.feedback.set('Alerta cerrada.');this.shared.reload();},
      error:()=>{this.finish(alert.id);this.actionErrors.update(errors=>({...errors,[alert.id]:'No se pudo cerrar la alerta. Intenta de nuevo.'}));},
    });
  }
  private finish(id:string):void {this.pending.update(ids=>{const next=new Set(ids);next.delete(id);return next;});}
  private matches(alert:Alert):boolean {return (!this.status||alert.status===this.status)&&(!this.pointId||alert.pointId===this.pointId);}
  private merge(alert:Alert):void {
    this.items.update(items=>{
      const rows=items.filter(a=>a.id!==alert.id);
      return (this.matches(alert)?[alert,...rows]:rows).sort((a,b)=>b.openedAt.localeCompare(a.openedAt)).slice(0,50);
    });
  }
}
