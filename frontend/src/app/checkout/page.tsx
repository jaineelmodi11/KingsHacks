"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Card, Container, Pill, PrimaryButton, SecondaryButton, Stepper } from "../components";
import { getProfile, getRequest, startVerification, resetDemo } from "../../lib/demo";

export default function Checkout() {
  const [tick, setTick] = useState(0);
  const profile = useMemo(() => (typeof window !== "undefined" ? getProfile() : null), [tick]);
  const req = useMemo(() => (typeof window !== "undefined" ? getRequest() : null), [tick]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 700);
    return () => clearInterval(id);
  }, []);

  if (!profile || !req) return null;

  return (
    <Container>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-2">
          <Stepper step={2} />
          <h2 className="text-2xl font-semibold">Merchant Checkout (Demo)</h2>
          <div className="text-sm text-zinc-600">Simulates a Visa-only merchant requiring issuer verification.</div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Pill>{profile.travelMode ? `Travel Mode: ON (${profile.destination})` : "Travel Mode: OFF"}</Pill>
          <Pill>{profile.dataOnlyEsim ? "Data-only eSIM" : "SMS available"}</Pill>
          <button
            className="rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm hover:bg-zinc-50"
            onClick={() => {
              resetDemo();
              window.location.reload();
            }}
          >
            Reset Demo
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <div className="space-y-3">
            <div className="text-sm font-semibold">Order</div>
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <div className="font-medium">Westminster Abbey — Entry Ticket</div>
              <div className="text-sm text-zinc-600">Date: Tomorrow • 1 Adult</div>
              <div className="mt-3 flex items-center justify-between">
                <div className="text-sm text-zinc-600">Total</div>
                <div className="text-xl font-semibold">£32.00</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Pill>Visa accepted</Pill>
              <Pill>Issuer verification</Pill>
              <Pill>Travel scenario</Pill>
            </div>

            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <div className="text-sm font-semibold">What usually breaks</div>
              <div className="mt-1 text-sm text-zinc-600">
                Issuer sends an SMS OTP — but travelers with data-only eSIM can’t receive it.
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <div className="text-sm font-semibold">Payment</div>

            {req.status === "IDLE" && (
              <>
                <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700">
                  Choose payment method
                </div>
                <PrimaryButton
                  onClick={() => {
                    startVerification();
                    setTick((t) => t + 1);
                  }}
                >
                  Pay £32 with Visa
                </PrimaryButton>
                <div className="text-xs text-zinc-500">
                  Demo creates a verification request. Approve it in the “Approve” tab.
                </div>
              </>
            )}

            {req.status === "PENDING" && (
              <>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <div className="font-medium text-amber-900">Verification required</div>
                  <div className="text-sm text-amber-900/80">
                    Issuer needs confirmation before completing payment.
                  </div>
                </div>

                <div className="rounded-xl border border-zinc-200 bg-white p-4">
                  <div className="text-sm font-semibold">Policy decision</div>
                  <div className="mt-1 text-sm text-zinc-600">{req.recommendation}</div>

                  <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                    <div className="text-sm font-semibold">Explainable reasoning</div>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-600">
                      {(req.riskReasoning ?? []).map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="mt-3 flex gap-2">
                    <Link href="/approve" className="w-full">
                      <PrimaryButton className="w-full">Open Approval Screen</PrimaryButton>
                    </Link>
                    <Link href="/setup" className="w-full">
                      <SecondaryButton className="w-full">Edit Policy</SecondaryButton>
                    </Link>
                  </div>
                </div>

                <div className="text-xs text-zinc-500">
                  IBM track story: consent-based verification + policy controls + auditability.
                </div>
              </>
            )}

            {req.status === "APPROVED" && (
              <>
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center">
                  <div className="text-3xl">✅</div>
                  <div className="mt-2 text-lg font-semibold text-emerald-900">Payment Complete</div>
                  <div className="text-sm text-emerald-900/80">Verified via in-app approval (no SMS).</div>
                </div>

                <div className="flex gap-2">
                  <Link href="/admin" className="w-full">
                    <SecondaryButton className="w-full">View Audit Trail</SecondaryButton>
                  </Link>
                  <Link href="/setup" className="w-full">
                    <SecondaryButton className="w-full">Try Another Scenario</SecondaryButton>
                  </Link>
                </div>
              </>
            )}

            {req.status === "DENIED" && (
              <>
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center">
                  <div className="text-3xl">❌</div>
                  <div className="mt-2 text-lg font-semibold text-rose-900">Payment Denied</div>
                  <div className="text-sm text-rose-900/80">User denied the verification request.</div>
                </div>
                <PrimaryButton
                  onClick={() => {
                    resetDemo();
                    window.location.reload();
                  }}
                >
                  Start Over
                </PrimaryButton>
              </>
            )}
          </div>
        </Card>
      </div>
    </Container>
  );
}
