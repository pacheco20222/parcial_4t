import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { Crew } from '../../core/api/models';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-crews', imports: [FormsModule, IconComponent],
  template: `<main class="view"><header class="view-header"><h1>Cuadrillas</h1></header>
    @if (auth.hasRole('Supervisor')) {
      <section aria-labelledby="create-crew"><h2 id="create-crew">Crear cuadrilla</h2>
        <form class="form-grid" (ngSubmit)="create()" novalidate>
          <label for="crew-name">Nombre<input id="crew-name" name="name" [(ngModel)]="name" maxlength="100" required [attr.aria-invalid]="submitted() && !name.trim()" /></label>
          <label for="crew-zone">Zona<input id="crew-zone" name="zone" [(ngModel)]="zone" maxlength="100" required [attr.aria-invalid]="submitted() && !zone.trim()" /></label>
          <button type="submit" [disabled]="saving()">{{ saving() ? 'Creando…' : 'Crear cuadrilla' }}</button>
        </form>
        @if (submitted() && (!name.trim() || !zone.trim()) && !feedback()) { <p class="error" role="alert">Escribe el nombre y la zona de la cuadrilla.</p> }
        @if (saveError()) { <p class="error" role="alert">{{ saveError() }}</p> }
        <p class="feedback" role="status">{{ feedback() }}</p>
      </section>
    }
    <section aria-labelledby="crew-list"><h2 id="crew-list">Cuadrillas registradas</h2>
      @if (loading()) { <div class="skeleton" aria-label="Cargando cuadrillas" aria-busy="true"></div> }
      @else if (error()) { <p class="error" role="alert">{{ error() }}</p><button type="button" (click)="load()">Reintentar</button> }
      @else if (!crews().length) { <p class="empty">Sin cuadrillas registradas. Un supervisor puede crear la primera cuadrilla.</p> }
      @else { <div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Nombre</th><th scope="col">Zona</th><th scope="col">Disponibilidad</th></tr></thead><tbody>
        @for (crew of crews(); track crew.id) { <tr><td data-label="Nombre">{{ crew.name }}</td><td data-label="Zona">{{ crew.zone }}</td><td data-label="Disponibilidad"><span class="crew-state" [class.available]="crew.available"><app-icon [name]="crew.available ? 'Normal' : 'NoData'" />{{ crew.available ? 'Disponible' : 'No disponible' }}</span></td></tr> }
      </tbody></table></div> }
      <nav class="pagination" aria-label="Páginas de cuadrillas"><button type="button" (click)="page(-1)" [disabled]="loading() || offset() === 0">Anterior</button><span>Página {{ offset() / 50 + 1 }}</span><button type="button" (click)="page(1)" [disabled]="loading() || crews().length < 50">Siguiente</button></nav>
    </section></main>`,
  styleUrls: ['./views.scss', './crews.component.scss'], changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CrewsComponent {
  readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly crews = signal<Crew[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly submitted = signal(false);
  readonly offset = signal(0);
  readonly error = signal('');
  readonly saveError = signal('');
  readonly feedback = signal('');
  name = ''; zone = '';
  constructor() { this.load(); }
  load(): void {
    this.loading.set(true); this.error.set('');
    this.http.get<Crew[]>('/api/ops/crews', { params: { limit: 50, offset: this.offset() } }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({ next: items => this.crews.set(items), error: () => this.error.set('No pudimos cargar las cuadrillas. Intenta de nuevo.') });
  }
  page(direction: number): void { if (this.loading()) return; this.offset.update(value => Math.max(0, value + direction * 50)); this.load(); }
  create(): void {
    this.submitted.set(true); this.feedback.set(''); this.saveError.set('');
    if (this.saving() || !this.auth.hasRole('Supervisor') || !this.name.trim() || !this.zone.trim()) return;
    this.saving.set(true);
    this.http.post<Crew>('/api/ops/crews', { name: this.name.trim(), zone: this.zone.trim() }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: () => { this.name = ''; this.zone = ''; this.submitted.set(false); this.feedback.set('Cuadrilla creada.'); this.offset.set(0); this.load(); },
      error: () => this.saveError.set('No pudimos crear la cuadrilla. Revisa los datos e intenta de nuevo.'),
    });
  }
}
