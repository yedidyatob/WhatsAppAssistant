import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  jidNormalizedUser,
} from "@whiskeysockets/baileys"
import pino from "pino"
import express from "express"
import { Boom } from "@hapi/boom"
import {CONFIG} from "./config.js";
import axios from "axios"
import qrcode from "qrcode-terminal"

const PORT = Number(process.env.PORT || 3000)
const logger = pino({ level: process.env.LOG_LEVEL || "error" })

let sock = null

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function randomDelayMs(minMs = 500, maxMs = 2000) {
  return Math.floor(minMs + Math.random() * (maxMs - minMs))
}


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

function extractQuotedText(msg) {
  const quoted = msg.message?.extendedTextMessage?.contextInfo?.quotedMessage
  if (!quoted) return null

  return (
    quoted.conversation ||
    quoted.extendedTextMessage?.text ||
    quoted.imageMessage?.caption ||
    quoted.videoMessage?.caption ||
    null
  )
}

function extractContact(msg) {
  const contactMessage = msg.message?.contactMessage
  const contactsArray = msg.message?.contactsArrayMessage?.contacts
  const contact = contactMessage || (Array.isArray(contactsArray) ? contactsArray[0] : null)
  if (!contact) return null

  const vcard = contact.vcard || ""
  const displayName = contact.displayName || null
  const waidMatch = vcard.match(/waid=(\d+)/i)
  const telMatch = vcard.match(/TEL[^:]*:([+0-9]+)/i)
  const rawNumber = (waidMatch && waidMatch[1]) || (telMatch && telMatch[1]) || null
  const digits = rawNumber ? rawNumber.replace(/\D/g, "") : null

  return {
    contact_name: displayName,
    contact_phone: digits,
  }
}

function buildEvent(msg) {
  const isGroup = msg.key.remoteJid.endsWith("@g.us")
  const contact = extractContact(msg)

  return {
    message_id: msg.key.id,
    timestamp: Number(msg.messageTimestamp || Date.now() / 1000),
    chat_id: msg.key.remoteJid,
    sender_id: isGroup
      ? msg.key.participant
      : msg.key.remoteJid,
    is_group: isGroup,
    text: normalizeMessage(msg),
    quoted_text: extractQuotedText(msg),
    sender_name: msg.pushName || null,
    contact_name: contact?.contact_name || null,
    contact_phone: contact?.contact_phone || null,
    raw: msg,
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
    printQRInTerminal: false,
    generateHighQualityLinkPreview: true,
  })

  sock.ev.on("creds.update", saveCreds)

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update

    if (qr) {
      qrcode.generate(qr, { small: true })
    }

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

      const event = buildEvent(msg)
      if (!event?.text && !event?.quoted_text && !event?.contact_phone) continue

      if (!CONFIG.EVENT_TARGETS.length) {
        logger.warn("No WHATSAPP_EVENT_TARGETS configured")
        continue
      }

      await Promise.allSettled(
        CONFIG.EVENT_TARGETS.map((target) =>
          axios.post(target, event, { timeout: 60_000 })
        )
      ).then((results) => {
        const firstFailureIndex = results.findIndex(
          (result) => result.status === "rejected"
        )
        if (firstFailureIndex !== -1) {
          logger.error(
            { err: results[firstFailureIndex].reason },
            "failed sending event to %s",
            CONFIG.EVENT_TARGETS[firstFailureIndex]
          )
        }
      })
    }
  })
}

// --------------------
// EXPRESS API (OUTBOUND)
// --------------------
const app = express()
app.use(express.json())

app.post("/send", async (req, res) => {
  // TODO: Security - add auth/signature checks for gateway inbound requests.
  const { to, text } = req.body

  if (!sock) {
    return res.status(503).json({ status: "error", error: "WhatsApp not ready" })
  }

  try {
    await sleep(randomDelayMs())
    await sock.sendMessage(jidNormalizedUser(to), { text })
    res.json({ status: "ok" })
  } catch (err) {
    logger.error(err)
    res.status(500).json({ status: "error", error: "send failed" })
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
