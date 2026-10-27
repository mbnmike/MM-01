(() => {
  "use strict";

  const cfgEl = document.getElementById("editor-config");
  if (!cfgEl) return;
  const cfg = JSON.parse(cfgEl.textContent);
  const $ = (sel, root = document) => root.querySelector(sel);

  const form = document.getElementById("post_form");
  const title = $("#id_title");
  const excerpt = $("#id_excerpt");
  const body = $("#id_body");
  const box = $("[data-editor]");
  const frame = $("[data-preview-frame]");
  const stateEl = $("[data-save-state]");
  const fileInput = $("[data-file-input]");
  const uploadStatus = $("[data-upload-status]");
  const wordcount = $("[data-wordcount]");
  const csrf = form.querySelector("[name=csrfmiddlewaretoken]").value;

  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function send(url, data) {
    const res = await fetch(url, {
      method: data ? "POST" : "GET",
      body: data,
      headers: { "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    });
    if (res.redirected || !(res.headers.get("content-type") || "").includes("json")) {
      throw new Error("Your login session ended. Log in again in another tab, then save.");
    }
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || `Request failed (${res.status})`);
    return json;
  }

  // ----- Unsaved-change tracking and server autosave -----

  let dirty = false;
  let submitting = false;
  let backupLabel = "";
  let autosaveTimer = null;
  let lastAutosaveAt = Date.now();
  const snapshot = () => [title.value, excerpt.value, body.value].join("\u0000");
  let lastAutosaved = snapshot();

  function setState(text, tone = "") {
    stateEl.textContent = text;
    stateEl.dataset.tone = tone;
  }

  function markDirty() {
    dirty = true;
    setState(backupLabel ? `Unsaved changes · backed up ${backupLabel}` : "Unsaved changes", "warn");
    scheduleAutosave();
  }

  function scheduleAutosave() {
    clearTimeout(autosaveTimer);
    const overdue = Date.now() - lastAutosaveAt > 30000;
    autosaveTimer = setTimeout(autosave, overdue ? 0 : 4000);
  }

  async function autosave() {
    const snap = snapshot();
    if (submitting || snap === lastAutosaved || (!title.value.trim() && !body.value.trim())) return;
    lastAutosaveAt = Date.now();
    const data = new FormData();
    if (cfg.postId) data.append("post_id", cfg.postId);
    data.append("title", title.value);
    data.append("excerpt", excerpt.value);
    data.append("body", body.value);
    try {
      const res = await send(cfg.autosaveUrl, data);
      lastAutosaved = snap;
      backupLabel = res.savedAt;
      if (dirty) setState(`Unsaved changes · backed up ${backupLabel}`, "warn");
    } catch (err) {
      setState(`Backup failed: ${err.message}`, "error");
    }
  }

  form.addEventListener("input", (e) => { if (e.target !== fileInput) markDirty(); });
  form.addEventListener("change", (e) => { if (e.target !== fileInput) markDirty(); });
  // Select2 fires synthetic jQuery "change" events while it initialises; only its user events mean an edit.
  if (window.django && window.django.jQuery) {
    window.django.jQuery(form).on("select2:select select2:unselect select2:clear", markDirty);
  }

  form.addEventListener("submit", (e) => {
    const btn = e.submitter;
    if (btn && btn.hasAttribute("data-preview-btn")) return;
    if (btn && btn.dataset.confirm && !window.confirm(btn.dataset.confirm)) {
      e.preventDefault();
      return;
    }
    submitting = true;
    clearTimeout(autosaveTimer);
    setState("Saving…");
  });

  window.addEventListener("beforeunload", (e) => {
    if (dirty && !submitting) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      const saveBtn = form.querySelector('button[name="_save"]');
      if (saveBtn) form.requestSubmit(saveBtn);
    }
    if (e.key === "Escape" && box.classList.contains("is-focus")) toggleFocus(false);
  });

  // ----- Restore an autosave that's newer than the saved post -----

  if (cfg.autosave) {
    const banner = $("[data-restore]");
    banner.hidden = false;
    $("[data-restore-time]").textContent = cfg.autosave.savedAt;
    $("[data-restore-yes]").addEventListener("click", () => {
      title.value = cfg.autosave.title;
      excerpt.value = cfg.autosave.excerpt;
      body.value = cfg.autosave.body;
      banner.hidden = true;
      markDirty();
      updateCount();
      refreshPreview();
    });
    $("[data-restore-no]").addEventListener("click", async () => {
      banner.hidden = true;
      const data = new FormData();
      if (cfg.postId) data.append("post_id", cfg.postId);
      data.append("discard", "1");
      try { await send(cfg.autosaveUrl, data); } catch (_) { /* nothing to lose */ }
    });
  }

  // ----- Text editing helpers -----

  function replaceSelection(text) {
    body.focus();
    // execCommand keeps the browser's undo history; setRangeText is the fallback.
    if (!document.execCommand || !document.execCommand("insertText", false, text)) {
      body.setRangeText(text, body.selectionStart, body.selectionEnd, "end");
      body.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function wrap(before, after = before, placeholder = "text") {
    const start = body.selectionStart;
    const selected = body.value.slice(start, body.selectionEnd) || placeholder;
    replaceSelection(before + selected + after);
    body.setSelectionRange(start + before.length, start + before.length + selected.length);
  }

  function prefixLines(prefix, numbered = false) {
    const v = body.value;
    const start = v.lastIndexOf("\n", body.selectionStart - 1) + 1;
    let end = v.indexOf("\n", body.selectionEnd);
    if (end === -1) end = v.length;
    const lines = v.slice(start, end).split("\n");
    const marker = /^(#{1,6} |> |[-*] |\d+\. )/;
    const has = (l) => (numbered ? /^\d+\. /.test(l) : l.startsWith(prefix));
    const removing = lines.every(has);
    const out = lines.map((l, i) => {
      const bare = l.replace(marker, "");
      return removing ? bare : (numbered ? `${i + 1}. ` : prefix) + bare;
    }).join("\n");
    body.setSelectionRange(start, end);
    replaceSelection(out);
    body.setSelectionRange(start, start + out.length);
  }

  function insertBlock(text) {
    const v = body.value;
    const before = v.slice(0, body.selectionStart);
    const after = v.slice(body.selectionEnd);
    const pre = !before || before.endsWith("\n\n") ? "" : before.endsWith("\n") ? "\n" : "\n\n";
    const post = after.startsWith("\n\n") ? "" : after.startsWith("\n") ? "\n" : "\n\n";
    replaceSelection(pre + text + post);
  }

  const commands = {
    h2: () => prefixLines("## "),
    h3: () => prefixLines("### "),
    bold: () => wrap("**", "**", "bold text"),
    italic: () => wrap("*", "*", "italic text"),
    quote: () => prefixLines("> "),
    ul: () => prefixLines("- "),
    ol: () => prefixLines("", true),
    hr: () => insertBlock("---"),
    link: () => {
      const url = window.prompt("Link address", "https://");
      if (!url || url === "https://") return;
      wrap("[", `](${url.trim().replace(/\s/g, "%20").replace(/\)/g, "%29")})`, "link text");
    },
    image: () => pickImages(false),
    gallery: () => pickImages(true),
    library: () => openLibrary(),
    focus: () => toggleFocus(),
  };

  document.querySelectorAll("[data-cmd]").forEach((btn) => {
    btn.addEventListener("click", () => commands[btn.dataset.cmd]());
  });

  body.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const map = { b: "bold", i: "italic", k: "link" };
    const cmd = map[e.key.toLowerCase()];
    if (cmd) {
      e.preventDefault();
      commands[cmd]();
    }
  });

  function toggleFocus(force) {
    const on = box.classList.toggle("is-focus", force);
    document.documentElement.classList.toggle("lot-no-scroll", on);
    body.focus();
  }

  // ----- Photos: upload, drag & drop, paste, library -----

  let galleryPick = false;

  function pickImages(gallery) {
    galleryPick = gallery;
    fileInput.multiple = gallery;
    fileInput.value = "";
    fileInput.click();
  }

  fileInput.addEventListener("change", () => {
    const files = Array.from(fileInput.files);
    uploadFiles(files, galleryPick || files.length > 1);
  });

  async function uploadFiles(files, asGallery) {
    files = files.filter((f) => f.type.startsWith("image/"));
    if (!files.length) return;
    const marker = `![Uploading ${files.length} photo${files.length > 1 ? "s" : ""}…](#upload-${Date.now()})`;
    insertBlock(marker);
    const lines = [];
    const errors = [];
    for (const [i, file] of files.entries()) {
      uploadStatus.textContent = `Uploading ${i + 1} of ${files.length}…`;
      const data = new FormData();
      data.append("image", file);
      try {
        const res = await send(cfg.uploadUrl, data);
        lines.push(`![](${res.url})`);
      } catch (err) {
        errors.push(`${file.name}: ${err.message}`);
      }
    }
    const block = lines.join(asGallery ? "\n" : "\n\n");
    const at = body.value.indexOf(marker);
    if (at === -1) {
      if (block) insertBlock(block);
    } else {
      body.setRangeText(block, at, at + marker.length, "end");
      body.focus();
      if (lines.length === 1) body.setSelectionRange(at + 2, at + 2);
      body.dispatchEvent(new Event("input", { bubbles: true }));
    }
    uploadStatus.textContent = errors.length
      ? errors.join(" · ")
      : lines.length === 1 ? "Uploaded. Type a caption between the [ ] if you like." : `Uploaded ${lines.length} photos.`;
    uploadStatus.dataset.tone = errors.length ? "error" : "";
  }

  body.addEventListener("dragover", (e) => {
    if (Array.from(e.dataTransfer.types).includes("Files")) {
      e.preventDefault();
      box.classList.add("is-drop");
    }
  });
  body.addEventListener("dragleave", () => box.classList.remove("is-drop"));
  body.addEventListener("drop", (e) => {
    box.classList.remove("is-drop");
    const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (!files.length) return;
    e.preventDefault();
    uploadFiles(files, files.length > 1);
  });
  body.addEventListener("paste", (e) => {
    const files = Array.from((e.clipboardData && e.clipboardData.files) || []).filter((f) => f.type.startsWith("image/"));
    if (files.length) {
      e.preventDefault();
      uploadFiles(files, files.length > 1);
    }
  });

  const library = $("[data-library]");
  const libraryGrid = $("[data-library-grid]");
  $("[data-library-close]").addEventListener("click", () => library.close());

  async function openLibrary() {
    const selStart = body.selectionStart;
    const selEnd = body.selectionEnd;
    libraryGrid.textContent = "Loading…";
    library.showModal();
    try {
      const { items } = await send(cfg.mediaUrl);
      libraryGrid.textContent = "";
      $("[data-library-empty]").hidden = items.length > 0;
      items.forEach((item) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.title = item.alt || "Insert photo";
        const img = document.createElement("img");
        img.src = item.thumb;
        img.alt = item.alt || "";
        img.loading = "lazy";
        btn.appendChild(img);
        btn.addEventListener("click", () => {
          library.close();
          body.focus();
          body.setSelectionRange(selStart, selEnd);
          insertBlock(`![${(item.alt || "").replace(/[[\]]/g, "")}](${item.url})`);
        });
        libraryGrid.appendChild(btn);
      });
    } catch (err) {
      libraryGrid.textContent = err.message;
    }
  }

  const coverInput = $("#id_cover_image");
  const coverPreview = $("[data-cover-preview]");
  if (coverInput && coverPreview) {
    coverInput.addEventListener("change", () => {
      const file = coverInput.files[0];
      if (!file) return;
      coverPreview.src = URL.createObjectURL(file);
      coverPreview.hidden = false;
    });
  }

  // ----- Live preview (same styles as the public site) -----

  let previewTimer = null;
  let previewSeq = 0;

  function writeFrame(html) {
    let scrollY = 0;
    try { scrollY = frame.contentWindow.scrollY; } catch (_) { /* first render */ }
    const css = cfg.previewCss.map((href) => `<link rel="stylesheet" href="${new URL(href, location.href).href}">`).join("");
    const heading = title.value.trim() ? `<h1 class="h-display text-5xl">${escapeHtml(title.value)}</h1>` : "";
    frame.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><base target="_blank">${css}</head>
      <body class="bg-white font-sans text-ink antialiased"><div class="mx-auto max-w-[44rem] px-6 py-10">${heading}
      <div class="${cfg.proseClasses} mt-8">${html}</div></div></body></html>`;
    frame.onload = () => { try { frame.contentWindow.scrollTo(0, scrollY); } catch (_) { /* ignore */ } };
  }

  async function refreshPreview() {
    if (box.dataset.mode === "write") return;
    const seq = ++previewSeq;
    const data = new FormData();
    data.append("body", body.value);
    try {
      const res = await send(cfg.renderUrl, data);
      if (seq === previewSeq) writeFrame(res.html);
    } catch (err) {
      if (seq === previewSeq) writeFrame(`<p style="color:#b91c1c">Preview unavailable: ${escapeHtml(err.message)}</p>`);
    }
  }

  function setMode(mode) {
    box.dataset.mode = mode;
    document.querySelectorAll("[data-mode-btn]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.modeBtn === mode)));
    try { localStorage.setItem("lot-editor-mode", mode); } catch (_) { /* private mode */ }
    refreshPreview();
  }

  document.querySelectorAll("[data-mode-btn]").forEach((btn) => btn.addEventListener("click", () => setMode(btn.dataset.modeBtn)));

  [body, title].forEach((el) => el.addEventListener("input", () => {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(refreshPreview, 450);
  }));

  // ----- Word count -----

  function updateCount() {
    const text = body.value.replace(/!\[[^\]]*\]\([^)]*\)/g, " ").replace(/\]\([^)]*\)/g, " ");
    const words = (text.match(/[\p{L}\p{N}][\p{L}\p{N}'’-]*/gu) || []).length;
    wordcount.textContent = `${words.toLocaleString()} word${words === 1 ? "" : "s"} · ${Math.max(1, Math.ceil(words / 220))} min read`;
  }
  body.addEventListener("input", updateCount);
  updateCount();

  let savedMode = "write";
  try { savedMode = localStorage.getItem("lot-editor-mode") || "write"; } catch (_) { /* private mode */ }
  if (savedMode !== "write" && window.matchMedia("(min-width: 1100px)").matches) setMode(savedMode);
  if (!title.value) title.focus();
})();
