import Link from "next/link";
import { Card, Container, Pill, PrimaryButton } from "./components";

export default function Home() {
  return (
    <Container>
      <div className="grid gap-8 lg:grid-cols-2 lg:items-center">
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <Pill>IBM Track</Pill>
            <Pill>Enterprise Security</Pill>
            <Pill>Governance + Audit</Pill>
          </div>

          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            Reliable travel verification — without insecure SMS workarounds.
          </h1>

          <p className="text-lg text-zinc-600">
            TravelPay is a demo of an enterprise-ready fallback that replaces SMS OTP failures abroad with
            consent-based in-app approval, policy controls, and a clear audit trail.
          </p>

          <div className="flex flex-wrap gap-3">
            <Link href="/setup">
              <PrimaryButton>Start Demo</PrimaryButton>
            </Link>
            <Link
              href="/checkout"
              className="rounded-xl border border-zinc-300 bg-white px-4 py-3 font-medium hover:bg-zinc-50"
            >
              Jump to Checkout
            </Link>
          </div>

          <div className="text-sm text-zinc-500">
            Scenario: Visa-only purchase abroad → issuer verification → SMS OTP fails on data-only eSIM.
          </div>
        </div>

        <Card>
          <div className="space-y-4">
            <div className="text-sm font-semibold text-zinc-900">Enterprise design goals</div>

            <div className="grid gap-3">
              {[
                ["Security", "Avoid SMS as a weak/unreliable channel; use stronger consent-based flows."],
                ["Governance", "Policy toggles + explainable decisioning for audits."],
                ["Reliability", "Works when travelers have data-only eSIMs (no phone number access)."],
                ["Responsible by design", "Human-in-the-loop approvals; minimal data; clear logs."],
              ].map(([t, d]) => (
                <div key={t} className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                  <div className="text-sm font-medium">{t}</div>
                  <div className="text-sm text-zinc-600">{d}</div>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <div className="text-sm font-medium">Future</div>
              <div className="text-sm text-zinc-600">
                Passkeys/WebAuthn, issuer integration, risk policies, and enterprise audit exports.
              </div>
            </div>
          </div>
        </Card>
      </div>
    </Container>
  );
}
