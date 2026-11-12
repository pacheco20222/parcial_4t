import { ChangeDetectionStrategy, Component, ElementRef, Injector, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { PointsStore } from '../../core/state/points.store';
import { formatAge, formatDepth, statusLabel } from '../../core/state/format';
import { pointLabel } from '../../core/state/labels';
import { PublicPoint } from '../../core/api/models';
import { IconComponent } from '../../shared/icon.component';
import { MapComponent } from '../../shared/map.component';
import { StatusBandComponent } from '../../shared/status-band.component';

@Component({
  selector: 'app-citizen',
  imports: [FormsModule, RouterLink, IconComponent, MapComponent, StatusBandComponent],
  templateUrl: './citizen.component.html',
  styleUrl: './citizen.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CitizenComponent {
  readonly points = inject(PointsStore);
  private readonly http = inject(HttpClient);
  private readonly injector = inject(Injector);
  private readonly feedback = viewChild<ElementRef<HTMLElement>>('feedback');
  readonly selectedId = signal<string | null>(null);
  readonly sending = signal(false);
  readonly submitted = signal(false);
  readonly error = signal('');
  readonly folio = signal('');
  readonly statusLabel = statusLabel;
  readonly pointLabel = pointLabel;
  pointId = '';
  category = '';
  description = '';
  readonly categories = [
    { id: 'Encharcamiento', label: 'Encharcamiento' },
    { id: 'CalleIntransitable', label: 'Calle intransitable' },
    { id: 'DrenajeTapado', label: 'Drenaje tapado' },
    { id: 'Otro', label: 'Otro' },
  ];

  age(point: PublicPoint): string {
    return formatAge(point.updatedAt ? (this.points.now() - Date.parse(point.updatedAt)) / 1000 : null);
  }

  depth(point: PublicPoint): string {
    return formatDepth(point.status === 'NoData' ? null : point.waterDepthCm);
  }

  private focusFeedback(): void {
    afterNextRender(() => this.feedback()?.nativeElement.focus(), { injector: this.injector });
  }

  send(): void {
    this.submitted.set(true);
    if (!this.category || !this.description.trim() || this.description.length > 500 || this.sending()) return;
    this.error.set('');
    this.folio.set('');
    this.sending.set(true);
    this.http.post<{ folio: string }>('/api/ops/public/reports', {
      ...(this.pointId ? { pointId: this.pointId } : {}),
      category: this.category,
      description: this.description.trim(),
    }).pipe(finalize(() => this.sending.set(false))).subscribe({
      next: (report) => {
        this.folio.set(report.folio);
        this.description = '';
        this.submitted.set(false);
        this.focusFeedback();
      },
      error: (error: HttpErrorResponse) => {
        this.error.set(error.status === 429
          ? 'Llegaste al límite de reportes. Espera 10 minutos antes de intentar de nuevo.'
          : 'No se pudo enviar el reporte. Intenta de nuevo.');
        this.focusFeedback();
      },
    });
  }
}
