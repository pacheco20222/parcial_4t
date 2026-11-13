import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter, withComponentInputBinding, withNavigationErrorHandler } from '@angular/router';
import { routes } from './app.routes';
import { authInterceptor } from './core/http/auth.interceptor';
import { csrfInterceptor } from './core/http/csrf.interceptor';
import { handleChunkNavigationError } from './chunk-recovery';
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding(), withNavigationErrorHandler(handleChunkNavigationError)),
    provideHttpClient(withInterceptors([authInterceptor, csrfInterceptor])),
  ],
};
