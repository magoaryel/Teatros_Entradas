"use client";
import { useState } from "react";

export default function RefreshButton() {
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setLoading(true);
    try {
      await fetch("/api/cron/scrape");
    } finally {
      setLoading(false);
      window.location.reload();
    }
  }

  return (
    <button className="btn btn-ghost" onClick={handleClick} disabled={loading}>
      {loading ? "Actualizando..." : "🔄 Actualizar todo"}
    </button>
  );
}
