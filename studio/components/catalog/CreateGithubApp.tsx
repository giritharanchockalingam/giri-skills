"use client";
/* One click "Create the GitHub App": posts the App manifest to GitHub (personal account or an organization). */
import { useState } from "react";

export function CreateGithubApp({ manifest }: { manifest: string }) {
  const [org, setOrg] = useState("");
  const valid = org === "" || /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/.test(org);
  const action = org ? `https://github.com/organizations/${encodeURIComponent(org)}/settings/apps/new` : "https://github.com/settings/apps/new";
  return (
    <form method="post" action={action} className="flex flex-wrap items-end gap-2">
      <input type="hidden" name="manifest" value={manifest} />
      <div className="field" style={{ margin: 0 }}>
        <label htmlFor="gh-org">GitHub organization (leave empty for your personal account)</label>
        <input id="gh-org" className="input" value={org} onChange={(e) => setOrg(e.target.value.trim())} placeholder="e.g. acme-corp" style={{ maxWidth: 280 }} aria-invalid={!valid} />
      </div>
      <button type="submit" className="btn btn-primary" disabled={!valid}>Create the GitHub App</button>
    </form>
  );
}
