import { EmptyState } from "@/components/ui/states";

/** Foundation placeholder page body, shared by the
 * app shells. Each page states which backend endpoint
 * will feed it in a later milestone. */
export function AreaPlaceholder({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">{title}</h1>
      <EmptyState title={`${title} arrives in a later milestone`} description={description} />
    </div>
  );
}
