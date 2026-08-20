/**
 * Utility for building authenticated, org-scoped API request headers.
 * Ensures all API calls include:
 * - Authorization: Bearer {token}
 * - X-Org-Id: {currentOrgId}
 */

export type AuthHeaders = {
  "Authorization": string;
  "X-Org-Id": string;
  "Content-Type"?: string;
};

/**
 * Build org-scoped headers for authenticated API requests.
 * 
 * Usage:
 *   const headers = getAuthHeaders(token, orgId, "application/json");
 *   const response = await fetch(url, {
 *     method: "POST",
 *     headers,
 *     body: JSON.stringify(payload),
 *   });
 */
export function getAuthHeaders(
  token: string | null,
  orgId: string | null,
  contentType?: string
): AuthHeaders & Record<string, string> {
  if (!token) {
    throw new Error("Authentication token is required. User must be logged in.");
  }

  if (!orgId) {
    throw new Error("Organization ID is required. Please select an organization.");
  }

  const headers: Record<string, string> = {
    "Authorization": `Bearer ${token}`,
    "X-Org-Id": orgId,
  };

  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  return headers;
}

/**
 * Build headers for unauthenticated requests (e.g., guest mode).
 * Does NOT include Authorization header.
 */
export function getGuestHeaders(contentType?: string): Record<string, string> {
  const headers: Record<string, string> = {};

  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  return headers;
}
