import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, defer, finalize, firstValueFrom, from, map, of, shareReplay, switchMap, tap, throwError } from 'rxjs';
import { Me, Role } from '../api/models';
import { LiveService } from '../live/live.service';
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly live = inject(LiveService);
  readonly me = signal<Me | null>(null);
  readonly roles = computed(() => this.me()?.roles ?? []);
  private refreshRequest: Observable<void> | undefined;
  private meRequest: Observable<Me | null> | undefined;
  private timer: ReturnType<typeof setInterval> | undefined;
  private loaded = false;
  constructor() { inject(DestroyRef).onDestroy(() => clearInterval(this.timer)); }
  hasRole(min: Role): boolean {
    const ranks: Record<Role, number> = { Operator: 0, Supervisor: 1, Admin: 2 };
    return this.roles().some(role => ranks[role] >= ranks[min]);
  }
  login(email: string, password: string): Observable<{mfaRequired: boolean}> {
    return this.http.post<{mfaRequired: boolean}>('/api/ops/auth/login', { email, password }).pipe(
      switchMap(result => result.mfaRequired ? of(result) : this.loadMe(true).pipe(map(() => result))),
    );
  }
  verifyMfa(code: string): Observable<Me | null> {
    return this.http.post<void>('/api/ops/auth/mfa/verify', { code }).pipe(switchMap(() => this.loadMe(true)));
  }
  logout(): Observable<void> {
    return this.http.post<void>('/api/ops/auth/logout', {}).pipe(tap(() => this.clear()));
  }
  loadMe(force = false): Observable<Me | null> {
    if (this.meRequest) return this.meRequest;
    if (this.loaded && !force) return of(this.me());
    this.meRequest = this.http.get<Me>('/api/ops/auth/me').pipe(
      tap(me => { this.loaded = true; this.setSession(me); }),
      catchError((error: HttpErrorResponse) => {
        if (error.status !== 401) return throwError(() => error);
        this.loaded = true; this.clear(); return of(null);
      }),
      finalize(() => { this.meRequest = undefined; }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    return this.meRequest;
  }
  refresh(): Observable<void> {
    if (!this.refreshRequest) {
      this.refreshRequest = defer(() => {
        if (typeof navigator === 'undefined' || !navigator.locks) {
          return this.http.post<void>('/api/ops/auth/refresh', {});
        }
        return from(navigator.locks.request('flood-auth-refresh', () => firstValueFrom(
          this.http.get<Me>('/api/ops/auth/me').pipe(
            map(() => undefined),
            catchError((error: HttpErrorResponse) => error.status === 401
              ? this.http.post<void>('/api/ops/auth/refresh', {})
              : throwError(() => error)),
          ),
        )));
      }).pipe(
        finalize(() => { this.refreshRequest = undefined; }),
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    }
    return this.refreshRequest;
  }
  clear(): void { this.setSession(null); this.loaded = true; }
  private setSession(me: Me | null): void {
    const changed = this.me()?.id !== me?.id;
    this.me.set(me);
    clearInterval(this.timer);
    if (me) this.timer = setInterval(() => this.refresh().subscribe({error: () => this.clear()}), 12 * 60 * 1000 + (Math.random() * 60 - 30) * 1000);
    if (changed) this.live.restart();
  }
}
