import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function UnauthorizedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-3xl font-bold">You do not have access to this area</h1>
      <p className="max-w-md text-muted-foreground">
        This area is restricted. If you believe you should have access, ask a
        platform administrator to check your account — access is decided by
        the backend, not by this page.
      </p>
      <div className="flex gap-3">
        <Button asChild>
          <Link href="/">Back to home</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/sign-in">Sign in with another account</Link>
        </Button>
      </div>
    </div>
  );
}
