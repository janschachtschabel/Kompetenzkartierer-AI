// Who is signed in: the account the token belongs to (GET /api/v1/me).
import { apiFetch, verifyToken } from "./http";

/** The roles an admin grants (app/core/auth.py). */
export type Role = "admin" | "redaktion" | "nutzer";

export interface Me {
  id: string;
  name: string;
  roles: Role[];
}

export function getMe(): Promise<Me> {
  return apiFetch<Me>("/api/v1/me");
}

/** The account a candidate token belongs to, or null where the server refuses the token. */
export function checkToken(candidate: string): Promise<Me | null> {
  return verifyToken<Me>(candidate);
}
