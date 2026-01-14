import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  jidNormalizedUser,
} from "@whiskeysockets/baileys"
import axios from "axios"
import pino from "pino"
import express from "express"
import { Boom } from "@hapi/boom"
import {CONFIG} from "./config.js";

const API_BASE_URL = process.env.API_BASE_URL || "http://localhost:8000"
const PORT = Number(process.env.PORT || 3000)
const SESSION = process.env.WHATSAPP_SESSION || "default"

const logger = pino({ level: process.env.LOG_LEVEL || "info" })

let sock = null


// --------------------
// HTTP CLIENT
// --------------------
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10_000,
})

// --------------------
// NORMALIZATION
// --------------------
function normalizeMessage(msg) {
  const m = msg.message
  if (!m) return null

  if (m.conversation) return m.conversation
  if (m.extendedTextMessage?.text) return m.extendedTextMessage.text
  if (m.imageMessage?.caption) return m.imageMessage.caption
  if (m.videoMessage?.caption) return m.videoMessage.caption

  return null
}

function buildEvent(msg) {
  const isGroup = msg.key.remoteJid.endsWith("@g.us")

  return {
    message_id: msg.key.id,
    timestamp: msg.messageTimestamp,
    chat_id: msg.key.remoteJid,
    sender_id: isGroup
      ? msg.key.participant
      : msg.key.remoteJid,
    is_group: isGroup,
    text: normalizeMessage(msg),
    raw: msg, // optional but useful
  }
}

// --------------------
// MAIN SOCKET
// --------------------
async function startSocket() {
  const { state, saveCreds } = await useMultiFileAuthState(`auth`)

  const { version } = await fetchLatestBaileysVersion()

  sock = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: true, //TODO: test if we need to handle QR code manually
    generateHighQualityLinkPreview: true,
  })

  sock.ev.on("creds.update", saveCreds)

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect } = update

    if (connection === "close") {
      const reason = new Boom(lastDisconnect?.error)?.output?.statusCode

      logger.warn({ reason }, "connection closed")

      if (reason !== DisconnectReason.loggedOut) {
        startSocket()
      }
    }

    if (connection === "open") {
      logger.info("WhatsApp connected")
    }
  })

  // --------------------
  // INCOMING MESSAGES
  // --------------------
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return

    for (const msg of messages) {
      if (!msg.message) continue
      if (msg.key.fromMe) continue

      const event = buildEvent(msg)
      if (!event?.text) continue

      try {
        await api.post("/whatsapp/events", event)
      } catch (err) {
        logger.error(err, "failed sending event to API")
      }
    }
  })
}

// --------------------
// EXPRESS API (OUTBOUND)
// --------------------
const app = express()
app.use(express.json())

app.post("/send", async (req, res) => {
  const { to, text } = req.body

  if (!sock) {
    return res.status(503).json({ error: "WhatsApp not ready" })
  }

  try {
    await sock.sendMessage(jidNormalizedUser(to), { text })
    res.json({ ok: true })
  } catch (err) {
    logger.error(err)
    res.status(500).json({ error: "send failed" })
  }
})

// --------------------
// BOOT
// --------------------
app.listen(PORT, () => {
  logger.info(`Gateway listening on ${PORT}`)
})

startSocket().catch((err) => {
  logger.error(err, "failed to start socket")
})
