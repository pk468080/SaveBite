"use client";

import { useMerchantStores } from "@/components/merchant/store-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, LoadingState } from "@/components/ui/states";

/**
 * Merchant settings (W4). There is no merchant
 * settings endpoint in the backend, so this page
 * changes nothing — it states the account the
 * portal is signed in as, the merchant
 * memberships the backend reports, and the two
 * honest limitations: notification preferences
 * are not persisted (PATCH returns 501), and
 * document submission has no merchant-facing
 * endpoint yet. No staff invitation or role
 * management is offered, because no such
 * merchant API exists in this milestone.
 */
export default function MerchantSettingsPage() {
  const { merchants, stores, loading, error } = useMerchantStores();

  if (loading) return <LoadingState label="Loading settings" />;
  if (error) return <Alert variant="error">{error}</Alert>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Your merchant account, as the backend reports it. Nothing on this page changes backend
          data.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Your merchants and stores</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {merchants.length === 0 ? (
            <p className="text-muted-foreground">No merchant memberships yet.</p>
          ) : (
            merchants.map((merchant) => (
              <p key={merchant.id}>
                {merchant.display_name} — status {merchant.status}, verification{" "}
                {merchant.verification_status}
              </p>
            ))
          )}
          <p className="text-muted-foreground">
            {stores.length} authorized store(s). Roles are assigned by the platform, not from this
            portal — staff invitation and role management are not part of this milestone.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <p className="text-muted-foreground">
            Notification preferences cannot be changed here: the backend stores no per-user
            preferences yet, and saving them returns 501. Reading and marking notifications as read
            works from the Notifications page.
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Verification documents</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <p className="text-muted-foreground">
            Document submission is not available through this portal yet — there is no
            merchant-facing upload endpoint. Admin approval requires a verified, current FSSAI
            document, which the review team will request through another channel until that
            endpoint exists.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
