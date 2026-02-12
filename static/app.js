const outEl = document.getElementById("out");

function escapeHtml(s) {
    return String(s ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

function openPdfUrl(url) {
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
}

function shouldIgnoreOpen(e) {
    if (e.target && e.target.closest && e.target.closest("a.save-chip")) return true;
    const sel = (window.getSelection && window.getSelection().toString().trim()) || "";
    if (sel) return true;
    return false;
}

function attachOpenHandlers(pre) {
    pre.addEventListener("click", (e) => {
        if (shouldIgnoreOpen(e)) return;
    });

    pre.addEventListener("dblclick", (e) => {
        if (shouldIgnoreOpen(e)) return;
        openPdfUrl(pre.dataset.viewUrl);
    });
}

function showPre(htmlInsidePre, viewUrl = "", downloadUrl = "") {
    outEl.innerHTML = "";
    const pre = document.createElement("pre");
    pre.className = "full";
    pre.innerHTML = htmlInsidePre;

    if (viewUrl) pre.dataset.viewUrl = viewUrl;
    if (downloadUrl) pre.dataset.downloadUrl = downloadUrl;

    attachOpenHandlers(pre);

    outEl.appendChild(pre);
    return pre;
}

function appendPre(htmlInsidePre, fullWidth = false, viewUrl = "", downloadUrl = "") {
    const pre = document.createElement("pre");
    if (fullWidth) pre.classList.add("full");
    pre.innerHTML = htmlInsidePre;

    if (viewUrl) pre.dataset.viewUrl = viewUrl;
    if (downloadUrl) pre.dataset.downloadUrl = downloadUrl;

    outEl.appendChild(pre);

    attachOpenHandlers(pre);
    return pre;
}

function clearLog() {
    showPre("Cleared.");
    window.MetaPanel?.clear?.();
}

function makeProcessingBlock(filename) {
    return `⏳ Processing: ${escapeHtml(filename)}\n`;
}

function formatIban(v) {
    const raw = String(v ?? "").trim();
    if (!raw) return raw;

    const compact = raw.replace(/\s+/g, "").toUpperCase();
    if (!compact.startsWith("TR") || compact.length < 10) return raw;
    return compact;
}

function formatData(data) {
    if (!data || typeof data !== "object") return escapeHtml(JSON.stringify(data));

    const order = [
        "tr_status",
        "sender_name",
        "receiver_name",
        "receiver_iban",
        "amount",
        "transaction_time",
        "receipt_no",
        "transaction_ref",
        "error",
    ];

    const pad = 18;

    const statusDisplay = (v) => {
        const raw = String(v ?? "");
        const st = raw.toLowerCase();

        if (st.includes("completed")) return { text: "✅", color: "var(--c-ok)" };
        if (!st || st.includes("unknown")) return { text: raw || "unknown-manually", color: "var(--c-warn)" };
        if (st.includes("pending")) return { text: raw, color: "var(--c-warn)" };
        return { text: raw, color: "var(--c-bad)" };
    };

    const valueWrap = (k, v) => {
        if (k === "tr_status") {
            const sd = statusDisplay(v);
            return `<span style="color:${sd.color};font-weight:800">${escapeHtml(sd.text)}</span>`;
        }

        if (k === "receiver_name" || k === "receiver_iban" || k === "amount" || k === "transaction_time") {
            return `<span class="imp">${escapeHtml(v)}</span>`;
        }

        return `<span style="color:var(--c-val)">${escapeHtml(v)}</span>`;
    };

    let out = "";
    for (const k of order) {
        if (!(k in data)) continue;

        const key = (k + "").padEnd(pad, " ");
        let val = data[k];
        if (k === "receiver_iban") val = formatIban(val);

        out += `${escapeHtml(key)}${valueWrap(k, val)}\n`;
    }

    return out.trimEnd();
}

function saveChipHtml(downloadUrl) {
    if (!downloadUrl) return "";
    return `<a class="save-chip" href="${escapeHtml(downloadUrl)}" target="_blank" rel="noopener noreferrer">SAVE</a>`;
}

function headerBlock(filename, detected, downloadUrl) {
    const bank = detected?.bank ?? "Unknown";
    const variant = detected?.variant || "no variant";

    return (
        `FILE :  <span class="imp">${escapeHtml(filename)}</span>\n` +
        `BANK: <span class="imp">${escapeHtml(bank)} (${escapeHtml(variant)})</span>` +
        `${saveChipHtml(downloadUrl)}` +
        `\n\n`
    );
}

async function checkPdf() {
    const input = document.getElementById("checkFile");
    const f = input?.files?.[0];
    if (!f) return;

    showPre("⏳ Uploading...");
    window.MetaPanel?.clear?.();

    const fd = new FormData();
    fd.append("file", f);

    try {
        const r = await fetch("/check", { method: "POST", body: fd });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();

        showPre(
            headerBlock(f.name, j.detected, j.download_url || "") + formatData(j.data),
            j.view_url || "",
            j.download_url || ""
        );

        window.MetaPanel?.render?.(j.meta || null);
    } catch (e) {
        showPre(`❌ Error\n${escapeHtml(String(e))}\n`);
        window.MetaPanel?.clear?.();
    } finally {
        if (input) input.value = "";
    }
}

/**
 * Batch parallelism:
 * - Render-friendly: cap concurrency (default 4)
 * - UI stable: create blocks in original order, then fill them as results complete
 */
const BATCH_CONCURRENCY = 4;

async function checkPdfBatch() {
    const input = document.getElementById("checkFiles");
    const files = Array.from(input?.files || []);
    if (!files.length) return;

    outEl.innerHTML = "";
    window.MetaPanel?.clear?.(); // no meta in batch for now
    appendPre(`Batch selected: <span class="imp">${files.length}</span>\n\n`, true);

    // Create output blocks in the same order as selected files
    const blocks = files.map((f) => appendPre(makeProcessingBlock(f.name), false, "", ""));

    // Shared index for the pool
    let nextIndex = 0;

    async function processOne(i) {
        const f = files[i];
        const fd = new FormData();
        fd.append("file", f);

        try {
            const r = await fetch("/check", { method: "POST", body: fd });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const j = await r.json();

            blocks[i].innerHTML = headerBlock(f.name, j.detected, j.download_url || "") + formatData(j.data);
            blocks[i].dataset.viewUrl = j.view_url || "";
            blocks[i].dataset.downloadUrl = j.download_url || "";
        } catch (e) {
            blocks[i].innerHTML = `❌ Error processing ${escapeHtml(f.name)}\n${escapeHtml(String(e))}\n`;
        }
    }

    async function worker() {
        while (true) {
            const i = nextIndex;
            nextIndex += 1;
            if (i >= files.length) return;
            await processOne(i);
        }
    }

    // Start N workers (cap by number of files)
    const n = Math.max(1, Math.min(BATCH_CONCURRENCY, files.length));
    await Promise.all(Array.from({ length: n }, () => worker()));

    if (input) input.value = "";
}

document.getElementById("checkFile")?.addEventListener("change", checkPdf);
document.getElementById("checkFiles")?.addEventListener("change", checkPdfBatch);
document.getElementById("clearBtn")?.addEventListener("click", clearLog);

// ===== Palette button (professional variations only) =====
const PRO_PALETTES = [
    { "--c-key": "#D1D5DB", "--c-val": "#D1D5DB", "--c-imp": "#60A5FA", "--c-chip": "#86EFAC", "--c-ok": "#34D399", "--c-warn": "#FBBF24", "--c-bad": "#F87171" },
    { "--c-key": "#CBD5E1", "--c-val": "#CBD5E1", "--c-imp": "#93C5FD", "--c-chip": "#A7F3D0", "--c-ok": "#22C55E", "--c-warn": "#F59E0B", "--c-bad": "#EF4444" },
    { "--c-key": "#D4D4D8", "--c-val": "#D4D4D8", "--c-imp": "#7DD3FC", "--c-chip": "#86EFAC", "--c-ok": "#34D399", "--c-warn": "#FCD34D", "--c-bad": "#FB7185" },
    { "--c-key": "#E5E7EB", "--c-val": "#E5E7EB", "--c-imp": "#A5B4FC", "--c-chip": "#93C5FD", "--c-ok": "#10B981", "--c-warn": "#FBBF24", "--c-bad": "#F87171" },
];

let paletteIndex = 0;

function applyPalette(pal) {
    const root = document.documentElement;
    for (const k of Object.keys(pal)) root.style.setProperty(k, pal[k]);
}

document.getElementById("randomColorsBtn")?.addEventListener("click", () => {
    paletteIndex = (paletteIndex + 1) % PRO_PALETTES.length;
    applyPalette(PRO_PALETTES[paletteIndex]);
});
