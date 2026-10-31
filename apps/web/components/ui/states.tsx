import * as React from "react";
import { cn } from "@/lib/utils";

/** Skeleton loading placeholder. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

/** Centered loading state for a page section. */
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center gap-3 py-12">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-64" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Empty state: shown when a list legitimately has no items. */
export function EmptyState({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-12 text-center">
      <h2 className="text-lg font-semibold">{title}</h2>
      {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {children}
    </div>
  );
}

/** Error state: shown when a section fails to load. Never leaks internal details. */
export function ErrorState({
  title = "Something went wrong",
  description = "Please try again. If the problem continues, contact support.",
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border border-destructive/50 p-12 text-center">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}

/** Inline alert banner (info / error / success). */
export function Alert({
  variant = "info",
  children,
}: {
  variant?: "info" | "error" | "success";
  children: React.ReactNode;
}) {
  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={cn(
        "rounded-md border px-4 py-3 text-sm",
        variant === "error"
          ? "border-destructive/50 bg-destructive/10 text-foreground"
          : variant === "success"
            ? "border-primary/50 bg-primary/10 text-foreground"
            : "border-border bg-muted text-foreground",
      )}
    >
      {children}
    </div>
  );
}
