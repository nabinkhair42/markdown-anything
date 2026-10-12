(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    drop: $("drop"),
    fileInput: $("fileInput"),
    dropMain: $("dropMain"),
    urlForm: $("urlForm"),
    urlInput: $("urlInput"),
    workbench: $("workbench"),
    dividerAfter: $("dividerAfterWorkbench"),
    fileList: $("fileList"),
    queueCount: $("queueCount"),
    clearAll: $("clearAll"),
    downloadAll: $("downloadAll"),
    outName: $("outName"),
    outMd: $("outMd"),
    outCode: $("outCode"),
    outPreview: $("outPreview"),
    outEmpty: $("outEmpty"),
    outError: $("outError"),
    copyBtn: $("copyBtn"),
    dlBtn: $("dlBtn"),
    tabMd: $("tabMd"),
    tabPreview: $("tabPreview"),
  };

  const items = [];
  let activeId = null;
  let nextId = 1;
  let activeTab = "md";

  const STATUS_MARK = { queued: "·", converting: "◜", done: "✓", error: "✕" };
  const STATUS_WORD = { queued: "queued", converting: "converting", done: "converted", error: "failed" };
  const MAX_CONCURRENT = 2;
  let running = 0;


  const fmtSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const mdName = (name) => {
    const base = name.replace(/\.[^.]+$/, "") || name;
    return `${base}.md`;
  };

  const byId = (id) => items.find((item) => item.id === id);


  function renderQueue() {
    els.fileList.textContent = "";
    for (const item of items) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "file-row";
      btn.setAttribute("aria-current", String(item.id === activeId));
      btn.dataset.id = String(item.id);

      const mark = document.createElement("span");
      mark.className = `status ${item.status}`;
      mark.textContent = STATUS_MARK[item.status] || "·";
      mark.setAttribute("aria-hidden", "true");

      const name = document.createElement("span");
      name.className = "name";
      name.textContent = item.name;
      name.title = item.name;

      const size = document.createElement("span");
      size.className = "size";
      size.textContent = fmtSize(item.size);

      const srLabel = document.createElement("span");
      srLabel.className = "visually-hidden";
      srLabel.textContent = ` (${STATUS_WORD[item.status] || item.status})${item.error ? `: ${item.error}` : ""}`;

      btn.append(mark, name, size, srLabel);
      btn.addEventListener("click", () => select(item.id));
      li.appendChild(btn);
      els.fileList.appendChild(li);
    }

    const done = items.filter((i) => i.status === "done").length;
    const pending = items.filter((i) => i.status === "queued" || i.status === "converting").length;
    els.queueCount.textContent = items.length
      ? pending
        ? `${done} done · ${pending} in progress`
        : `${done} of ${items.length} converted`
      : "";
    els.downloadAll.hidden = done < 1;
    els.clearAll.disabled = items.length === 0;
  }

  function engineLabel(item) {
    return item.engine === "mineru-ocr" ? " · OCR" : "";
  }

  function renderOutput() {
    const item = byId(activeId);
    const show = (el, on) => { el.hidden = !on; };

    if (!item) {
      els.outName.textContent = "No file selected";
      show(els.outMd, false);
      show(els.outPreview, false);
      show(els.outError, false);
      show(els.outEmpty, true);
      els.copyBtn.disabled = true;
      els.dlBtn.disabled = true;
      els.tabPreview.disabled = true;
      return;
    }

    els.outName.textContent = item.name + engineLabel(item);
    els.outName.title = item.name;
    els.copyBtn.disabled = item.status !== "done";
    els.dlBtn.disabled = item.status !== "done";
    els.tabPreview.disabled = item.status !== "done";

    if (item.status === "error") {
      els.outName.textContent = `${item.name}${engineLabel(item)}: failed`;
      show(els.outMd, false);
      show(els.outPreview, false);
      show(els.outEmpty, false);
      show(els.outError, true);
      els.outError.textContent = item.error || "Conversion failed.";
      return;
    }

    if (item.status !== "done") {
      show(els.outMd, false);
      show(els.outPreview, false);
      show(els.outError, false);
      show(els.outEmpty, true);
      els.outEmpty.textContent = item.status === "converting" ? "Converting…" : "Queued";
      return;
    }

    show(els.outEmpty, false);
    show(els.outError, false);

    if (activeTab === "preview") {
      show(els.outPreview, true);
      show(els.outMd, false);
      els.outPreview.innerHTML = "";
      if (window.marked?.parse) {
        els.outPreview.innerHTML = window.marked.parse(item.markdown || "");
      } else {
        const note = document.createElement("p");
        note.textContent = "Preview needs a one-time CDN script and you appear to be offline. The Markdown tab works regardless.";
        els.outPreview.appendChild(note);
      }
    } else {
      show(els.outMd, true);
      show(els.outPreview, false);
      els.outCode.textContent = item.markdown || "";
    }
  }

  function render() {
    renderQueue();
    renderOutput();
    els.workbench.hidden = items.length === 0;
    els.dividerAfter.hidden = items.length === 0;
  }


  async function post(path, body, isForm) {
    const res = await fetch(path, {
      method: "POST",
      body: isForm ? body : JSON.stringify(body),
      headers: isForm ? undefined : { "Content-Type": "application/json" },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    return data;
  }

  async function convertItem(item, requestFactory) {
    item.status = "converting";
    render();
    try {
      const data = await requestFactory();
      item.markdown = data.markdown ?? "";
      item.engine = data.engine || null;
      if (item.markdown.trim()) {
        item.status = "done";
      } else {
        item.status = "error";
        item.error = "Converted, but no text was found in this file.";
      }
    } catch (err) {
      item.status = "error";
      item.error = err.message || "Conversion failed.";
    }
    render();
  }

  function pump() {
    while (running < MAX_CONCURRENT) {
      const next = items.find((i) => i.status === "queued");
      if (!next) return;
      const run = next.request;
      running += 1;
      convertItem(next, run).finally(() => {
        running -= 1;
        pump();
      });
    }
  }

  function enqueue(name, size, requestFactory) {
    const item = {
      id: nextId++,
      name,
      size,
      status: "queued",
      markdown: null,
      error: null,
      request: requestFactory,
    };
    items.push(item);
    if (activeId === null) activeId = item.id;
    render();
    pump();
  }

  function addFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    for (const file of files) {
      enqueue(file.name, file.size, () => {
        const form = new FormData();
        form.append("file", file, file.name);
        return post("/api/convert", form, true);
      });
    }
    els.fileInput.value = "";
  }

  function addUrl(url) {
    enqueue(`web page from ${new URL(url).hostname}`, 0, () =>
      post("/api/convert-url", { url }, false)
    );
  }


  function select(id) {
    activeId = id;
    render();
  }

  function download(item) {
    const blob = new Blob([item.markdown || ""], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = mdName(item.name);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  els.copyBtn.addEventListener("click", async () => {
    const item = byId(activeId);
    if (!item || item.status !== "done") return;
    try {
      await navigator.clipboard.writeText(item.markdown || "");
      els.copyBtn.textContent = "Copied";
      els.copyBtn.classList.add("copied");
      setTimeout(() => {
        els.copyBtn.textContent = "Copy";
        els.copyBtn.classList.remove("copied");
      }, 1600);
    } catch {
      els.copyBtn.textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? "Press ⌘C" : "Press Ctrl+C";
      setTimeout(() => { els.copyBtn.textContent = "Copy"; }, 1600);
    }
  });

  els.dlBtn.addEventListener("click", () => {
    const item = byId(activeId);
    if (item && item.status === "done") download(item);
  });

  els.downloadAll.addEventListener("click", () => {
    const ready = items.filter((i) => i.status === "done");
    ready.forEach((item, i) => setTimeout(() => download(item), i * 350));
  });

  els.clearAll.addEventListener("click", () => {
    items.length = 0;
    activeId = null;
    render();
  });

  function setTab(tab) {
    activeTab = tab;
    els.tabMd.setAttribute("aria-selected", String(tab === "md"));
    els.tabPreview.setAttribute("aria-selected", String(tab === "preview"));
    renderOutput();
  }

  els.tabMd.addEventListener("click", () => setTab("md"));
  els.tabPreview.addEventListener("click", () => setTab("preview"));


  els.drop.addEventListener("click", () => els.fileInput.click());
  els.drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      els.fileInput.click();
    }
  });
  els.fileInput.addEventListener("change", () => addFiles(els.fileInput.files));

  ["dragenter", "dragover"].forEach((type) =>
    els.drop.addEventListener(type, (e) => {
      e.preventDefault();
      els.drop.classList.add("dragover");
      els.dropMain.textContent = "Drop to add files";
    })
  );
  ["dragleave", "dragend"].forEach((type) =>
    els.drop.addEventListener(type, () => {
      els.drop.classList.remove("dragover");
      els.dropMain.textContent = "Drop files here, or choose files";
    })
  );
  els.drop.addEventListener("drop", (e) => {
    e.preventDefault();
    els.drop.classList.remove("dragover");
    els.dropMain.textContent = "Drop files here, or choose files";
    addFiles(e.dataTransfer?.files);
  });

  // Dropping anywhere on the page lands in the queue, not the browser's viewer.
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    if (!els.drop.contains(e.target)) e.preventDefault();
  });

  els.urlForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const url = els.urlInput.value.trim();
    if (!url) return;
    try {
      addUrl(url);
      els.urlInput.value = "";
    } catch {
      els.urlInput.setCustomValidity("Enter a valid URL.");
      els.urlInput.reportValidity();
      setTimeout(() => els.urlInput.setCustomValidity(""), 1000);
    }
  });

  render();
})();
