import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Admin access-denied state (W6). Shown when
 * the backend answers 401 or 403 to an admin
 * request. It never retries the request, and it
 * never guesses which role the user has: the
 * backend gate admits only operations_admin and
 * super_admin, and every other role — including
 * support, finance and compliance roles, whose
 * names exist in the database — is denied by
 * that gate until a backend fix lands.
 */
export function AccessDenied({ detail }: { detail?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Access denied</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p>
          Your account is not authorized for platform administration. Access is decided by the
          backend, not by this page.
        </p>
        {detail ? <p className="text-muted-foreground">{detail}</p> : null}
        <p className="text-muted-foreground">
          If you believe you should have access, ask a platform administrator to check your
          account. Merchant membership never counts as platform-admin access.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href="/">Back to home</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/sign-in">Sign in with another account</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
