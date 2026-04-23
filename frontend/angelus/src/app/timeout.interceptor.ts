import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { throwError } from 'rxjs';
import { timeout, catchError } from 'rxjs/operators';

export const timeoutInterceptor: HttpInterceptorFn = (req, next) => {
  let timeoutSec = 30;
  try {
    const raw = localStorage.getItem('angelus_apiTimeout');
    if (raw !== null) {
      const parsed = Number(raw);
      if (Number.isFinite(parsed) && parsed > 0) {
        timeoutSec = parsed;
      }
    }
  } catch {
    // localStorage unavailable
  }

  return next(req).pipe(
    timeout(timeoutSec * 1000),
    catchError((error) => {
      if (error.name === 'TimeoutError') {
        return throwError(() => new HttpErrorResponse({
          error: { message: `请求超时（${timeoutSec}秒）` },
          status: 0,
          statusText: 'Request Timeout',
          url: req.url,
        }));
      }
      return throwError(() => error);
    })
  );
};
