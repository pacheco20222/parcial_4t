import { afterNextRender, ChangeDetectionStrategy, Component, DestroyRef, effect, ElementRef, inject, input, output, viewChild } from '@angular/core';
import * as L from 'leaflet';
import { PublicPoint } from '../core/api/models';
import { pointLabel } from '../core/state/labels';
import { formatDepth, statusLabel } from '../core/state/format';

@Component({
  selector: 'app-map',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div #canvas class="map-canvas" role="region" aria-label="Mapa de puntos de monitoreo en Mérida"></div>
    <div class="map-legend" aria-label="Simbología de estados"><span class="legend-alert">Alerta</span><span class="legend-watch">Vigilancia</span><span class="legend-normal">Normal</span><span class="legend-nodata">Sin datos</span></div>`,
  styles: `:host{display:block;position:relative;min-height:360px;height:100%;border:1px solid var(--line);background:var(--ground)}.map-canvas{position:absolute;inset:0;height:100%;z-index:0}.map-legend{display:flex;flex-wrap:wrap;gap:8px 14px;position:absolute;bottom:30px;left:10px;right:10px;width:fit-content;z-index:400;background:var(--card);border:1px solid var(--line);padding:6px 10px;font-size:12px;font-weight:600}.map-legend span{display:flex;gap:5px;align-items:center}.map-legend span:before{content:'';width:10px;height:10px;background:var(--normal)}.legend-alert:before{background:var(--alert)!important;clip-path:polygon(50% 0,100% 100%,0 100%)}.legend-watch:before{background:var(--watch)!important;transform:rotate(45deg)}.legend-normal:before{border-radius:50%}.legend-nodata:before{background:var(--nodata)!important}`,
})
export class MapComponent {
  readonly points = input<PublicPoint[]>([]);
  readonly selectedId = input<string | null>(null);
  // Required public component API; this emits a point ID, not a DOM select event.
  // eslint-disable-next-line @angular-eslint/no-output-native
  readonly select = output<string>();
  private readonly canvas = viewChild.required<ElementRef<HTMLDivElement>>('canvas');
  private map?: L.Map;
  private readonly markers = new Map<string, { marker: L.Marker; status: string }>();
  private observer?: ResizeObserver;
  private fittedInitialPoints = false;
  constructor() {
    afterNextRender(() => {
      this.map = L.map(this.canvas().nativeElement, { zoomAnimation: false, fadeAnimation: false, markerZoomAnimation: false }).setView([20.97, -89.62], 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19,
      }).addTo(this.map);
      this.observer = new ResizeObserver(() => this.map?.invalidateSize());
      this.observer.observe(this.canvas().nativeElement);
      this.updateMarkers();
    });
    effect(() => { this.points(); this.selectedId(); this.updateMarkers(); });
    inject(DestroyRef).onDestroy(() => { this.observer?.disconnect(); this.map?.remove(); });
  }
  private updateMarkers(): void {
    if (!this.map) return;
    const points = this.points();
    if (points.length && !this.fittedInitialPoints) {
      this.map.fitBounds(L.latLngBounds(points.map(point => L.latLng(point.lat, point.lon))), { padding: [40, 40], maxZoom: 14, animate: false });
      this.fittedInitialPoints = true;
    }
    for (const [id, entry] of this.markers) {
      if (!points.some(point => point.id === id)) { entry.marker.remove(); this.markers.delete(id); }
    }
    for (const point of points) {
      const status = `${point.status}-${this.selectedId() === point.id}`;
      const icon = () => L.divIcon({ className: `point-marker marker-${point.status}${this.selectedId() === point.id ? ' selected' : ''}`, html: '<span class="marker-shape"></span>', iconSize: [32, 32], iconAnchor: [16, 16] });
      let entry = this.markers.get(point.id);
      if (!entry) {
        const marker = L.marker([point.lat, point.lon], { icon: icon(), keyboard: true, title: `${pointLabel(point)}`, alt: `${pointLabel(point)}: ${statusLabel(point.status)}` }).addTo(this.map);
        marker.on('click', () => this.select.emit(point.id));
        entry = { marker, status }; this.markers.set(point.id, entry);
      }
      entry.marker.setLatLng([point.lat, point.lon]);
      if (entry.status !== status) { entry.marker.setIcon(icon()); entry.status = status; }
      const text = document.createElement('span');
      text.textContent = `${pointLabel(point)} · ${statusLabel(point.status)} · ${point.status === 'NoData' || point.waterDepthCm === null ? 'sin datos' : formatDepth(point.waterDepthCm)}`;
      entry.marker.getElement()?.setAttribute('aria-label', text.textContent);
      const tooltip = entry.marker.getTooltip();
      if (tooltip) tooltip.setContent(text); else entry.marker.bindTooltip(text, { direction: 'top' });
    }
  }
}
