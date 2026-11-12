import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../auth/auth.service';
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const excluded = /^\/api\/ops\/auth\/(login|refresh|me|mfa)(\/|\?|$)/.test(request.url);
  return next(request).pipe(catchError((error: HttpErrorResponse) => {
    if (error.status !== 401 || excluded) return throwError(() => error);
    return auth.refresh().pipe(
      catchError((refreshError: HttpErrorResponse) => {
        auth.clear();
        void router.navigate(['/login'], { queryParams: { returnUrl: router.url } });
        return throwError(() => refreshError);
      }),
      switchMap(() => next(request)),
    );
  }));
};
