import 'dotenv/config';

export const CONFIG = {
  EVENT_TARGETS: (process.env.WHATSAPP_EVENT_TARGETS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
};
