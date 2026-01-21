import 'dotenv/config';

export const CONFIG = {
  SETUP_MODE: process.env.SETUP_MODE === 'true',
  EVENT_TARGETS: (process.env.WHATSAPP_EVENT_TARGETS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
  FORWARD_RAW: process.env.WHATSAPP_FORWARD_RAW === "true",
};
