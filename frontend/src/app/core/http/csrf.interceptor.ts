import { HttpInterceptorFn } from '@angular/common/http';
export const csrfInterceptor: HttpInterceptorFn = (request, next) => next(
  ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method)
    ? request.clone({ setHeaders: { 'X-Requested-With': 'XMLHttpRequest' } })
    : request,
);
