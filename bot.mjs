import makeWASocket, { useMultiFileAuthState, DisconnectReason } from "@whiskeysockets/baileys";
import axios from "axios";
import pino from "pino";
import qrcode from "qrcode-terminal";

const PYTHON_API = process.env.FLASK_URL;
// const PYTHON_API = "http://localhost:5001/process";

// groups where the bot should respond
// Example format: "1234567890-123456@g.us"
const ALLOWED_GROUPS = new Set([
    'REDACTED_GROUP_ID',
    'REDACTED_GROUP_ID'
]);

async function startBot() {
    const { state, saveCreds } = await useMultiFileAuthState("auth");

    const sock = makeWASocket({
        auth: state,
        // 🚫 Prevent history sync

    // 🚫 prevent full history sync
    syncFullHistory: false,

    // 🚫 prevent incremental history sync (offline nodes)
    shouldSyncHistoryMessage: () => false,
    shouldLoadHistoryMsg: () => false,
    getMessage: async () => null, // prevents Baileys from trying to fetch missing messages

    // Optional quiet logs
    logger: pino({ level: 'error' }),

    markOnlineOnConnect: false
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", (update) => {
        console.log("CONNECTION UPDATE:", update);
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log("SCAN THIS QR:\n");
            qrcode.generate(qr, { small: true });
        }

        if (connection === "close") {
            const reason = lastDisconnect?.error?.output?.statusCode;
            console.log("Connection closed:", reason);
        } else if (connection === "open") {
            console.log("WhatsApp connection established.");
        }
    });

    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        if (type !== "notify") return;

        for (const msg of messages) {
            if (!msg.message) continue;
            const chatId = msg.key.remoteJid;

            // ❌ Ignore if not in an approved group
            if (!ALLOWED_GROUPS.has(chatId)) continue;


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
            // Extract the quoted text from different possible message types
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
            let replyText = null;
            try {
                const response = await axios.post(PYTHON_API, {
                    text: inputForPython,
                    sender: msg.pushName || "Unknown",
                    chat_id: chatId
                });
                console.log("FULL PYTHON RESPONSE:", response.data);

                // Python decides if we should reply
                const replyText = response.data.summary ?? null;
                if (response.data.status.toString().toLowerCase() === "ok" && replyText) {
                    console.log("Reply:", replyText);
                    await sock.sendMessage(chatId, { text: replyText });
                }
                else {
                    console.log("status:", response.data.status);
                    console.log("message", response.data.message)
                    console.log("summary", response.data.summary)

                    await sock.sendMessage(chatId, { text: 'Error' });
                }

            } catch (err) {
                console.error("Python error:", err.message);
                replyText = null; // fail silently
            }

            // ---- Only reply if python says so ----
            if (replyText) {
                await sock.sendMessage(chatId, {
                    text: replyText,
                    quoted: msg
                });
            }
        }
    });
}

startBot();
