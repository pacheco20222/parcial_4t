import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { LiveService } from '../live/live.service';
import { Role } from '../api/models';
describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;
  const restart = vi.fn();
  beforeEach(() => {
    restart.mockClear(); TestBed.configureTestingModule({providers: [provideHttpClient(), provideHttpClientTesting(), {provide: LiveService, useValue: {restart}}]});
    auth = TestBed.inject(AuthService); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    try { http.verify(); }
    finally { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); }
  });
  it('honors Operator < Supervisor < Admin hierarchy', () => {
    expect(auth.hasRole('Operator')).toBe(false);
    for (const [role, permissions] of [['Operator', [true, false, false]], ['Supervisor', [true, true, false]], ['Admin', [true, true, true]]] as const) {
      auth.me.set({id: '1', email: 'staff@example.test', roles: [role], mfaEnabled: false}); expect((['Operator', 'Supervisor', 'Admin'] as Role[]).map(min => auth.hasRole(min))).toEqual(permissions);
    }
  });
  it('keeps MFA pending until verification and loads cookie-backed identity', () => {
    auth.login('staff@example.test', 'secret').subscribe(result => expect(result.mfaRequired).toBe(true)); http.expectOne('/api/ops/auth/login').flush({mfaRequired: true}); expect(auth.me()).toBeNull(); http.expectNone('/api/ops/auth/me');
    auth.verifyMfa('123456').subscribe(); const verify = http.expectOne('/api/ops/auth/mfa/verify'); expect(verify.request.body).toEqual({code: '123456'}); verify.flush(null);
    http.expectOne('/api/ops/auth/me').flush({id: '1', email: 'staff@example.test', roles: ['Admin'], mfaEnabled: true}); expect(auth.hasRole('Admin')).toBe(true); expect(restart).toHaveBeenCalledOnce();
  });
  it('treats /me 401 as anonymous', () => {
    const result = vi.fn(); auth.loadMe().subscribe(result); http.expectOne('/api/ops/auth/me').flush(null, {status: 401, statusText: 'Unauthorized'}); expect(result).toHaveBeenCalledWith(null);
  });
  it('checks identity inside the cross-tab lock and skips an already refreshed cookie', async () => {
    vi.stubGlobal('navigator', {locks: {request: (_name: string, callback: () => Promise<void>) => callback()}});
    const complete = vi.fn(); auth.refresh().subscribe(complete);
    http.expectNone('/api/ops/auth/refresh');
    http.expectOne('/api/ops/auth/me').flush({id: '1', roles: ['Operator']});
    await vi.waitFor(() => expect(complete).toHaveBeenCalledOnce());
    http.expectNone('/api/ops/auth/refresh');
  });
  it('serializes independent tabs and lets only the first rotate an expired cookie', async () => {
    let queue = Promise.resolve();
    vi.stubGlobal('navigator', {locks: {request: (name: string, callback: () => Promise<void>) => {
      expect(name).toBe('flood-auth-refresh');
      const result = queue.then(callback); queue = result.catch(() => undefined); return result;
    }}});
    const otherTab = TestBed.runInInjectionContext(() => new AuthService());
    const first = vi.fn(); const second = vi.fn();
    auth.refresh().subscribe(first); otherTab.refresh().subscribe(second);
    await Promise.resolve();
    http.expectOne('/api/ops/auth/me').flush(null, {status: 401, statusText: 'Unauthorized'});
    http.expectOne('/api/ops/auth/refresh').flush(null);
    await vi.waitFor(() => expect(first).toHaveBeenCalledOnce());
    http.expectOne('/api/ops/auth/me').flush({id: '1', roles: ['Operator']});
    await vi.waitFor(() => expect(second).toHaveBeenCalledOnce());
    http.expectNone('/api/ops/auth/refresh');
  });
  it('does not rotate cookies when the lock identity check fails with a server error', async () => {
    vi.stubGlobal('navigator', {locks: {request: (_name: string, callback: () => Promise<void>) => callback()}});
    const failed = vi.fn(); auth.refresh().subscribe({error: failed});
    http.expectOne('/api/ops/auth/me').flush(null, {status: 503, statusText: 'Unavailable'});
    await vi.waitFor(() => expect(failed).toHaveBeenCalledOnce());
    http.expectNone('/api/ops/auth/refresh');
  });
  it('keeps in-tab single-flight when Web Locks is unavailable', () => {
    vi.stubGlobal('navigator', {});
    const first = vi.fn(); const second = vi.fn();
    auth.refresh().subscribe(first); auth.refresh().subscribe(second);
    http.expectNone('/api/ops/auth/me');
    http.expectOne('/api/ops/auth/refresh').flush(null);
    expect(first).toHaveBeenCalledOnce(); expect(second).toHaveBeenCalledOnce();
  });
  it('uses the shared refresh path from the proactive timer with thirty-second jitter', () => {
    vi.useFakeTimers(); vi.spyOn(Math, 'random').mockReturnValue(0);
    vi.stubGlobal('navigator', {locks: {request: (_name: string, callback: () => Promise<void>) => callback()}});
    auth.loadMe().subscribe(); http.expectOne('/api/ops/auth/me').flush({id: '1', roles: ['Operator']});
    vi.advanceTimersByTime(12 * 60 * 1000 - 30001); http.expectNone('/api/ops/auth/me');
    vi.advanceTimersByTime(1);
    http.expectOne('/api/ops/auth/me').flush({id: '1', roles: ['Operator']});
    http.expectNone('/api/ops/auth/refresh'); auth.clear();
  });
});
