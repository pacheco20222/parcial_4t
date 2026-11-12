import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';
import { Role, User } from '../../core/api/models';
import { roleLabel } from '../../core/state/labels';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-users', imports: [FormsModule, IconComponent],
  template: `<main class="view"><header class="view-header"><h1>Usuarios</h1></header>
    @if (auth.hasRole('Admin')) {
      <section aria-labelledby="create-user"><h2 id="create-user">Crear usuario</h2>
        <form class="form-grid" (ngSubmit)="create()" novalidate>
          <label for="user-email">Correo electrónico<input id="user-email" name="email" type="email" autocomplete="off" [(ngModel)]="email" maxlength="254" required [attr.aria-invalid]="submitted() && !validEmail()" aria-describedby="user-email-hint" /></label>
          <label for="user-password">Contraseña<input id="user-password" name="password" type="password" autocomplete="new-password" [(ngModel)]="password" minlength="12" maxlength="1024" required [attr.aria-invalid]="submitted() && password.length < 12" aria-describedby="password-hint" /></label>
          <label for="user-role">Rol<select id="user-role" name="role" [(ngModel)]="role">@for (item of roles; track item) { <option [value]="item">{{ roleLabel(item) }}</option> }</select></label>
          <button type="submit" [disabled]="saving()">{{ saving() ? 'Creando…' : 'Crear usuario' }}</button>
        </form>
        <p id="password-hint" [class.error]="submitted() && password.length < 12">La contraseña debe tener al menos 12 caracteres.</p>
        <p id="user-email-hint" [class.error]="submitted() && !validEmail()">Usa un correo electrónico válido para el acceso.</p>
        @if (saveError()) { <p class="error" role="alert">{{ saveError() }}</p> }
        <p class="feedback" role="status">{{ feedback() }}</p>
      </section>
    }
    <section aria-labelledby="users-list"><h2 id="users-list">Personal registrado</h2>
      @if (loading()) { <div class="skeleton" aria-label="Cargando usuarios" aria-busy="true"></div> }
      @else if (error()) { <p class="error" role="alert">{{ error() }}</p><button type="button" (click)="load()">Reintentar</button> }
      @else if (!users().length) { <p class="empty">Sin usuarios en esta página. Crea un usuario o vuelve a la página anterior.</p> }
      @else { <div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">Correo electrónico</th><th scope="col">Rol</th><th scope="col">MFA</th></tr></thead><tbody>
        @for (user of users(); track user.id) { <tr><td data-label="Correo electrónico">{{ user.email }}</td><td data-label="Rol">@for (item of user.roles; track item) { <span>{{ roleLabel(item) }} </span> }</td><td data-label="MFA"><span class="status"><app-icon [name]="user.mfaEnabled ? 'check' : 'close'" /> {{ user.mfaEnabled ? 'Activada' : 'Sin activar' }}</span></td></tr> }
      </tbody></table></div> }
      <nav class="pagination" aria-label="Páginas de usuarios"><button type="button" (click)="page(-1)" [disabled]="loading() || offset() === 0">Anterior</button><span>Página {{ offset() / 50 + 1 }}</span><button type="button" (click)="page(1)" [disabled]="loading() || users().length < 50">Siguiente</button></nav>
    </section></main>`,
  styleUrl: './views.scss', changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UsersComponent {
  readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly roleLabel = roleLabel;
  readonly roles: Role[] = ['Operator', 'Supervisor', 'Admin'];
  readonly users = signal<User[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly submitted = signal(false);
  readonly offset = signal(0);
  readonly error = signal('');
  readonly saveError = signal('');
  readonly feedback = signal('');
  email = ''; password = ''; role: Role = 'Operator';
  constructor() { this.load(); }
  validEmail(): boolean { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email.trim()); }
  load(): void {
    this.loading.set(true); this.error.set('');
    this.http.get<User[]>('/api/ops/users', { params: { limit: 50, offset: this.offset() } }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({ next: items => this.users.set(items), error: () => this.error.set('No pudimos cargar los usuarios. Intenta de nuevo.') });
  }
  page(direction: number): void { if (this.loading()) return; this.offset.update(value => Math.max(0, value + direction * 50)); this.load(); }
  create(): void {
    this.submitted.set(true); this.feedback.set(''); this.saveError.set('');
    if (this.saving() || !this.auth.hasRole('Admin') || !this.validEmail() || this.password.length < 12 || !this.roles.includes(this.role)) return;
    this.saving.set(true);
    this.http.post<unknown>('/api/ops/users', { email: this.email.trim(), password: this.password, role: this.role }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: () => { this.email = ''; this.password = ''; this.role = 'Operator'; this.submitted.set(false); this.feedback.set('Usuario creado.'); this.offset.set(0); this.load(); },
      error: () => { this.password = ''; this.saveError.set('No pudimos crear el usuario. Revisa el correo y escribe otra contraseña para intentar de nuevo.'); },
    });
  }
}
