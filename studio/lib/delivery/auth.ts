/* Which delivery requests the middleware lets through to the route's own API-key check (no session needed). Pure. */
export function isKeyBearingDeliveryRequest(pathname: string, authorization: string | null | undefined): boolean {
  return pathname.startsWith("/api/delivery-runs") && /^Bearer\s+\S+/i.test(authorization ?? "");
}
