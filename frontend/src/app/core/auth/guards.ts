import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';
import { Role } from '../api/models';
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.loadMe().pipe(map(me => me ? true : router.createUrlTree(['/login'], {queryParams: {returnUrl: state.url}})), catchError(() => of(router.createUrlTree(['/login'], {queryParams: {returnUrl: state.url}}))));
};
export function roleGuard(min: Extract<Role, 'Supervisor' | 'Admin'>): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    return auth.loadMe().pipe(map(() => auth.hasRole(min) || router.createUrlTree(['/ops/panel'])));
  };
}
