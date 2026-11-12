import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { PointsStore } from '../core/state/points.store';
import { LiveService } from '../core/live/live.service';
import { statusLabel, statusSentence } from '../core/state/format';
import { IconComponent } from './icon.component';
@Component({
  selector: 'app-status-band',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="band" [class]="'band status-' + points.worstStatus()">
    <strong class="tag"><app-icon [name]="points.worstStatus()"/>{{ label(points.worstStatus()) }}</strong>
    <p>{{ points.loading() && !points.points().length ? 'Cargando puntos…' : points.error() && !points.points().length ? 'No se pudieron cargar los puntos. Reintenta desde la lista.' : sentence() }}</p>
    <span class="live"><span class="connection-dot" [class.connected]="live.state() === 'connected'"></span>{{ connectionLabel() }}</span>
  </div>`,
  styles: `:host{display:block}.band{min-height:56px;display:flex;align-items:center;gap:16px;padding:8px 24px;transition:background-color 180ms cubic-bezier(.16,1,.3,1)}.tag{display:flex;align-items:center;gap:8px;font:800 28px/32px var(--font-heading);text-transform:uppercase;letter-spacing:.04em}.band p{flex:1;margin:0;font-size:18px;font-weight:600}.live{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;white-space:nowrap;border:1px solid currentColor;padding:7px 10px}.connection-dot{width:8px;height:8px;border:1px solid currentColor}.connection-dot.connected{border-radius:50%;background:currentColor}@media(max-width:767px){.band{padding:12px 16px;gap:8px;flex-wrap:wrap}.tag{font-size:24px}.band p{order:3;flex-basis:100%;font-size:16px}.live{margin-left:auto;font-size:12px}}@media(prefers-reduced-motion:reduce){.band{transition:none}}`,
})
export class StatusBandComponent {
  protected readonly points = inject(PointsStore);
  protected readonly live = inject(LiveService);
  protected readonly label = statusLabel;
  protected readonly sentence = computed(() => statusSentence(this.points.points(), this.points.now()));
  protected readonly connectionLabel = computed(() => ({ connecting:'Conectando…', connected:'En vivo', reconnecting:'Reconectando…', disconnected:'Sin conexión' })[this.live.state()]);
}
