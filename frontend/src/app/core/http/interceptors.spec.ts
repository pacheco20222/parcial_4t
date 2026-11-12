import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { authInterceptor } from './auth.interceptor';
import { csrfInterceptor } from './csrf.interceptor';
import { AuthService } from '../auth/auth.service';
import { LiveService } from '../live/live.service';
describe('HTTP interceptors', () => {
  let http: HttpClient;
  let controller: HttpTestingController;
  const navigate = vi.fn().mockResolvedValue(true);
  beforeEach(() => {
    navigate.mockClear();
    TestBed.configureTestingModule({providers: [provideHttpClient(withInterceptors([csrfInterceptor, authInterceptor])), provideHttpClientTesting(), {provide: Router, useValue: {url: '/ops/panel', navigate}}, {provide: LiveService, useValue: {restart: vi.fn()}}]});
    http = TestBed.inject(HttpClient); controller = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    try { controller.verify(); }
    finally { vi.unstubAllGlobals(); }
  });
  it('adds CSRF header only to unsafe methods', () => {
    for (const method of ['GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE']) {
      http.request(method, '/test').subscribe();
      const request = controller.expectOne('/test');
      expect(request.request.headers.get('X-Requested-With')).toBe(['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) ? 'XMLHttpRequest' : null);
      request.flush(null);
    }
  });
  it('shares one refresh across concurrent 401s then retries both requests', () => {
    const results: string[] = [];
    http.get<string>('/first').subscribe(value => results.push(value)); http.get<string>('/second').subscribe(value => results.push(value));
    controller.expectOne('/first').flush(null, {status: 401, statusText: 'Unauthorized'});
    controller.expectOne('/second').flush(null, {status: 401, statusText: 'Unauthorized'});
    const refresh = controller.expectOne('/api/ops/auth/refresh');
    expect(refresh.request.method).toBe('POST'); expect(refresh.request.headers.get('X-Requested-With')).toBe('XMLHttpRequest'); refresh.flush(null);
    controller.expectOne('/first').flush('one'); controller.expectOne('/second').flush('two'); expect(results).toEqual(['one', 'two']);
  });
  it('retries a 401 without rotating again when another tab refreshed first', async () => {
    vi.stubGlobal('navigator', {locks: {request: (_name: string, callback: () => Promise<void>) => callback()}});
    const result = vi.fn(); http.get('/private').subscribe(result);
    controller.expectOne('/private').flush(null, {status: 401, statusText: 'Unauthorized'});
    controller.expectOne('/api/ops/auth/me').flush({id: '1', roles: ['Operator']});
    await vi.waitFor(() => {
      controller.expectOne('/private').flush('retried');
    });
    expect(result).toHaveBeenCalledWith('retried');
    controller.expectNone('/api/ops/auth/refresh'); expect(navigate).not.toHaveBeenCalled();
  });
  it('clears session and redirects with returnUrl after refresh fails', () => {
    const auth = TestBed.inject(AuthService); auth.me.set({id: '1', email: 'operator@example.test', roles: ['Operator'], mfaEnabled: false});
    const failed = vi.fn(); http.get('/private').subscribe({error: failed});
    controller.expectOne('/private').flush(null, {status: 401, statusText: 'Unauthorized'});
    controller.expectOne('/api/ops/auth/refresh').flush(null, {status: 401, statusText: 'Unauthorized'});
    expect(auth.me()).toBeNull(); expect(failed).toHaveBeenCalledOnce(); expect(navigate).toHaveBeenCalledWith(['/login'], {queryParams: {returnUrl: '/ops/panel'}});
  });
  it('excludes auth endpoints and never refreshes a retried request twice', () => {
    for (const path of ['login', 'refresh', 'me', 'mfa/verify']) {
      http.get(`/api/ops/auth/${path}`).subscribe({error: () => undefined}); controller.expectOne(`/api/ops/auth/${path}`).flush(null, {status: 401, statusText: 'Unauthorized'});
    }
    http.get('/private').subscribe({error: () => undefined}); controller.expectOne('/private').flush(null, {status: 401, statusText: 'Unauthorized'});
    controller.expectOne('/api/ops/auth/refresh').flush(null); controller.expectOne('/private').flush(null, {status: 401, statusText: 'Unauthorized'}); controller.expectNone('/api/ops/auth/refresh');
  });
});
