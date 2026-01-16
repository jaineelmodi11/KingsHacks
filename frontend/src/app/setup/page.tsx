"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, Container, Pill, PrimaryButton, SecondaryButton, Stepper } from "../components";
import { getProfile, saveProfile, TravelProfile } from "../../lib/demo";

export default function Setup() {
  const [profile, setProfile] = useState<TravelProfile | null>(null);

  useEffect(() => {
    setProfile(getProfile());
  }, []);

  if (!profile) return null;

  return (
    <Container>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-2">
          <Stepper step={1} />
          <h2 className="text-2xl font-semibold">Travel Mode Setup</h2>
          <div className="text-sm text-zinc-600">Configure travel context + enterprise policy controls.</div>
        </div>
        <div className="flex gap-2">
          <Pill>{profile.travelMode ? "Travel Mode: ON" : "Travel Mode: OFF"}</Pill>
          <Pill>{profile.dataOnlyEsim ? "Data-only eSIM" : "SMS available"}</Pill>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <div className="space-y-4">
            <div className="text-sm font-semibold">Your travel context</div>

            <label className="flex items-center justify-between rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <div>
                <div className="font-medium">Travel Mode</div>
                <div className="text-sm text-zinc-600">Enables travel-aware verification policies</div>
              </div>
              <input
                type="checkbox"
                checked={profile.travelMode}
                onChange={(e) => setProfile({ ...profile, travelMode: e.target.checked })}
                className="h-5 w-5"
              />
            </label>

            <div className="grid gap-2">
              <div className="text-sm font-medium">Destination</div>
              <select
                className="rounded-xl border border-zinc-300 bg-white p-3"
                value={profile.destination}
                onChange={(e) => setProfile({ ...profile, destination: e.target.value })}
              >
                <option>United Kingdom</option>
                <option>France</option>
                <option>United States</option>
                <option>Italy</option>
                <option>Other</option>
              </select>
            </div>

            <label className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-white p-4">
              <input
                type="checkbox"
                checked={profile.dataOnlyEsim}
                onChange={(e) => setProfile({ ...profile, dataOnlyEsim: e.target.checked })}
                className="h-5 w-5"
              />
              <div>
                <div className="font-medium">I only have a data-only eSIM (no SMS)</div>
                <div className="text-sm text-zinc-600">Avoids SMS OTP channels when unreliable</div>
              </div>
            </label>

            <label className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white p-4">
              <div>
                <div className="font-medium">Strict policy mode</div>
                <div className="text-sm text-zinc-600">
                  Prefer phishing-resistant verification (in-app / passkeys) over SMS-style OTP.
                </div>
              </div>
              <input
                type="checkbox"
                checked={profile.policyStrictMode}
                onChange={(e) => setProfile({ ...profile, policyStrictMode: e.target.checked })}
                className="h-5 w-5"
              />
            </label>

            <div className="grid gap-2">
              <div className="text-sm font-medium">Preferred verification (fallback)</div>
              <div className="flex flex-wrap gap-2">
                {(["PUSH", "EMAIL", "TOTP"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setProfile({ ...profile, preferredVerification: m })}
                    className={
                      "rounded-full px-4 py-2 text-sm font-medium " +
                      (profile.preferredVerification === m
                        ? "bg-zinc-900 text-white"
                        : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200")
                    }
                  >
                    {m === "PUSH" ? "In-app Push" : m === "EMAIL" ? "Email" : "Authenticator (TOTP)"}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-2">
              <div className="text-sm font-medium">Emergency fallback contact (optional)</div>
              <input
                className="rounded-xl border border-zinc-300 bg-white p-3"
                placeholder="e.g., parent/partner contact"
                value={profile.emergencyContact ?? ""}
                onChange={(e) => setProfile({ ...profile, emergencyContact: e.target.value })}
              />
              <div className="text-xs text-zinc-500">
                Demo note: we don’t forward codes — we’re avoiding SMS dependency in the first place.
              </div>
            </div>

            <div className="flex gap-3">
              <PrimaryButton
                onClick={() => {
                  saveProfile(profile);
                  window.location.href = "/checkout";
                }}
              >
                Save & Continue
              </PrimaryButton>
              <Link href="/checkout">
                <SecondaryButton>Skip</SecondaryButton>
              </Link>
            </div>
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <div className="text-sm font-semibold">IBM track framing</div>

            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <div className="font-medium">Security</div>
              <div className="text-sm text-zinc-600">
                Reduce reliance on SMS OTP; use consent-based in-app approval.
              </div>
            </div>

            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
              <div className="font-medium">Governance</div>
              <div className="text-sm text-zinc-600">
                Policy toggles + explainable reasoning + an audit trail (see Audit tab).
              </div>
            </div>

            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <div className="font-medium">Responsible AI posture</div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-zinc-600">
                <li>Human-in-the-loop: user explicitly approves</li>
                <li>Transparent reasoning (no black-box approvals)</li>
                <li>Minimal data stored (demo uses local storage)</li>
              </ul>
            </div>
          </div>
        </Card>
      </div>
    </Container>
  );
}
