"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Card, Container, Pill, PrimaryButton, SecondaryButton, Stepper } from "../components";
import { approve, deny, getProfile, getRequest } from "../../lib/demo";

export default function ApprovePage() {
  const [tick, setTick] = useState(0);
  const profile = useMemo(() => (typeof window !== "undefined" ? getProfile() : null), [tick]);
  const req = useMemo(() => (typeof window !== "undefined" ? getRequest() : null), [tick]);

  useEffect(() => setTick((t) => t + 1), []);

  if (!profile || !req) return null;

  return (
    <Container>
      <div className="mb-6 space-y-2">
        <Stepper step={3} />
        <h2 className="text-2xl font-semibold">Approve Purchase</h2>
        <div className="text-sm text-zinc-600">Bank-style in-app verification (demo).</div>
      </div>

      <div className="mx-auto grid max-w-2xl gap-6">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm text-zinc-500">Merchant</div>
              <div className="text-lg font-semibold">{req.merchant}</div>
            </div>
            <div className="text-right">
              <div className="text-sm text-zinc-500">Amount</div>
              <div className="text-2xl font-semibold">
                {req.currency} {req.amount.toFixed(2)}
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Pill>{profile.travelMode ? "Travel Mode" : "No Travel Mode"}</Pill>
            <Pill>{profile.dataOnlyEsim ? "Data-only eSIM" : "SMS available"}</Pill>
            <Pill>Location: {req.country}</Pill>
            <Pill>Status: {req.status}</Pill>
          </div>

          <div className="mt-5 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
            <div className="text-sm font-semibold">Recommendation</div>
            <div className="mt-1 text-sm text-zinc-600">{req.recommendation}</div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <PrimaryButton
              disabled={req.status !== "PENDING" && req.status !== "IDLE"}
              onClick={() => {
                approve();
                setTick((t) => t + 1);
              }}
            >
              Approve
            </PrimaryButton>
            <SecondaryButton
              disabled={req.status !== "PENDING" && req.status !== "IDLE"}
              onClick={() => {
                deny();
                setTick((t) => t + 1);
              }}
            >
              Deny
            </SecondaryButton>
          </div>

          <div className="mt-4 text-xs text-zinc-500">
            Compliance note (demo): action is logged with timestamp for auditability.
          </div>
        </Card>

        <div className="flex gap-3">
          <Link href="/checkout" className="w-full">
            <SecondaryButton className="w-full">Back to Checkout</SecondaryButton>
          </Link>
          <Link href="/admin" className="w-full">
            <SecondaryButton className="w-full">View Audit Trail</SecondaryButton>
          </Link>
        </div>
      </div>
    </Container>
  );
}
