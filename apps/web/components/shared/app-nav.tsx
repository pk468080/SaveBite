"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  /** Optional count badge (e.g. unread notifications). */
  badge?: number;
}

/** Responsive app navigation: horizontal bar on small
 * screens, sidebar on large screens. Used by the
 * customer, merchant, and admin shells. The active
 * link is a visual convenience only — it never grants
 * access; the backend verifies every operation. */
export function AppNav({ title, items }: { title: string; items: NavItem[] }) {
  const currentPath = usePathname() ?? "";
  return (
    <nav aria-label={`${title} navigation`} className="w-full lg:w-60 lg:shrink-0">
      <h2 className="mb-3 hidden text-sm font-semibold text-muted-foreground lg:block">{title}</h2>
      <ul className="flex gap-1 overflow-x-auto lg:flex-col">
        {items.map((item) => {
          // Active when exact, or when this item is the
          // LONGEST nav prefix of the current path — so
          // /customer/orders does not also highlight
          // the /customer index link.
          const active =
            currentPath === item.href ||
            (currentPath.startsWith(`${item.href}/`) &&
              !items.some(
                (other) =>
                  other.href !== item.href &&
                  other.href.startsWith(`${item.href}/`) &&
                  (currentPath === other.href || currentPath.startsWith(`${other.href}/`)),
              ));
          return (
            <li key={item.href} className="shrink-0">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block rounded-md px-3 py-2 text-sm font-medium",
                  active ? "bg-accent text-accent-foreground" : "hover:bg-accent",
                )}
              >
                {item.label}
                {item.badge && item.badge > 0 ? (
                  <span className="ml-2 rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-primary-foreground">
                    {item.badge}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
