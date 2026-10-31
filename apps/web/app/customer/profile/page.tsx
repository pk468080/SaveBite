import { createServices } from "@savebite/api-client";
import Link from "next/link";
import { SignOutButton } from "@/components/shared/sign-out-button";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/states";
import { createServerApiClient } from "@/lib/api/server";

/**
 * Customer profile (W3). Read-only BY DESIGN: no
 * backend endpoint supports editing profile fields,
 * so no editable fields are invented and no direct
 * browser writes to Supabase tables are made. Only
 * information returned by GET /v1/me is shown.
 */
export default async function CustomerProfilePage() {
  let me = null;
  let failed = false;
  try {
    const client = await createServerApiClient();
    me = await createServices(client).auth.me();
  } catch {
    failed = true;
  }

  if (failed || !me) {
    return <Alert variant="error">Could not load your account information. Please try again.</Alert>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Profile</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your account information, as returned by SaveBite. Editing is not available yet —
          no profile-editing endpoint exists on the backend.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Account information</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p className="flex justify-between gap-4">
            <span className="text-muted-foreground">Email</span>
            <span className="font-medium">{me.email ?? "Not provided"}</span>
          </p>
          <p className="flex justify-between gap-4">
            <span className="text-muted-foreground">Account ID</span>
            <span className="font-mono text-xs">{me.id}</span>
          </p>
          {me.platform_roles.length > 0 ? (
            <p className="flex justify-between gap-4">
              <span className="text-muted-foreground">Platform roles</span>
              <span className="font-medium">{me.platform_roles.join(", ")}</span>
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline">
          <Link href="/customer/orders">Order history</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/customer/notifications">Notifications</Link>
        </Button>
        <SignOutButton />
      </div>
    </div>
  );
}
