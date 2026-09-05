export function BenchmarkBanner({ label }: { label: string }) {
  return (
    <p className="banner" role="status">
      {label}
    </p>
  );
}
