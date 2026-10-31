import { Brand } from "@/components/shared/site-header";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mb-8">
        <Brand />
      </div>
      <main className="w-full max-w-md">{children}</main>
    </div>
  );
}
