import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { MfaService, mfaQrImage } from './mfa.service';
import { AuthService } from './auth.service';
import { LiveService } from '../live/live.service';

describe('MFA enrollment', () => {
  let service: MfaService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), { provide: LiveService, useValue: { restart: vi.fn() } }] });
    service = TestBed.inject(MfaService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('posts setup and creates a local SVG QR image without inline styles', () => {
    const uri = 'otpauth://totp/Flood:test?secret=EXAMPLE&issuer=Flood&digits=6';
    service.setup().subscribe(result => expect(result.otpauthUri).toBe(uri));
    const request = http.expectOne('/api/ops/auth/mfa/setup');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    request.flush({ otpauthUri: uri });
    const image = mfaQrImage(uri);
    expect(image.startsWith('data:image/svg+xml,')).toBe(true);
    const svg = decodeURIComponent(image.slice(image.indexOf(',') + 1));
    expect(svg).toContain('<svg');
    expect(svg).toContain('<path');
    expect(svg).not.toContain('style=');
    expect(svg).not.toContain(uri);
  });
  it('enables MFA then refreshes cookie-backed identity', () => {
    service.enable('123456').subscribe(me => expect(me?.mfaEnabled).toBe(true));
    const request = http.expectOne('/api/ops/auth/mfa/enable');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ code: '123456' });
    http.expectNone('/api/ops/auth/me');
    request.flush(null);
    http.expectOne('/api/ops/auth/me').flush({ id: '1', email: 'staff@example.test', roles: ['Operator'], mfaEnabled: true });
    expect(TestBed.inject(AuthService).me()?.mfaEnabled).toBe(true);
  });
  it('does not refresh identity after a rejected code', () => {
    const failed = vi.fn();
    service.enable('123456').subscribe({ error: failed });
    http.expectOne('/api/ops/auth/mfa/enable').flush({}, { status: 400, statusText: 'Bad Request' });
    expect(failed).toHaveBeenCalledOnce();
    http.expectNone('/api/ops/auth/me');
  });
});
