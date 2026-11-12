import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PublicPoint } from '../../core/api/models';
import { PointsStore } from '../../core/state/points.store';
import { formatAge, formatDepth, statusLabel } from '../../core/state/format';
import { pointLabel } from '../../core/state/labels';
import { MapComponent } from '../../shared/map.component';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector:'app-map-view', imports:[RouterLink,MapComponent,IconComponent], changeDetection:ChangeDetectionStrategy.OnPush,
  template:`<main class="view">
    <header class="view-header"><h1>Mapa de puntos</h1><a routerLink="/ops/panel">Volver al panel</a></header>
    <div class="map-layout"><app-map [points]="points.points()" [selectedId]="selectedId()" (select)="selectedId.set($event)" />
      <aside aria-label="Puntos de monitoreo">
        <h2>Selecciona un punto</h2>
        @if(points.loading()){<div class="skeleton" aria-busy="true">Cargando puntos…</div>}
        @if(points.error()){<p class="error">{{points.error()}} <button type="button" (click)="points.reload()">Reintentar</button></p>}
        <ul>@for(point of points.points();track point.id){<li><button type="button" class="point-choice" [attr.aria-pressed]="selectedId()===point.id" (click)="selectedId.set(point.id)"><strong>{{pointLabel(point)}}</strong><span [class]="'status status-'+point.status"><app-icon [name]="point.status"/>{{statusLabel(point.status)}}</span></button></li>}@empty{ @if(!points.loading()&&!points.error()){<li class="empty">Sin puntos disponibles. Vuelve al panel para consultar el estado de conexión.</li>}}</ul>
        @if(selected();as point){<section class="summary" aria-labelledby="selected-point"><h2 id="selected-point">{{pointLabel(point)}}</h2><p>{{point.zone}} · <span [class]="'status status-'+point.status"><app-icon [name]="point.status"/>{{statusLabel(point.status)}}</span></p><p>Tirante: <strong>{{depth(point)}}</strong></p><p>Actualizado {{formatAge(points.age(point))}}</p><a class="button" [routerLink]="['/ops/puntos',point.id]">Ver detalle del punto</a></section>}
      </aside>
    </div>
  </main>`,
  styleUrls:['./views.scss','./map-view.component.scss'],
})
export class MapViewComponent {
  readonly points=inject(PointsStore);
  readonly selectedId=signal<string|null>(null);
  readonly selected=computed(()=>this.points.points().find(point=>point.id===this.selectedId()));
  readonly pointLabel=pointLabel;
  readonly statusLabel=statusLabel;
  readonly formatAge=formatAge;
  depth(point:PublicPoint):string {return formatDepth(point.status === 'NoData' ? null : point.waterDepthCm);}
}
