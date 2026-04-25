"use client";

export default function DeleteButton({ eventId }: { eventId: number }) {
  async function handleClick() {
    if (!confirm("¿Eliminar este evento y todos sus datos?")) return;
    await fetch(`/api/events/${eventId}`, { method: "DELETE" });
    window.location.reload();
  }

  return (
    <button className="btn btn-danger btn-sm" onClick={handleClick} title="Eliminar evento">
      🗑
    </button>
  );
}
