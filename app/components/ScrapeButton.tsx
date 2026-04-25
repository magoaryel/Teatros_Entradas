"use client";
import { useState } from "react";

export default function ScrapeButton({ eventId }: { eventId: number }) {
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setLoading(true);
    try {
      await fetch(`/api/scrape/${eventId}`, { method: "POST" });
    } finally {
      setLoading(false);
      window.location.reload();
    }
  }

  return (
    <button className="btn btn-ghost btn-sm" onClick={handleClick} disabled={loading} title="Actualizar este evento">
      {loading ? "..." : "🔄"}
    </button>
  );
}
