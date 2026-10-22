// Thin fetch wrapper: sends the token from sessionStorage as a bearer token and
// turns every failure into a typed ApiError the page can say in German.

// Per tab: a reload keeps it, closing the tab ends the session. The account
// itself (`Me`) stays in memory (session.ts), never in storage.
const TOKEN_STORAGE = "kka_token";

/** network: no answer; unauthorized: no valid token (401); forbidden: the account lacks the role (403). */
export type ApiErrorKind = "network" | "unauthorized" | "forbidden" | "server";

export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    readonly status: number,
    /** The server's stable code for programs (app/api/errors.py); refusals.ts says the known ones in German. */
    readonly code?: string,
    /** The server's English sentence (its `message`); quoted, never shown as German. */
    readonly sentence?: string,
    /** What the server adds by field and kind; never input values. */
    readonly details: Record<string, unknown> = {},
    /** Seconds a 429 or 503 asks the client to wait, where it names them. */
    readonly retryAfter?: number,
  ) {
    super(`api error: ${kind} (${status})`);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_STORAGE);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_STORAGE, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_STORAGE);
}

// What to do once the server no longer accepts the token. Registered by the
// router, which knows where the sign-in is; this module cannot import it, since
// the router imports this module for the token.
let unauthorizedHandler: (() => void) | null = null;

export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  return "server";
}

/** The seconds a 429 or 503 asks to wait; a date in their place leaves the wait unknown rather than guessed. */
function waitOf(status: number, header: string | null): number | undefined {
  if (status !== 429 && status !== 503) return undefined;
  const value = header?.trim() ?? "";
  return /^\d+$/.test(value) ? Number(value) : undefined;
}

function failedAnswer(response: Response, body: unknown): ApiError {
  // The server's shape is {code, message, details}; anything else - a proxy's
  // HTML page, an empty body - keeps only its status.
  const shape = (body ?? {}) as { code?: unknown; message?: unknown; details?: unknown };
  const code = typeof shape.code === "string" ? shape.code : undefined;
  const sentence = typeof shape.message === "string" ? shape.message : undefined;
  const details =
    shape.details && typeof shape.details === "object" && !Array.isArray(shape.details)
      ? (shape.details as Record<string, unknown>)
      : {};
  return new ApiError(
    kindForStatus(response.status),
    response.status,
    code,
    sentence,
    details,
    waitOf(response.status, response.headers.get("Retry-After")),
  );
}

async function bodyOf(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined; // no JSON: the status says what there is to say
  }
}

/**
 * One request, the way every request goes: the token where there is one, a JSON
 * body said to be JSON, a network failure as an ApiError, and a token the server
 * no longer accepts dropped with the app told.
 *
 * `withToken` is false for open routes, which do not look at a token: a 401 there
 * says nothing about the session.
 */
export async function send(
  path: string,
  init: RequestInit = {},
  { withToken = true }: { withToken?: boolean } = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = withToken ? getToken() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  // A string body is JSON here. Without saying so, fetch sends text/plain, and
  // FastAPI refuses what it could otherwise have read. Only for a string: an
  // upload sends FormData, whose boundary the browser writes into this header.
  if (typeof init.body === "string" && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError("network", 0);
  }
  if (response.ok) return response;

  const error = failedAnswer(response, await bodyOf(response));
  if (response.status === 401 && token) {
    // The token is no longer good. Keeping it made every view show the same
    // error with no way back but a reload. A 403 is different: the token is
    // fine, this route is not for this account, and the view says so.
    clearToken();
    unauthorizedHandler?.();
  }
  throw error;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await send(path, init);
  const body = await response.text();
  return (body ? JSON.parse(body) : null) as T;
}

/**
 * The account a candidate token belongs to, checked before the token is kept;
 * null where the server refuses it. Fetched directly rather than through `send`:
 * a wrong token typed at the sign-in is that page's business, not a session ending.
 * Every refusal counts against the address's failure limit (429 after it).
 */
export async function verifyToken<T>(candidate: string, path = "/api/v1/me"): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Authorization: `Bearer ${candidate}` } });
  } catch {
    throw new ApiError("network", 0);
  }
  if (response.status === 200) return (await response.json()) as T;
  if (response.status === 401) return null;
  throw failedAnswer(response, await bodyOf(response));
}
