export type TravelProfile = {
  travelMode: boolean;
  destination: string;
  dataOnlyEsim: boolean;
  preferredVerification: "PUSH" | "EMAIL" | "TOTP";
  policyStrictMode: boolean;
  emergencyContact?: string;
};

export type AuthRequest = {
  id: string;
  merchant: string;
  amount: number;
  currency: string;
  country: string;
  status: "IDLE" | "PENDING" | "APPROVED" | "DENIED";
  createdAt?: number;
  decidedAt?: number;
  recommendation?: string;
  riskReasoning?: string[];
};

type AuditLog = { t: number; msg: string };

const KEY_PROFILE = "tp_profile_v2";
const KEY_REQ = "tp_request_v2";
const KEY_LOGS = "tp_logs_v2";

function now() {
  return Date.now();
}

export function getProfile(): TravelProfile {
  if (typeof window === "undefined") {
    return {
      travelMode: true,
      destination: "United Kingdom",
      dataOnlyEsim: true,
      preferredVerification: "PUSH",
      policyStrictMode: true,
      emergencyContact: "",
    };
  }

  const raw = localStorage.getItem(KEY_PROFILE);
  if (!raw) {
    const def: TravelProfile = {
      travelMode: true,
      destination: "United Kingdom",
      dataOnlyEsim: true,
      preferredVerification: "PUSH",
      policyStrictMode: true,
      emergencyContact: "",
    };
    localStorage.setItem(KEY_PROFILE, JSON.stringify(def));
    addLog("Policy initialized (enterprise defaults)");
    return def;
  }
  return JSON.parse(raw);
}

export function saveProfile(p: TravelProfile) {
  localStorage.setItem(KEY_PROFILE, JSON.stringify(p));
  addLog(
    p.travelMode
      ? `Travel Mode enabled — ${p.destination} • data-only eSIM: ${p.dataOnlyEsim ? "yes" : "no"}`
      : "Travel Mode disabled"
  );
  addLog(`Strict policy mode: ${p.policyStrictMode ? "ON" : "OFF"} • preference: ${p.preferredVerification}`);
}

export function getRequest(): AuthRequest {
  const raw = typeof window !== "undefined" ? localStorage.getItem(KEY_REQ) : null;
  if (!raw) {
    const def: AuthRequest = {
      id: "demo-req",
      merchant: "Westminster Abbey Tickets",
      amount: 32,
      currency: "GBP",
      country: "UK",
      status: "IDLE",
    };
    if (typeof window !== "undefined") localStorage.setItem(KEY_REQ, JSON.stringify(def));
    return def;
  }
  return JSON.parse(raw);
}

function setRequest(r: AuthRequest) {
  localStorage.setItem(KEY_REQ, JSON.stringify(r));
}

export function startVerification() {
  const p = getProfile();
  const r = getRequest();
  const { recommendation, riskReasoning } = generatePolicyDecision(p, r);

  const next: AuthRequest = {
    ...r,
    status: "PENDING",
    createdAt: now(),
    decidedAt: undefined,
    recommendation,
    riskReasoning,
  };
  setRequest(next);

  addLog(`Verification requested — ${r.currency} ${r.amount} at ${r.merchant} (${r.country})`);
  addLog("Decision engine: evaluated context + policy → routed to in-app approval");
}

export function approve() {
  const r = getRequest();
  const next: AuthRequest = { ...r, status: "APPROVED", decidedAt: now() };
  setRequest(next);
  addLog("User approved request (consent-based, in-app)");
  addLog("Transaction authorized ✅");
}

export function deny() {
  const r = getRequest();
  const next: AuthRequest = { ...r, status: "DENIED", decidedAt: now() };
  setRequest(next);
  addLog("User denied request ❌");
}

export function resetDemo() {
  localStorage.removeItem(KEY_REQ);
  localStorage.removeItem(KEY_LOGS);
  addLog("Demo reset");
}

export function getLogs(): AuditLog[] {
  const raw = localStorage.getItem(KEY_LOGS);
  if (!raw) return [];
  return JSON.parse(raw);
}

function addLog(msg: string) {
  const logs = getLogs();
  logs.unshift({ t: now(), msg });
  localStorage.setItem(KEY_LOGS, JSON.stringify(logs.slice(0, 30)));
}

function generatePolicyDecision(p: TravelProfile, r: AuthRequest) {
  const reasons: string[] = [];

  if (p.travelMode) reasons.push("Travel Mode is ON (user is abroad)");
  if (p.dataOnlyEsim) reasons.push("Data-only eSIM detected → SMS OTP unreliable");
  reasons.push("User consent required for transaction authorization");
  if (p.policyStrictMode) reasons.push("Strict policy: prefer phishing-resistant verification (in-app / passkeys)");

  let recommendation = "Route to in-app approval for verification.";
  if (!p.travelMode) recommendation = "Enable Travel Mode to apply safer travel verification policies.";
  if (!p.dataOnlyEsim && p.travelMode) {
    recommendation = `Route to ${p.preferredVerification} per preference (in-app as fallback).`;
  }

  return { recommendation, riskReasoning: reasons };
}
