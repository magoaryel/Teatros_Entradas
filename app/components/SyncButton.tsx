"use client";
import { useState } from "react";

export default function SyncButton() {
  const [loading, setLoading] = useState(false);

  async function handleClick() {
    setLoading(true);
    await fetch("/api/sync", { method: "POST" });
    setLoading(false);
    window.location.reload();
  }

  return (
    <button className="btn btn-ghost" onClick={handleClick} disabled={loading}>
      {loading ? "Sincronizando..." : "↻ Sync showsaryel.com"}
    </button>
  );
}
