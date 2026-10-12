import type { About } from "../App";

export default function AboutPage({ about }: { about: About | null }) {
  if (!about) return null;
  return (
    <div className="max-w-2xl">
      <h1 className="h1">About</h1>
      <div className="card">
        <div className="text-lg font-semibold">{about.application} <span className="badge">v{about.version}</span></div>
        <dl className="grid grid-cols-[8rem_1fr] text-sm gap-y-1 mt-3">
          <dt className="text-stone-500">Owner</dt><dd>{about.owner.name}</dd>
          <dt className="text-stone-500">Email</dt><dd><a className="underline" href={`mailto:${about.owner.email}`}>{about.owner.email}</a></dd>
          <dt className="text-stone-500">Phone</dt><dd>{about.owner.phone}</dd>
          <dt className="text-stone-500">Environment</dt><dd>{about.environment}</dd>
          <dt className="text-stone-500">Market data</dt><dd>{about.market_provider}</dd>
          <dt className="text-stone-500">API docs</dt><dd><a className="underline" href="/api/docs" target="_blank" rel="noreferrer">OpenAPI / Swagger</a></dd>
        </dl>
        <h2 className="h2 mt-4">Disclaimer</h2>
        <p className="text-sm text-stone-700">{about.disclaimer}</p>
      </div>
    </div>
  );
}
