"use client";
import { useState } from "react";

export default function ToggleButton({ eventId, active }: { eventId: number; active: boolean }) {
  const [current, setCurrent] = useState(active);

  async function handleClick() {
    await fetch(`/api/events/${eventId}`, { method: "PATCH" });
    setCurrent(!current);
    window.location.reload();
  }

  return (
    <button className="btn btn-ghost btn-sm" onClick={handleClick}>
      {current ? "⏸ Pausar" : "▶ Activar"}
    </button>
  );
}
