import 'dotenv/config';

export const CONFIG = {
  SETUP_MODE: process.env.SETUP_MODE === 'true',
  PYTHON_API: process.env.PYTHON_API || "http://summarizer:5001/process",
  ALLOWED_GROUPS: new Set(
      (process.env.ALLOWED_GROUPS || "")
          .split(",")
          .map(s => s.trim())
          .filter(Boolean)
  )
};
