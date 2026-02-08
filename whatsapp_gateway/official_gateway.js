import "dotenv/config";
import axios from "axios";
import crypto from "crypto";
import express from "express";
import pino from "pino";
import { CONFIG } from "./config.js";

const PORT = Number(process.env.OFFICIAL_GATEWAY_PORT || process.env.PORT || 3000);
const VERIFY_TOKEN = process.env.WHATSAPP_WEBHOOK_VERIFY_TOKEN || "";
const APP_SECRET = process.env.WHATSAPP_APP_SECRET || "";
const CLOUD_TOKEN = process.env.WHATSAPP_CLOUD_TOKEN || "";
const PHONE_NUMBER_ID = process.env.WHATSAPP_PHONE_NUMBER_ID || "";
const GRAPH_VERSION = process.env.WHATSAPP_GRAPH_VERSION || "v24.0";

const logger = pino({ level: process.env.LOG_LEVEL || "info" });
const app = express();
const rawBodySaver = (req, _res, buf) => {
  req.rawBody = buf;
};

function normalizePhone(value) {
  if (!value) return "";
  return String(value).replace(/\D/g, "");
}

function normalizeChatId(value) {
  const digits = normalizePhone(value);
  return digits ? `${digits}@s.whatsapp.net` : String(value);
}

function extractText(message) {
  if (!message || typeof message !== "object") return null;
  if (message.type === "text" && message.text?.body) {
    return message.text.body;
  }
  if (message.type && message[message.type]?.caption) {
    return message[message.type].caption;
  }
  if (message.button?.text) {
    return message.button.text;
  }
  if (message.interactive?.button_reply?.title) {
    return message.interactive.button_reply.title;
  }
  if (message.interactive?.list_reply?.title) {
    return message.interactive.list_reply.title;
  }
  return null;
}

function extractContact(message) {
  if (!message || typeof message !== "object") return null;
  if (message.type !== "contacts") return null;
  const contacts = Array.isArray(message.contacts) ? message.contacts : [];
  if (!contacts.length) return null;

  const allNumbers = [];
  for (const contact of contacts) {
    const phones = Array.isArray(contact?.phones) ? contact.phones : [];
    allNumbers.push(
      ...phones
        .map((phone) =>
          normalizePhone(phone?.wa_id || phone?.phone || phone?.value || "")
        )
        .filter(Boolean)
    );
  }
  const normalizedPhones = [...new Set(allNumbers)];

  const first = contacts[0] || {};
  const displayName = contacts.length === 1
    ? (
        first.name?.formatted_name ||
        [first.name?.first_name, first.name?.last_name].filter(Boolean).join(" ") ||
        null
      )
    : null;

  if (!normalizedPhones.length) return null;
  const contactPhone = normalizedPhones.length > 1 ? normalizedPhones : normalizedPhones[0];

  return {
    contact_name: displayName,
    contact_phone: contactPhone,
  };
}

function timingSafeEqual(a, b) {
  const aBuf = Buffer.from(a);
  const bBuf = Buffer.from(b);
  if (aBuf.length !== bBuf.length) return false;
  return crypto.timingSafeEqual(aBuf, bBuf);
}

function verifySignature(req) {
  if (!APP_SECRET) {
    logger.error("WHATSAPP_APP_SECRET not set; rejecting webhook");
    return false;
  }
  const signature = req.get("x-hub-signature-256") || "";
  if (!signature.startsWith("sha256=")) {
    return false;
  }
  if (!req.rawBody || !Buffer.isBuffer(req.rawBody)) {
    return false;
  }
  const expected =
    "sha256=" +
    crypto.createHmac("sha256", APP_SECRET).update(req.rawBody).digest("hex");
  return timingSafeEqual(signature, expected);
}

function buildEvents(payload) {
  const events = [];
  const entries = Array.isArray(payload?.entry) ? payload.entry : [];

  for (const entry of entries) {
    const changes = Array.isArray(entry?.changes) ? entry.changes : [];
    for (const change of changes) {
      const value = change?.value || {};
      const contacts = Array.isArray(value.contacts) ? value.contacts : [];
      const messages = Array.isArray(value.messages) ? value.messages : [];

      for (const message of messages) {
        const from = message?.from || contacts[0]?.wa_id;
        if (!from) continue;

        const text = extractText(message);
        const contact = extractContact(message);
        if (!text && !contact?.contact_phone) continue;
        const quotedMessageId = message?.context?.id || null;

        const senderName = contacts[0]?.profile?.name || null;
        const timestamp = Number(message?.timestamp) || Math.floor(Date.now() / 1000);
        const chatId = normalizeChatId(from);

        events.push({
          message_id: message?.id || "",
          timestamp,
          chat_id: chatId,
          sender_id: chatId,
          is_group: false,
          text,
          quoted_text: null,
          quoted_message_id: quotedMessageId,
          sender_name: senderName,
          contact_name: contact?.contact_name || null,
          contact_phone: contact?.contact_phone || null,
          raw: {
            message,
            contacts,
            metadata: value.metadata,
          },
        });
      }
    }
  }

  return events;
}

