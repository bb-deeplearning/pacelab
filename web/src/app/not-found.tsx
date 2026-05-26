import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-dvh px-6 py-24 max-w-3xl mx-auto">
      <h1 className="font-serif text-4xl">404 · driver not found</h1>
      <p className="mt-4 text-muted">
        That driver/season combination doesn&apos;t have a profile yet — either the metrics
        haven&apos;t been built, or this driver didn&apos;t race that season.
      </p>
      <Link
        href="/"
        className="mt-8 inline-block font-mono text-xs text-accent underline-offset-4 hover:underline"
      >
        ← back to all drivers
      </Link>
    </main>
  );
}
