import { FormEvent, useState } from "react";
import { del, get, post, put } from "../api";
import { ErrorBox, Field, Modal, Notice, useAction, useLoad } from "../components/ui";

function ProviderForm({ initial, defaults, onDone }: any) {
  const [f, setF] = useState<any>(initial ?? { kind: "openai", name: "", base_url: "", model: "", api_key: "", enabled: true, is_default: false, timeout_s: 60 });
  const act = useAction();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body: any = { ...f };
    if (!body.api_key) delete body.api_key;
    if (!body.base_url) delete body.base_url;
    const r = await act.run(() => (f.id ? put(`/api/v1/ai/providers/${f.id}`, body) : post("/api/v1/ai/providers", body)));
    if (r) onDone();
  };
  return (
    <form onSubmit={submit}>
      <Field label="Provider">
        <select className="input" value={f.kind} disabled={!!f.id} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          <option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="ollama">Ollama (local)</option>
        </select>
      </Field>
      <Field label="Display name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
      <Field label={`Base URL (default ${defaults[f.kind]})`}><input className="input" value={f.base_url ?? ""} placeholder={defaults[f.kind]} onChange={(e) => setF({ ...f, base_url: e.target.value })} /></Field>
      <Field label="Model"><input className="input" value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })} required placeholder={f.kind === "ollama" ? "llama3.1" : f.kind === "deepseek" ? "deepseek-chat" : "gpt-4o-mini"} /></Field>
      {f.kind !== "ollama" && (
        <Field label={f.has_api_key ? `API key (saved: ${f.api_key_masked}; blank = keep)` : "API key"}>
          <input className="input" type="password" autoComplete="off" value={f.api_key ?? ""} onChange={(e) => setF({ ...f, api_key: e.target.value })} />
        </Field>
      )}
      <Field label="Timeout (s)"><input className="input" type="number" min={5} max={300} value={f.timeout_s} onChange={(e) => setF({ ...f, timeout_s: Number(e.target.value) })} /></Field>
      <label className="flex gap-2 items-center text-sm mt-2"><input type="checkbox" checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.target.checked })} /> Enabled</label>
      <label className="flex gap-2 items-center text-sm"><input type="checkbox" checked={f.is_default} onChange={(e) => setF({ ...f, is_default: e.target.checked })} /> Default provider</label>
      {act.view}
      <button className="btn mt-3" disabled={act.busy}>Save</button>
    </form>
  );
}

export default function AIPage() {
  const { data, error, reload } = useLoad(() => get("/api/v1/ai/providers"));
  const [edit, setEdit] = useState<any>(null);
  const [results, setResults] = useState<Record<number, any>>({});
  const act = useAction();
  if (error) return <ErrorBox error={error} />;
  if (!data) return <div>Loading…</div>;
  const test = async (id: number) => {
    setResults({ ...results, [id]: { pending: true } });
    const r = await act.run(() => post(`/api/v1/ai/providers/${id}/test`));
    setResults((x) => ({ ...x, [id]: r }));
    reload();
  };
  return (
    <div>
      <div className="flex items-center mb-3"><h1 className="h1 mb-0">AI Settings</h1><button className="btn ml-auto" onClick={() => setEdit({})}>Add provider</button></div>
      <Notice>API keys are encrypted at rest and never returned in full. Analytics are computed by the backend; AI only receives a concise verified fact sheet. No inference runs on the ESP32.</Notice>
      {act.view}
      <div className="grid md:grid-cols-2 gap-3">
        {data.providers.map((p: any) => (
          <div key={p.id} className="card">
            <div className="flex items-center gap-2">
              <b>{p.name}</b><span className="badge">{p.kind}</span>{p.is_default && <span className="badge-ok">default</span>}{!p.enabled && <span className="badge-warn">disabled</span>}
            </div>
            <div className="text-sm text-stone-600 mt-1">{p.model} · {p.base_url}</div>
            <div className="text-xs text-stone-500">Key: {p.has_api_key ? p.api_key_masked : "none"}</div>
            <div className="text-xs mt-1">
              Last test: {p.last_test_at ? <span className={p.last_test_ok ? "pos" : "neg"}>{p.last_test_ok ? "OK" : "failed"} · {p.last_test_latency_ms ?? "—"} ms · {p.last_test_message}</span> : "never"}
            </div>
            {results[p.id] && !results[p.id].pending && (
              <ul className="text-xs mt-1 list-disc ml-4">{results[p.id].steps.map((s: string) => <li key={s}>{s}</li>)}<li className={results[p.id].ok ? "pos" : "neg"}>{results[p.id].message}</li></ul>
            )}
            <div className="mt-2 space-x-1">
              <button className="btn" onClick={() => test(p.id)} disabled={results[p.id]?.pending}>{results[p.id]?.pending ? "Testing…" : "Test connection"}</button>
              <button className="btn-alt" onClick={() => setEdit({ ...p, api_key: "" })}>Edit</button>
              <button className="btn-alt" onClick={() => confirm("Delete provider?") && act.run(() => del(`/api/v1/ai/providers/${p.id}`)).then(reload)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
      {data.providers.length === 0 && <p className="text-sm text-stone-500">No AI providers configured.</p>}
      {edit && <Modal title={edit.id ? "Edit AI provider" : "Add AI provider"} onClose={() => setEdit(null)}><ProviderForm initial={edit.id ? edit : undefined} defaults={data.defaults} onDone={() => { setEdit(null); reload(); }} /></Modal>}
    </div>
  );
}
