import { ChangeDetectionStrategy, Component, ElementRef, Injector, afterNextRender, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-login', imports: [FormsModule, RouterLink],
  template: `
    <main class="login-page"><a class="wordmark" routerLink="/">Alerta Pluvial Mérida</a>
    <section class="login-form"><h1>Acceso para personal</h1>
    @if (mfa()) { <p>Ingresa el código de tu aplicación de autenticación.</p> }
    @else { <p>Inicia sesión para supervisar los puntos de monitoreo.</p> }
    <form (ngSubmit)="submit()" novalidate>
      @if (!mfa()) {
        <label for="email">Correo electrónico</label><input id="email" name="email" type="email" autocomplete="username" [(ngModel)]="email" required [attr.aria-invalid]="submitted() && !validEmail()" aria-describedby="email-error" />
        @if (submitted() && !validEmail()) { <p id="email-error" class="error">Ingresa un correo electrónico válido.</p> }
        <label for="password">Contraseña</label><input id="password" name="password" type="password" autocomplete="current-password" [(ngModel)]="password" required [attr.aria-invalid]="submitted() && !password" aria-describedby="password-error" />
        @if (submitted() && !password) { <p id="password-error" class="error">Ingresa tu contraseña.</p> }
      } @else {
        <label for="code">Código de verificación</label><input #mfaInput id="code" name="code" type="text" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" [(ngModel)]="code" required [attr.aria-invalid]="submitted() && !validCode()" aria-describedby="code-error" />
        @if (submitted() && !validCode()) { <p id="code-error" class="error">Ingresa los seis dígitos del código.</p> }
      }
      @if (error()) { <p #feedback tabindex="-1" class="error">{{ error() }}</p> }
      <button type="submit" [disabled]="busy()">{{ busy() ? 'Verificando…' : mfa() ? 'Verificar código' : 'Iniciar sesión' }}</button>
    </form><a class="back" routerLink="/">Volver al estado público</a></section></main>`,
  styles: `:host{display:block}.login-page{min-height:75dvh;display:flex;flex-direction:column;align-items:center;padding:48px 20px}.wordmark{font:700 28px 'Barlow Condensed',sans-serif;color:var(--ink);text-decoration:none;margin-bottom:32px}.login-form{width:100%;max-width:420px;padding:28px;border:1px solid var(--line);background:var(--card)}h1{font-size:30px;margin:0}p{margin:12px 0 20px}form{display:flex;flex-direction:column;gap:8px}label{font-weight:600;margin-top:12px}input{font:inherit;padding:12px;border:1px solid var(--line);width:100%;background:var(--card);color:var(--ink)}button{margin-top:20px;padding:12px;background:var(--ink);color:var(--card);border:1px solid var(--ink);font:600 16px Barlow,sans-serif}button:disabled{opacity:.6}.error{color:var(--alert-text);margin:0}.back{display:inline-block;margin-top:24px;color:var(--ink)}`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  private readonly auth = inject(AuthService);
  private readonly injector = inject(Injector);
  private readonly feedback = viewChild<ElementRef<HTMLElement>>('feedback');
  private readonly mfaInput = viewChild<ElementRef<HTMLInputElement>>('mfaInput');
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly mfa = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly submitted = signal(false);
  email = '';
  password = '';
  code = '';
  validEmail(): boolean { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email); }
  validCode(): boolean { return /^\d{6}$/.test(this.code); }
  submit(): void {
    this.submitted.set(true);
    if (this.busy() || (this.mfa() ? !this.validCode() : !this.validEmail() || !this.password)) return;
    this.busy.set(true);
    this.error.set('');
    if (this.mfa()) {
      this.auth.verifyMfa(this.code).pipe(finalize(() => this.busy.set(false))).subscribe({ next: () => this.finish(), error: () => this.fail() });
    } else {
      this.auth.login(this.email, this.password).pipe(finalize(() => this.busy.set(false))).subscribe({
        next: result => {
          this.password = '';
          if (result.mfaRequired) {
            this.mfa.set(true); this.submitted.set(false);
            afterNextRender(() => this.mfaInput()?.nativeElement.focus(), { injector: this.injector });
          }
          else this.finish();
        }, error: () => this.fail(),
      });
    }
  }
  private finish(): void {
    const target = this.route.snapshot.queryParamMap.get('returnUrl');
    void this.router.navigateByUrl(target?.startsWith('/') && !target.startsWith('//') && !target.startsWith('/login') ? target : '/ops');
  }
  private fail(): void {
    this.error.set('No se pudo iniciar sesión. Revisa tus datos e intenta de nuevo.');
    afterNextRender(() => this.feedback()?.nativeElement.focus(), { injector: this.injector });
  }
}
