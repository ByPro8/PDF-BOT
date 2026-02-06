(function () {
    function ensureMetaPre() {
        const out = document.getElementById("out");
        if (!out) return null;

        let pre = document.getElementById("metaPre");
        if (pre) return pre;

        const tpl = document.getElementById("metaPanelTemplate");
        if (tpl && tpl.content && tpl.content.firstElementChild) {
            pre = tpl.content.firstElementChild.cloneNode(true);
        } else {
            pre = document.createElement("pre");
            pre.className = "full meta-pre";
        }

        pre.id = "metaPre";
        out.appendChild(pre);
        return pre;
    }

    function clear() {
        const pre = document.getElementById("metaPre");
        if (pre) pre.remove();
    }

    function render(meta) {
        const out = document.getElementById("out");
        if (!out) return;

        // If batch output is active, do nothing (we focus single file only for now)
        const pres = Array.from(out.querySelectorAll("pre"));
        const looksLikeBatch = pres.length > 1 && pres.some((p) => !p.classList.contains("full"));
        if (looksLikeBatch) return;

        if (!meta) {
            clear();
            return;
        }

        const python = meta.python || "";
        const exif = meta.exiftool || "";

        const block =
            "==== METADATA (Python) ====\n" +
            (python || "(none)") +
            "\n\n" +
            "==== METADATA (ExifTool) ====\n" +
            (exif || "(none)");

        const pre = ensureMetaPre();
        if (!pre) return;
        pre.textContent = block;
    }

    window.MetaPanel = { render, clear };
})();