function summarizeWebhook(payload) {
  const entries = Array.isArray(payload?.entry) ? payload.entry : [];
  let changesCount = 0;
  let messagesCount = 0;
  let statusesCount = 0;

  for (const entry of entries) {
    const changes = Array.isArray(entry?.changes) ? entry.changes : [];
    changesCount += changes.length;
    for (const change of changes) {
      const value = change?.value || {};
      messagesCount += Array.isArray(value.messages) ? value.messages.length : 0;
      statusesCount += Array.isArray(value.statuses) ? value.statuses.length : 0;
    }
  }

  return {
    object: payload?.object || null,
    entries: entries.length,
    changes: changesCount,
    messages: messagesCount,
    statuses: statusesCount,
  };
}

async function dispatchEvent(event) {
  if (!CONFIG.EVENT_TARGETS.length) {
    logger.warn("No WHATSAPP_EVENT_TARGETS configured");
    return;
  }
  const results = await Promise.allSettled(
    CONFIG.EVENT_TARGETS.map((target) =>
      axios.post(target, event, { timeout: 60_000 })
    )
  );
  const firstFailureIndex = results.findIndex(
    (result) => result.status === "rejected"
  );
  if (firstFailureIndex !== -1) {
    logger.error(
      { err: results[firstFailureIndex].reason },
      "failed sending event to %s",
      CONFIG.EVENT_TARGETS[firstFailureIndex]
    );
  }
}

function handleWebhookVerify(req, res) {
  const mode = req.query["hub.mode"];
  const token = req.query["hub.verify_token"];
  const challenge = req.query["hub.challenge"];

  if (mode === "subscribe" && token === VERIFY_TOKEN) {
    logger.info("Webhook verified");
    return res.status(200).send(challenge);
  }
  return res.status(403).end();
}

function handleWebhookPost(req, res) {
  if (!verifySignature(req)) {
    logger.warn("Invalid webhook signature");
    return res.status(403).end();
  }
  logger.debug("Webhook signature verified");

  const payload = req.body;
  if (!payload || typeof payload !== "object") {
    logger.warn("Invalid JSON payload");
    return res.status(400).json({ status: "error", message: "Invalid JSON payload" });
  }
  logger.info({ webhook: summarizeWebhook(payload) }, "Webhook received");

  const events = buildEvents(payload);
  if (events.length) {
    for (const event of events) {
      logger.info(
        {
          message_id: event.message_id,
          chat_id: event.chat_id,
          sender_name: event.sender_name,
          text: event.text,
        },
        "Inbound message event"
      );
    }
  }
  if (!events.length) {
    logger.info("Webhook received with no dispatchable text message");
    return res.status(200).json({ status: "ok" });
  }

  Promise.allSettled(events.map((event) => dispatchEvent(event))).catch((err) => {
    logger.error({ err }, "dispatch failed");
  });

  return res.status(200).json({ status: "ok" });
}

app.get("/", handleWebhookVerify);
app.post("/", express.json({ verify: rawBodySaver }), handleWebhookPost);

app.use(express.json());

app.post("/send", async (req, res) => {
  const { to, text, quoted_message_id: quotedMessageId } = req.body || {};
  if (!to || !text) {
    return res.status(400).json({ status: "error", error: "to and text required" });
  }

  if (!CLOUD_TOKEN || !PHONE_NUMBER_ID) {
    logger.error("WHATSAPP_CLOUD_TOKEN or WHATSAPP_PHONE_NUMBER_ID not set");
    return res.status(500).json({ status: "error", error: "gateway not configured" });
  }

  const toNumber = normalizePhone(to);
  if (!toNumber) {
    return res.status(400).json({ status: "error", error: "invalid recipient" });
  }

  const payload = {
    messaging_product: "whatsapp",
    to: toNumber,
    type: "text",
    text: { body: text },
  };

  if (quotedMessageId) {
    payload.context = { message_id: quotedMessageId };
  }

  try {
    const cloudResp = await axios.post(
      `https://graph.facebook.com/${GRAPH_VERSION}/${PHONE_NUMBER_ID}/messages`,
      payload,
      {
        headers: {
          Authorization: `Bearer ${CLOUD_TOKEN}`,
        },
        timeout: 15_000,
      }
    );
    const sentMessageId = cloudResp?.data?.messages?.[0]?.id || null;
    return res.json({ status: "ok", message_id: sentMessageId });
  } catch (err) {
    logger.error({ err }, "Cloud API send failed");
    return res.status(500).json({ status: "error", error: "send failed" });
  }
});

app.listen(PORT, () => {
  logger.info(`Official gateway listening on ${PORT}`);
});
