import "./globals.css";
import { Nav } from "./components";

export const metadata = {
  title: "TravelPay",
  description: "Enterprise-grade travel verification demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-zinc-50 text-zinc-900">
        <Nav />
        {children}
      </body>
    </html>
  );
}