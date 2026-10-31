"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/** Simple accessible tabs (button-based, no library needed in W1). */
export function Tabs({
  tabs,
  defaultValue,
  className,
}: {
  tabs: Array<{ value: string; label: string; content: React.ReactNode }>;
  defaultValue?: string;
  className?: string;
}) {
  const [active, setActive] = React.useState(defaultValue ?? tabs[0]?.value);
  const current = tabs.find((t) => t.value === active);
  return (
    <div className={className}>
      <div role="tablist" aria-label="Sections" className="inline-flex h-10 items-center justify-center rounded-md bg-muted p-1">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active === tab.value}
            onClick={() => setActive(tab.value)}
            className={cn(
              "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium transition-colors",
              active === tab.value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="mt-4">
        {current?.content}
      </div>
    </div>
  );
}
