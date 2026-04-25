import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Monitor de Entradas — Aryel",
  description: "Seguimiento de ventas de entradas para shows",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <nav>
          <a href="/" className="brand">🎭 Entradas</a>
          <a href="/" className="nav-link">Dashboard</a>
          <a href="/add" className="nav-link">+ Añadir</a>
          <div className="spacer" />
          <a href="/config" className="nav-link">⚙ Config</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
