import makeWASocket, { useMultiFileAuthState, DisconnectReason } from "@whiskeysockets/baileys";
import axios from "axios";
import pino from "pino";
import qrcode from "qrcode-terminal";
import { CONFIG } from './config.js';

function maybeLogGroupId(msg) {
  if (!CONFIG.SETUP_MODE) return;

  const jid = msg.key?.remoteJid;
  if (!jid) return;

  if (jid.endsWith('@g.us')) {
    console.log('📌 GROUP ID:', jid);
  } else {
    console.log('📩 PRIVATE CHAT ID:', jid);
  }
}

console.log("Allowed groups:", [...CONFIG.ALLOWED_GROUPS]);

async function startBot() {
    const { state, saveCreds } = await useMultiFileAuthState("auth");

    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: false, // We handle QR manually
        syncFullHistory: false,
        shouldSyncHistoryMessage: () => false,
        shouldLoadHistoryMsg: () => false,
        getMessage: async () => null,
        logger: pino({ level: 'error' }),
        markOnlineOnConnect: false
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log("SCAN THIS QR:\n");
            qrcode.generate(qr, { small: true });
        }

        if (connection === "close") {
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log("Connection closed due to ", lastDisconnect?.error, ", reconnecting ", shouldReconnect);
            if (shouldReconnect) {
                startBot();
            }
        } else if (connection === "open") {
            console.log("WhatsApp connection established.");
        }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        if (type !== "notify") return;

        for (const msg of messages) {
            maybeLogGroupId(msg);
            if (!msg.message) continue;
            const chatId = msg.key.remoteJid;

            // ❌ Ignore if not in an approved group
            if (!CONFIG.ALLOWED_GROUPS.has(chatId)) continue;

            const text =
                msg.message.conversation ||
                msg.message.extendedTextMessage?.text ||
                "";

            if (!text.toLowerCase().includes("@bot")) return;

            console.log("Bot trigger:", text);
            let inputForPython = text.replace(/@bot/gi, "").trim();

            // Check if message is a reply (quoted)
            const quoted = msg.message.extendedTextMessage?.contextInfo?.quotedMessage;
            if (quoted) {
                const quotedText =
                    quoted.conversation ||
                    quoted.extendedTextMessage?.text ||
                    quoted.imageMessage?.caption ||
                    null;

                if (quotedText) {
                    console.log("Using quoted text instead:", quotedText);
                    inputForPython = quotedText.trim();
                }
            }

            // ---- Send the entire message to Python ----
            try {
                const response = await axios.post(CONFIG.PYTHON_API, {
                    text: inputForPython,
                    sender: msg.pushName || "Unknown",
                    chat_id: chatId
                });
                console.log("FULL PYTHON RESPONSE:", response.data);

                const replyText = response.data.summary ?? null;

                if (response.data.status?.toString().toLowerCase() === "ok" && replyText) {
                    console.log("Reply:", replyText);
                    await sock.sendMessage(chatId, {
                        text: replyText,
                        quoted: msg
                    });
                } else {
                    console.log("Error status:", response.data.status);
                    console.log("Message:", response.data.message);
                    await sock.sendMessage(chatId, { text: 'Error processing request' });
                }

            } catch (err) {
                console.error("Python error:", err.message);
                await sock.sendMessage(chatId, { text: 'Summarizer service unavailable' });
            }
        }
    });
}

startBot();