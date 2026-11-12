import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { AuditEntry } from '../../core/api/models';

@Component({
  selector: 'app-audit', imports: [DatePipe],
  template: `<main class="view"><header class="view-header"><h1>Auditoría</h1><p>Registro de acciones del personal.</p></header>
    @if (loading()) { <div class="skeleton" aria-label="Cargando auditoría" aria-busy="true"></div> }
    @else if (error()) { <p class="error" role="alert">{{ error() }}</p><button type="button" (click)="load()">Reintentar</button> }
    @else if (!entries().length) { <p class="empty">Sin acciones en esta página. Las nuevas acciones del personal aparecerán aquí.</p> }
    @else { <div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Fecha y hora</th><th scope="col">Usuario</th><th scope="col">Acción</th><th scope="col">Entidad</th><th scope="col">IP</th></tr></thead><tbody>
      @for (entry of entries(); track entry.id) { <tr><td data-label="Fecha y hora">{{ entry.at | date:'dd/MM/yyyy HH:mm:ss' }}</td><td data-label="Usuario">{{ entry.userId ?? 'Sistema' }}</td><td data-label="Acción">{{ entry.action }}</td><td data-label="Entidad">{{ entry.entity }}</td><td data-label="IP">{{ entry.ip ?? 'No disponible' }}</td></tr> }
    </tbody></table></div> }
    <nav class="pagination" aria-label="Páginas de auditoría"><button type="button" (click)="page(-1)" [disabled]="loading() || offset() === 0">Anterior</button><span>Página {{ offset() / 50 + 1 }}</span><button type="button" (click)="page(1)" [disabled]="loading() || entries().length < 50">Siguiente</button></nav>
  </main>`,
  styleUrl: './views.scss', changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuditComponent {
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly entries = signal<AuditEntry[]>([]);
  readonly loading = signal(false);
  readonly offset = signal(0);
  readonly error = signal('');
  constructor() { this.load(); }
  load(): void {
    this.loading.set(true); this.error.set('');
    this.http.get<AuditEntry[]>('/api/ops/audit', { params: { limit: 50, offset: this.offset() } }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({ next: items => this.entries.set(items), error: () => this.error.set('No pudimos cargar la auditoría. Intenta de nuevo.') });
  }
  page(direction: number): void { if (this.loading()) return; this.offset.update(value => Math.max(0, value + direction * 50)); this.load(); }
}
