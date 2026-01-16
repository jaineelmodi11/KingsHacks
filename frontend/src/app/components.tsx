"use client";

import Link from "next/link";

export function Container({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-6xl px-4 py-10">{children}</div>;
}

export function Nav() {
  return (
    <div className="sticky top-0 z-20 border-b border-zinc-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2">
          <div className="h-9 w-9 rounded-xl bg-zinc-900" />
          <div className="leading-tight">
            <div className="text-sm font-semibold">TravelPay</div>
            <div className="text-xs text-zinc-500">Travel verification + audit</div>
          </div>
        </Link>
        <div className="flex items-center gap-2">
          <Link className="rounded-xl px-3 py-2 text-sm hover:bg-zinc-100" href="/setup">
            Setup
          </Link>
          <Link className="rounded-xl px-3 py-2 text-sm hover:bg-zinc-100" href="/checkout">
            Checkout
          </Link>
          <Link className="rounded-xl px-3 py-2 text-sm hover:bg-zinc-100" href="/approve">
            Approve
          </Link>
          <Link className="rounded-xl px-3 py-2 text-sm hover:bg-zinc-100" href="/admin">
            Audit
          </Link>
        </div>
      </div>
    </div>
  );
}

export function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">{children}</div>;
}

export function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full bg-zinc-100 px-3 py-1 text-sm text-zinc-700">
      {children}
    </span>
  );
}

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={
        "rounded-xl bg-zinc-900 px-4 py-3 font-medium text-white hover:bg-zinc-800 disabled:opacity-50 " +
        (props.className ?? "")
      }
    />
  );
}

export function SecondaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={
        "rounded-xl border border-zinc-300 bg-white px-4 py-3 font-medium hover:bg-zinc-50 disabled:opacity-50 " +
        (props.className ?? "")
      }
    />
  );
}

export function Stepper({ step }: { step: 1 | 2 | 3 | 4 }) {
  const steps = [
    { n: 1, label: "Setup" },
    { n: 2, label: "Checkout" },
    { n: 3, label: "Approve" },
    { n: 4, label: "Complete" },
  ] as const;

  return (
    <div className="flex items-center gap-2">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center gap-2">
          <div
            className={
              "flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold " +
              (step >= s.n ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-500")
            }
          >
            {s.n}
          </div>
          <div className={step >= s.n ? "text-sm font-medium" : "text-sm text-zinc-500"}>{s.label}</div>
          {i < steps.length - 1 && <div className="h-[2px] w-8 bg-zinc-200" />}
        </div>
      ))}
    </div>
  );
}
