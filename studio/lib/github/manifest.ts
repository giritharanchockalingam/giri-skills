/* The GitHub App manifest (one-click "create the App" flow). Least privilege: read-only repository contents and
 * metadata; OAuth during install so ownership of an installation can be proven; no webhook events yet (slice 4). */
export function appManifest(origin: string, name = "Skills Factory") {
  return {
    name: name.slice(0, 34), url: origin, public: false,
    hook_attributes: { url: `${origin}/api/github/webhook`, active: false },
    redirect_url: `${origin}/api/github/manifest`,
    callback_urls: [`${origin}/api/github/callback`],
    setup_url: `${origin}/api/github/callback`,
    request_oauth_on_install: true,
    setup_on_update: true,
    default_permissions: { contents: "read", metadata: "read" },
    default_events: [] as string[],
  };
}
