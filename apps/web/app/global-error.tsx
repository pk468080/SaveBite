"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

/** Global error boundary. Shows a safe message and a
 * retry; never leaks stack traces or internal details. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
          <h1 className="text-3xl font-bold">Something went wrong</h1>
          <p className="max-w-md text-muted-foreground">
            An unexpected error occurred. Please try again.
          </p>
          <Button onClick={reset}>Try again</Button>
        </div>
      </body>
    </html>
  );
}
