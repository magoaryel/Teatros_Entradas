async function post(token: string, chatId: string, text: string) {
  await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" }),
  });
}

function creds() {
  return {
    token: process.env.TELEGRAM_TOKEN ?? "",
    chatId: process.env.TELEGRAM_CHAT_ID ?? "",
  };
}

export async function notifySales(
  eventName: string,
  venue: string,
  sessionLabel: string,
  soldNow: number,
  soldBefore: number,
  capacity: number
) {
  const { token, chatId } = creds();
  if (!token || !chatId) return;
  const diff = soldNow - soldBefore;
  const available = capacity - soldNow;
  const text =
    `🎭 <b>${eventName}</b>\n` +
    `📍 ${venue}\n` +
    `📅 ${sessionLabel}\n\n` +
    `🎟 Vendidas: <b>${soldNow}</b> / ${capacity}\n` +
    `✅ Disponibles: <b>${available}</b>\n` +
    `📈 Nuevas ventas: +${diff}`;
  await post(token, chatId, text);
}

export async function notifySoldOut(
  eventName: string,
  venue: string,
  sessionLabel: string
) {
  const { token, chatId } = creds();
  if (!token || !chatId) return;
  const text =
    `🔴 <b>¡AGOTADO!</b>\n` +
    `🎭 ${eventName}\n📍 ${venue}\n📅 ${sessionLabel}`;
  await post(token, chatId, text);
}

export async function sendTest() {
  const { token, chatId } = creds();
  if (!token || !chatId) return false;
  try {
    const res = await fetch(
      `https://api.telegram.org/bot${token}/sendMessage`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_id: chatId,
          text: "✅ Test desde <b>Monitor de Entradas</b>.",
          parse_mode: "HTML",
        }),
      }
    );
    return res.ok;
  } catch {
    return false;
  }
}
