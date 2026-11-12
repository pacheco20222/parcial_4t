import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';
import { AuthService } from '../../core/auth/auth.service';
import { LoginComponent } from './login.component';

describe('LoginComponent', () => {
  function setup() {
    const auth = { login: vi.fn().mockReturnValue(of({ mfaRequired: true })), verifyMfa: vi.fn() };
    TestBed.configureTestingModule({ imports: [LoginComponent], providers: [provideRouter([]), { provide: AuthService, useValue: auth }] });
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    fixture.componentInstance.email = 'operator@example.test';
    fixture.componentInstance.password = 'example-password';
    return { fixture, auth };
  }
  it('moves focus to the TOTP input after MFA challenge', async () => {
    const { fixture } = setup();
    fixture.componentInstance.submit();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(document.activeElement?.id).toBe('code');
    expect(fixture.componentInstance.password).toBe('');
  });
  it('focuses a generic message when login fails', async () => {
    const { fixture, auth } = setup();
    auth.login.mockReturnValue(throwError(() => new Error('private detail')));
    fixture.componentInstance.submit();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(document.activeElement?.textContent).toContain('No se pudo iniciar sesión');
    expect(fixture.nativeElement.textContent).not.toContain('private detail');
  });
  it('does not send malformed email or empty credentials', () => {
    const { fixture, auth } = setup();
    fixture.componentInstance.email = 'invalid';
    fixture.componentInstance.submit();
    expect(auth.login).not.toHaveBeenCalled();
    expect(TestBed.inject(Router).url).toBe('/');
  });
});
