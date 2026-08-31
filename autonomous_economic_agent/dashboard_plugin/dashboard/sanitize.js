/** Marketplace/job display sanitizer. Never interpret HTML. */
(function (root) {
  const TAG_RE = /<[^>]*>/g;
  const CONTROL_RE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;

  function safeDisplayText(value, maxLen) {
    const limit = typeof maxLen === "number" ? maxLen : 240;
    let text = value == null ? "" : String(value);
    text = text.replace(CONTROL_RE, "");
    text = text.replace(TAG_RE, "");
    text = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
    if (text.length > limit) {
      text = text.slice(0, limit - 1) + "…";
    }
    return text;
  }

  root.AEA_SAFE_DISPLAY = { safeDisplayText };
})(typeof window !== "undefined" ? window : globalThis);
