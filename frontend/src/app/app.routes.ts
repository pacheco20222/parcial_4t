import { Routes } from '@angular/router';
import { authGuard, roleGuard } from './core/auth/guards';
export const routes: Routes = [
  { path: '', pathMatch: 'full', loadComponent: () => import('./features/citizen/citizen.component').then(m => m.CitizenComponent) },
  { path: 'login', loadComponent: () => import('./features/login/login.component').then(m => m.LoginComponent) },
  { path: 'ops', canActivate: [authGuard], loadComponent: () => import('./features/ops/ops-shell.component').then(m => m.OpsShellComponent), children: [
    { path: '', pathMatch: 'full', redirectTo: 'panel' },
    { path: 'panel', loadComponent: () => import('./features/ops/panel.component').then(m => m.PanelComponent) },
    { path: 'mapa', loadComponent: () => import('./features/ops/map-view.component').then(m => m.MapViewComponent) },
    { path: 'alertas', loadComponent: () => import('./features/ops/alerts.component').then(m => m.AlertsComponent) },
    { path: 'ordenes', loadComponent: () => import('./features/ops/work-orders.component').then(m => m.WorkOrdersComponent) },
    { path: 'reportes', loadComponent: () => import('./features/ops/reports.component').then(m => m.ReportsComponent) },
    { path: 'cuadrillas', loadComponent: () => import('./features/ops/crews.component').then(m => m.CrewsComponent) },
    { path: 'puntos/:id', loadComponent: () => import('./features/ops/point-detail.component').then(m => m.PointDetailComponent) },
    { path: 'cuenta', loadComponent: () => import('./features/ops/account.component').then(m => m.AccountComponent) },
    { path: 'admin/usuarios', canActivate: [roleGuard('Admin')], loadComponent: () => import('./features/ops/users.component').then(m => m.UsersComponent) },
    { path: 'admin/auditoria', canActivate: [roleGuard('Admin')], loadComponent: () => import('./features/ops/audit.component').then(m => m.AuditComponent) },
  ] },
  { path: '**', redirectTo: '' },
];
