import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';
import { IconComponent } from '../../shared/icon.component';
import { StatusBandComponent } from '../../shared/status-band.component';

@Component({
  selector: 'app-ops-shell', imports: [RouterLink, RouterLinkActive, RouterOutlet, IconComponent, StatusBandComponent],
  template: `
    <header class="ops-header">
      <a routerLink="/ops/panel" class="wordmark"><span class="brand-mark"></span>Alerta Pluvial Mérida</a>
      <button class="menu-button" type="button" [attr.aria-expanded]="menuOpen()" aria-controls="ops-nav" (click)="menuOpen.set(!menuOpen())"><app-icon [name]="menuOpen() ? 'close' : 'menu'" /><span>Menú</span></button>
      <nav id="ops-nav" aria-label="Navegación de operaciones" [class.open]="menuOpen()">
        @for (link of links; track link.path) { <a [routerLink]="link.path" routerLinkActive="active" ariaCurrentWhenActive="page" (click)="menuOpen.set(false)">{{ link.label }}</a> }
        @if (auth.hasRole('Admin')) {
          <details class="admin-menu"><summary>Admin</summary><div><a routerLink="/ops/admin/usuarios" (click)="menuOpen.set(false)">Usuarios</a><a routerLink="/ops/admin/auditoria" (click)="menuOpen.set(false)">Auditoría</a></div></details>
          <a href="/soc/" target="_blank" rel="noopener noreferrer">SOC <app-icon name="external" /><span class="sr-only">(abre una pestaña nueva)</span></a>
        }
      <div class="session"><a class="user-chip" routerLink="/ops/cuenta"><span>Mi cuenta · {{ auth.me()?.email }}</span><b>{{ roleName() }}</b></a><button class="logout" type="button" (click)="logout()" [disabled]="loggingOut()" aria-label="Cerrar sesión"><app-icon name="logout" /></button></div>
      </nav>
    </header>
    @if (logoutError()) { <p class="logout-error">No se pudo cerrar sesión. Intenta de nuevo.</p> }
    <app-status-band /><router-outlet />`,
  styleUrl: './ops-shell.component.scss', changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OpsShellComponent {
  readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly menuOpen = signal(false);
  readonly loggingOut = signal(false);
  readonly logoutError = signal(false);
  readonly links = [
    { path: '/ops/panel', label: 'Panel' }, { path: '/ops/mapa', label: 'Mapa' },
    { path: '/ops/alertas', label: 'Alertas' }, { path: '/ops/ordenes', label: 'Órdenes' },
    { path: '/ops/reportes', label: 'Reportes' }, { path: '/ops/cuadrillas', label: 'Cuadrillas' },
  ];
  roleName(): string { return this.auth.hasRole('Admin') ? 'Administrador' : this.auth.hasRole('Supervisor') ? 'Supervisor' : 'Operador'; }
  logout(): void {
    this.loggingOut.set(true);
    this.logoutError.set(false);
    this.auth.logout().subscribe({ next: () => { this.loggingOut.set(false); void this.router.navigateByUrl('/login'); }, error: () => { this.loggingOut.set(false); this.logoutError.set(true); } });
  }
}
