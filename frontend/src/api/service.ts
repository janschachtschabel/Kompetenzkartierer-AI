// Public facts about the service (GET /api/v1/info), asked before anyone signs in.
import { send } from "./http";

export interface Info {
  name: string;
  version: string;
  /** What a visitor without a token may do (PUBLIC_ACCESS). */
  public_access: "off" | "lookup" | "search";
  /** The largest file an upload may be (MAX_UPLOAD_MB). */
  max_upload_mb: number;
}

export async function getInfo(): Promise<Info> {
  // An open route: a token would not be looked at, and a 401 here says nothing of the session.
  const response = await send("/api/v1/info", {}, { withToken: false });
  return (await response.json()) as Info;
}
