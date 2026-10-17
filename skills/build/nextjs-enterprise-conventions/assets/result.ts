// lib/result.ts — typed Result and AppError. Pure; importable from any layer.
export type ErrorCode =
  | "VALIDATION_FAILED" | "AUTH_REQUIRED" | "AUTH_FORBIDDEN" | "NOT_FOUND"
  | "CONFLICT" | "RATE_LIMITED" | "UPSTREAM_FAILED" | "INTERNAL"
  | (string & {}); // domain codes, e.g. "INVOICE_ALREADY_PAID"

export type AppError = {
  code: ErrorCode;
  message: string;
  status: 400 | 401 | 403 | 404 | 409 | 422 | 429 | 500 | 502;
  fieldErrors?: Record<string, string[]>;
  cause?: unknown; // never serialized to the client
};

export type Result<T, E = AppError> = { ok: true; value: T } | { ok: false; error: E };

const STATUS: Record<string, AppError["status"]> = {
  VALIDATION_FAILED: 422, AUTH_REQUIRED: 401, AUTH_FORBIDDEN: 403, NOT_FOUND: 404,
  CONFLICT: 409, RATE_LIMITED: 429, UPSTREAM_FAILED: 502, INTERNAL: 500,
};

export const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });

export function fail<E extends AppError = AppError>(
  code: ErrorCode,
  message: string,
  extra: Partial<Omit<AppError, "code" | "message">> = {},
): Result<never, AppError> {
  return { ok: false, error: { code, message, status: extra.status ?? STATUS[code] ?? 400, ...extra } };
}

export const isOk = <T, E>(r: Result<T, E>): r is { ok: true; value: T } => r.ok;

export function unwrapOr<T, E>(r: Result<T, E>, fallback: T): T {
  return r.ok ? r.value : fallback;
}

export function mapResult<T, U, E>(r: Result<T, E>, f: (v: T) => U): Result<U, E> {
  return r.ok ? { ok: true, value: f(r.value) } : r;
}

/** Shape returned from server actions to client components. `cause` is stripped. */
export type ActionState<T = undefined> =
  | { ok: true; data: T }
  | { ok: false; error: { code: ErrorCode; message: string; fieldErrors?: Record<string, string[]> } }
  | { ok: null }; // initial

export function toActionState<T>(r: Result<T, AppError>): ActionState<T> {
  if (r.ok) return { ok: true, data: r.value };
  const { code, message, fieldErrors } = r.error;
  return { ok: false, error: { code, message, fieldErrors } };
}
