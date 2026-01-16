"use client";

import { useEffect, useState } from "react";
import { Card, Container, Pill } from "../components";
import { getLogs } from "../../lib/demo";

function fmt(t: number) {
  const d = new Date(t);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function Admin() {
  const [logs, setLogs] = useState<{ t: number; msg: string }[]>([]);

  useEffect(() => {
    setLogs(getLogs());
    const id = setInterval(() => setLogs(getLogs()), 800);
    return () => clearInterval(id);
  }, []);

  return (
    <Container>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Audit Trail</h2>
          <div className="text-sm text-zinc-600">Governance-ready event log (demo).</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Pill>Policy decisioning</Pill>
          <Pill>Consent-based approval</Pill>
          <Pill>Auditability</Pill>
        </div>
      </div>

      <Card>
        {logs.length === 0 ? (
          <div className="text-sm text-zinc-600">No events yet. Run the checkout demo.</div>
        ) : (
          <div className="space-y-3">
            {logs.map((l, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl border border-zinc-200 bg-white p-4">
                <div className="w-16 shrink-0 text-xs text-zinc-500">{fmt(l.t)}</div>
                <div className="text-sm">{l.msg}</div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </Container>
  );
}
