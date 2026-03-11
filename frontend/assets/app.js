const API = ""; // 同一オリジンなら空でOK

// 生成待ちキュー: { id, client_name, target_month, other_notes, files?: File[], text?: string }
let reportQueue = [];
// 一括PDFで検出した人（名前の列挙のみ。確認後に「一覧に追加」でキューに入れる）
let bulkDetectedPersons = [];

function $(id) { return document.getElementById(id); }
function showStatus(el, message, type = "") {
  const e = typeof el === "string" ? $(el) : el;
  if (!e) return;
  e.textContent = message;
  e.className = "status " + type;
  e.hidden = false;
}
function showDuplicateAlert(existing) {
  const alert = $("duplicate-alert");
  $("duplicate-message").textContent =
    `「${existing.client_name}」の ${existing.target_month} の報告書はすでに作られています。`;
  $("duplicate-link").href = "#/report/" + existing.id;
  alert.hidden = false;
  // 「作成」ボタンを「上書きして新しく作成」に切り替え（次回クリックで上書き送信）
  const submitBtn = $("submit-btn");
  if (submitBtn) {
    submitBtn.textContent = "上書きして新しく作成する";
    submitBtn.dataset.overwrite = "1";
  }
}
function hideDuplicateAlert() {
  const alert = $("duplicate-alert");
  if (alert) alert.hidden = true;
  const submitBtn = $("submit-btn");
  if (submitBtn) {
    submitBtn.textContent = "作成";
    delete submitBtn.dataset.overwrite;
  }
}

// 報告書一覧の元データ（並び替え用）
let reportsData = [];

function sortReports(reports, sortKey) {
  const arr = reports.slice();
  const date = (r) => (r.updated_at || r.created_at || "").slice(0, 19);
  const name = (r) => (r.client_name || "").trim();
  const month = (r) => (r.target_month || "").trim();
  switch (sortKey) {
    case "created-desc":
      arr.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
      break;
    case "created-asc":
      arr.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
      break;
    case "updated-desc":
      arr.sort((a, b) => (date(b) || "").localeCompare(date(a) || ""));
      break;
    case "updated-asc":
      arr.sort((a, b) => (date(a) || "").localeCompare(date(b) || ""));
      break;
    case "name-asc":
      arr.sort((a, b) => (name(a) || "").localeCompare(name(b) || "", "ja"));
      break;
    case "name-desc":
      arr.sort((a, b) => (name(b) || "").localeCompare(name(a) || "", "ja"));
      break;
    case "month-desc":
      arr.sort((a, b) => (month(b) || "").localeCompare(month(a) || ""));
      break;
    case "month-asc":
      arr.sort((a, b) => (month(a) || "").localeCompare(month(b) || ""));
      break;
    default:
      arr.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  }
  return arr;
}

function renderReportList() {
  const list = $("report-list");
  const sortEl = $("report-sort");
  const sortKey = (sortEl && sortEl.value) || "created-desc";
  if (!reportsData.length) {
    list.innerHTML = "<p class='muted'>まだ報告書はありません。PDFをアップロードして生成してください。</p>";
    return;
  }
  const sorted = sortReports(reportsData, sortKey);
  list.innerHTML = sorted
    .map(
      (r) =>
        `<a class="report-item" href="#/report/${r.id}" data-id="${r.id}">
          <span class="name">${escapeHtml(r.client_name)}</span>
          <span class="meta">${escapeHtml(r.target_month)} ・ ${(r.updated_at || r.created_at || "").slice(0, 10)}</span>
        </a>`
    )
    .join("");
}

async function loadReports() {
  const res = await fetch(API + "/api/reports");
  const data = await res.json();
  reportsData = data.reports || [];
  renderReportList();
}

function escapeHtml(s) {
  if (s == null) return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function showDetail(report) {
  $("list-section").hidden = true;
  $("upload-section").hidden = true;
  $("detail-section").hidden = false;
  $("edit_id").value = report.id;
  $("edit_client_name").value = report.client_name || "";
  $("edit_target_month").value = report.target_month || "";
  $("edit_病状の経過").value = report["病状の経過"] || "";
  $("edit_看護リハビリテーションの内容").value = report["看護リハビリテーションの内容"] || "";
  $("edit_家庭での介護の状況").value = report["家庭での介護の状況"] || "";
}

function showList() {
  $("detail-section").hidden = true;
  $("list-section").hidden = false;
  $("upload-section").hidden = false;
  loadReports();
  renderQueue();
}

function renderQueue() {
  const listEl = $("queue-list");
  const actionsEl = $("queue-actions");
  if (!listEl) return;
  if (reportQueue.length === 0) {
    listEl.innerHTML = "<p class='muted'>ここに「一覧に追加」した項目が並びます。追加後に「生成」または「すべて生成」で報告書を作成できます。</p>";
    if (actionsEl) actionsEl.hidden = true;
    return;
  }
  listEl.innerHTML = reportQueue
    .map(
      (item) => {
        const source = item.text ? "一括PDFより" : `${(item.files || []).length}ファイル`;
        return `<div class="queue-item" data-queue-id="${escapeHtml(item.id)}">
          <span class="label">${escapeHtml(item.client_name)}</span>
          <span class="meta">${escapeHtml(item.target_month)} ・ ${source}</span>
          <span class="btns">
            <button type="button" class="btn btn-sm btn-primary queue-generate">生成</button>
            <button type="button" class="btn btn-sm queue-remove">削除</button>
          </span>
        </div>`;
      }
    )
    .join("");
  if (actionsEl) actionsEl.hidden = false;

  listEl.querySelectorAll(".queue-generate").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".queue-item");
      const id = row && row.dataset.queueId;
      const item = reportQueue.find((q) => q.id === id);
      if (item) runGenerateQueueItem(item, row);
    });
  });
  listEl.querySelectorAll(".queue-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".queue-item");
      const id = row && row.dataset.queueId;
      reportQueue = reportQueue.filter((q) => q.id !== id);
      renderQueue();
    });
  });
}

// キュー1件をAPIで生成。options.openReport === false のときは一覧のまま（一括生成用）
async function runGenerateQueueItem(item, rowEl, options = {}) {
  const openReport = options.openReport !== false;
  const form = new FormData();
  form.append("client_name", item.client_name);
  form.append("target_month", item.target_month);
  form.append("other_notes", item.other_notes || "");
  form.append("overwrite", "1");
  let url;
  if (item.text) {
    form.append("text", item.text);
    url = "/api/reports/generate-from-text";
  } else {
    const files = item.files || [];
    if (files.length === 0) throw new Error("データがありません");
    if (files.length === 1) form.append("file", files[0]);
    else for (let i = 0; i < files.length; i++) form.append("files", files[i]);
    url = files.length > 1 ? "/api/reports/generate-multi" : "/api/reports/generate";
  }
  const controller = new AbortController();
  let timeoutId = setTimeout(() => controller.abort(), 6 * 60 * 1000);

  if (rowEl) rowEl.classList.add("generating");

  try {
    const res = await fetch(API + url, { method: "POST", body: form, signal: controller.signal });
    clearTimeout(timeoutId);
    timeoutId = null;
    let data;
    try {
      data = await res.json();
    } catch (_) {
      throw new Error("サーバーからの応答が正しくありません。");
    }
    if (!res.ok) {
      const msg = Array.isArray(data.detail) ? data.detail.map((d) => d.msg || JSON.stringify(d)).join(" ") : (data.detail || "エラー");
      throw new Error(msg);
    }
    if (data.duplicate) {
      showStatus("upload-status", `「${item.client_name}」${item.target_month} は既に存在します。上書きする場合は画面上部のフォームから「上書きして新しく作成」で作成してください。`, "error");
    } else {
      reportQueue = reportQueue.filter((q) => q.id !== item.id);
      renderQueue();
      loadReports();
      showStatus("upload-status", "1件、報告書を生成しました。", "success");
      if (openReport && data.report) {
        window.location.hash = "#/report/" + data.report.id;
        showDetail(data.report);
      }
    }
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    const isTimeout = err.name === "AbortError";
    showStatus("upload-status", isTimeout ? "時間がかかりすぎています。通信を確認して再度お試しください。" : (err.message || "エラーが発生しました。"), "error");
  } finally {
    if (rowEl) rowEl.classList.remove("generating");
  }
}

// 報告書全文をカイポケ転記用に1テキストでコピー
function buildCopyText(report) {
  return [
    "【病状の経過】",
    report["病状の経過"] || "",
    "",
    "【看護リハビリテーションの内容】",
    report["看護リハビリテーションの内容"] || "",
    "",
    "【家庭での介護の状況】",
    report["家庭での介護の状況"] || "",
  ].join("\n");
}

function init() {
  // ハッシュルート
  function route() {
    const hash = window.location.hash.slice(1) || "/";
    const m = hash.match(/^\/report\/([a-f0-9]+)$/);
    if (m) {
      const id = m[1];
      fetch(API + "/api/reports/" + id)
        .then((r) => (r.ok ? r.json() : null))
        .then((report) => {
          if (report) showDetail(report);
          else showList();
        })
        .catch(() => showList());
    } else {
      showList();
    }
  }
  window.addEventListener("hashchange", route);
  route();

  // 共有用URL表示・コピー（同じWi-Fi用＋外から用トンネルURL）
  const shareUrlEl = $("share-url");
  const copyDoneMsg = $("copy-done-msg");
  const shareUrlOutsideText = $("share-url-outside-text");
  const shareUrlPublicWrap = $("share-url-public-wrap");
  const shareUrlPublicEl = $("share-url-public");
  let urlToShare = window.location.origin;
  let publicUrlToShare = "";
  if (shareUrlEl) shareUrlEl.textContent = urlToShare;

  function setShareUrl(url) {
    urlToShare = url || window.location.origin;
    if (shareUrlEl) shareUrlEl.textContent = urlToShare;
  }
  function setPublicShareUrl(url) {
    publicUrlToShare = url || "";
    if (shareUrlPublicEl) shareUrlPublicEl.textContent = publicUrlToShare;
    if (shareUrlPublicWrap) shareUrlPublicWrap.hidden = !publicUrlToShare;
    if (shareUrlOutsideText) shareUrlOutsideText.hidden = !!publicUrlToShare;
  }
  function copyToClipboard(text) {
    if (!text || String(text).trim() === "") return Promise.reject(new Error("コピーする文字がありません"));
    const str = String(text).trim();
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(str).catch(() => copyFallback(str));
    }
    return Promise.resolve(copyFallback(str));
  }
  function copyFallback(text) {
    return new Promise((resolve, reject) => {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.setAttribute("aria-label", "URLをコピー");
      ta.style.cssText = "position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:80%;max-width:320px;height:3em;padding:0.5rem;border:1px solid #ccc;border-radius:6px;font-size:14px;z-index:9999;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.15);";
      document.body.appendChild(ta);
      ta.focus();
      ta.setSelectionRange(0, text.length);
      const doCopy = () => {
        let ok = false;
        try {
          ok = document.execCommand("copy");
        } finally {
          document.body.removeChild(ta);
        }
        if (ok) resolve(); else reject(new Error("copy failed"));
      };
      requestAnimationFrame(() => {
        requestAnimationFrame(doCopy);
      });
    });
  }
  function doCopyUrl() {
    return copyToClipboard(urlToShare);
  }
  function doCopyPublicUrl() {
    return copyToClipboard(publicUrlToShare);
  }
  function showCopyDone(msg) {
    const m = msg != null ? msg : "コピーしました。Windows・iPadのブラウザでこのURLを貼り付けて開けます。";
    if (copyDoneMsg) {
      copyDoneMsg.textContent = m;
      copyDoneMsg.hidden = false;
      setTimeout(() => { if (copyDoneMsg) copyDoneMsg.hidden = true; }, 4000);
    }
  }

  // サーバーから「他端末で開く用」URL（LANのIP＋任意で外から用）を取得
  fetch(API + "/api/server-info")
    .then((r) => r.json())
    .then((data) => {
      if (data.share_url) setShareUrl(data.share_url);
      else setShareUrl(window.location.origin);
      if (data.public_url) setPublicShareUrl(data.public_url);
    })
    .catch(() => setShareUrl(window.location.origin));

  function setCopyFailedMsg() {
    if (copyDoneMsg) {
      copyDoneMsg.textContent = "コピーに失敗しました。上のURLを長押しして選択し、コピーしてください。";
      copyDoneMsg.hidden = false;
      copyDoneMsg.style.color = "";
      setTimeout(() => { if (copyDoneMsg) copyDoneMsg.hidden = true; }, 6000);
    }
  }
  if (shareUrlEl) {
    shareUrlEl.addEventListener("click", () => {
      doCopyUrl().then(() => { showCopyDone(); }).catch(setCopyFailedMsg);
    });
  }
  if ($("copy-url-btn")) {
    $("copy-url-btn").addEventListener("click", () => {
      doCopyUrl().then(() => {
        showCopyDone();
        const btn = $("copy-url-btn");
        if (btn) { btn.textContent = "コピーしました"; setTimeout(() => { btn.textContent = "URLをコピー"; }, 2000); }
      }).catch(() => {
        setCopyFailedMsg();
        const btn = $("copy-url-btn");
        if (btn) { btn.textContent = "コピーに失敗"; setTimeout(() => { btn.textContent = "URLをコピー"; }, 2000); }
      });
    });
  }
  if ($("copy-public-url-btn")) {
    $("copy-public-url-btn").addEventListener("click", () => {
      doCopyPublicUrl().then(() => {
        showCopyDone("外から開く用URLをコピーしました。");
        const btn = $("copy-public-url-btn");
        if (btn) { btn.textContent = "コピーしました"; setTimeout(() => { btn.textContent = "URLをコピー"; }, 2000); }
      }).catch(() => {
        setCopyFailedMsg();
        const btn = $("copy-public-url-btn");
        if (btn) { btn.textContent = "コピーに失敗"; setTimeout(() => { btn.textContent = "URLをコピー"; }, 2000); }
      });
    });
  }

  // PDF選択時に利用者名・対象月を自動読み取り
  $("pdf_files").addEventListener("change", async () => {
    const files = $("pdf_files").files;
    const statusEl = $("extract-status");
    if (!files || files.length === 0) {
      statusEl.textContent = "";
      return;
    }
    statusEl.textContent = "読み取り中…";
    const form = new FormData();
    form.append("file", files[0]);
    try {
      const res = await fetch(API + "/api/extract-info", { method: "POST", body: form });
      const data = await res.json();
      if (data.client_name) $("client_name").value = data.client_name;
      if (data.target_month) $("target_month").value = data.target_month;
      statusEl.textContent = data.client_name || data.target_month
        ? "利用者名・対象月を読み取りました。"
        : "読み取れませんでした。PDFの形式を確認してください。";
    } catch {
      statusEl.textContent = "読み取りに失敗しました。PDFを確認してください。";
    }
  });

  // 報告書生成を送信（overwrite: 既存があるときに上書きするなら true）
  async function doSubmit(overwrite) {
    hideDuplicateAlert();
    const client_name = ($("client_name") && $("client_name").value) ? $("client_name").value.trim() : "";
    const target_month = ($("target_month") && $("target_month").value) ? $("target_month").value : "";
    const other_notes = ($("other_notes") && $("other_notes").value) ? $("other_notes").value.trim() : "";
    const files = $("pdf_files") && $("pdf_files").files;
    const statusEl = $("upload-status");
    const submitBtn = $("submit-btn");

    if (!files || files.length === 0) {
      showStatus("upload-status", "PDFファイルを選択してください。", "error");
      if (statusEl) statusEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    if (!client_name) {
      showStatus("upload-status", "利用者名が読み取れていません。PDFを選択してください。", "error");
      if (statusEl) statusEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    if (!target_month) {
      showStatus("upload-status", "対象月を選択してください。", "error");
      if (statusEl) statusEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "送信中…"; }
    showStatus("upload-status", "処理中です。2〜5分かかることがあります。そのままお待ちください…", "loading");
    if (statusEl) statusEl.hidden = false;
    if (statusEl) statusEl.scrollIntoView({ behavior: "smooth", block: "nearest" });

    const form = new FormData();
    form.append("client_name", client_name);
    form.append("target_month", target_month);
    form.append("other_notes", other_notes);
    if (overwrite) form.append("overwrite", "1");
    if (files.length === 1) {
      form.append("file", files[0]);
    } else {
      for (let i = 0; i < files.length; i++) {
        form.append("files", files[i]);
      }
    }

    const url = files.length > 1 ? "/api/reports/generate-multi" : "/api/reports/generate";
    const controller = new AbortController();
    let timeoutId = setTimeout(() => controller.abort(), 6 * 60 * 1000);

    try {
      const res = await fetch(API + url, { method: "POST", body: form, signal: controller.signal });
      clearTimeout(timeoutId);
      timeoutId = null;
      let data;
      try {
        data = await res.json();
      } catch (_) {
        throw new Error("サーバーからの応答が正しくありません。サーバーが起動しているか確認してください。");
      }
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail.map((d) => d.msg || JSON.stringify(d)).join(" ") : (data.detail || "エラーが発生しました");
        throw new Error(msg);
      }
      if (data.duplicate) {
        showDuplicateAlert(data.existing_report);
        showStatus("upload-status", data.message || "すでに作られています。既存を開くか、上書きして新しく作成できます。", "error");
      } else {
        hideDuplicateAlert();
        showStatus("upload-status", "報告書を生成しました。", "success");
        loadReports();
        window.location.hash = "#/report/" + data.report.id;
        showDetail(data.report);
      }
    } catch (err) {
      if (timeoutId) clearTimeout(timeoutId);
      const isTimeout = err.name === "AbortError";
      showStatus("upload-status", isTimeout ? "時間がかかりすぎています。通信を確認して、もう一度お試しください。" : (err.message || "エラーが発生しました。"), "error");
      if (statusEl) statusEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = submitBtn.dataset.overwrite === "1" ? "上書きして新しく作成する" : "作成";
      }
    }
  }

  // 「作成」ボタン（重複表示中は「上書きして新しく作成する」になっているので、そのときは overwrite=true で送信）
  const submitBtn = $("submit-btn");
  if (submitBtn) submitBtn.addEventListener("click", () => {
    const overwrite = submitBtn.dataset && submitBtn.dataset.overwrite === "1";
    doSubmit(overwrite);
  });

  // 「一括印刷PDFを人ごとに展開」：PDFを解析し、検出した人の名前を列挙（まだキューには入れない）
  $("split-bulk-btn").addEventListener("click", async () => {
    const fileInput = $("pdf_files");
    const files = fileInput && fileInput.files ? Array.from(fileInput.files) : [];
    const statusEl = $("upload-status");
    if (files.length === 0) {
      showStatus("upload-status", "一括印刷のPDFを選んでから押してください。", "error");
      return;
    }
    showStatus("upload-status", "一括PDFを解析しています…", "loading");
    const form = new FormData();
    form.append("file", files[0]);
    try {
      const res = await fetch(API + "/api/split-bulk-pdf", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "解析に失敗しました");
      const persons = data.persons || [];
      if (persons.length === 0) throw new Error("利用者を検出できませんでした");
      bulkDetectedPersons = persons;
      const listEl = $("bulk-preview-list");
      if (listEl) {
        listEl.innerHTML = persons
          .map((p) => {
            const name = p.client_name || "（氏名不明）";
            const month = p.target_month || "（要入力）";
            return `<li>${escapeHtml(name)} ／ ${escapeHtml(month)}</li>`;
          })
          .join("");
      }
      const previewEl = $("bulk-preview");
      if (previewEl) previewEl.hidden = false;
      showStatus("upload-status", `${persons.length} 人を検出しました。上記の名前を確認し、「検出した全員を一覧に追加」で待ちリストに追加してから作成してください。`, "success");
    } catch (err) {
      showStatus("upload-status", err.message || "一括PDFの解析に失敗しました。", "error");
    }
  });

  // 「検出した全員を一覧に追加」：列挙した人を待ちリストに追加してから作成できるようにする
  $("bulk-add-all-btn").addEventListener("click", () => {
    const other_notes = ($("other_notes") && $("other_notes").value) ? $("other_notes").value.trim() : "";
    for (const p of bulkDetectedPersons) {
      reportQueue.push({
        id: "q-" + Date.now() + "-" + Math.random().toString(36).slice(2, 9),
        client_name: p.client_name || "（氏名不明）",
        target_month: p.target_month || "",
        other_notes,
        text: p.text || "",
      });
    }
    bulkDetectedPersons = [];
    const previewEl = $("bulk-preview");
    if (previewEl) previewEl.hidden = true;
    showStatus("upload-status", "待ちリストに追加しました。下の一覧から「生成」または「すべて生成」で報告書を作成してください。", "success");
    renderQueue();
  });

  $("bulk-preview-cancel").addEventListener("click", () => {
    bulkDetectedPersons = [];
    const previewEl = $("bulk-preview");
    if (previewEl) previewEl.hidden = true;
    showStatus("upload-status", "キャンセルしました。", "");
  });

  // 「一覧に追加」：フォームの内容を待ちリストに追加し、フォームをクリア
  $("add-queue-btn").addEventListener("click", () => {
    hideDuplicateAlert();
    const client_name = ($("client_name") && $("client_name").value) ? $("client_name").value.trim() : "";
    const target_month = ($("target_month") && $("target_month").value) ? $("target_month").value : "";
    const other_notes = ($("other_notes") && $("other_notes").value) ? $("other_notes").value.trim() : "";
    const fileInput = $("pdf_files");
    const files = fileInput && fileInput.files ? Array.from(fileInput.files) : [];
    const statusEl = $("upload-status");
    if (files.length === 0) {
      showStatus("upload-status", "PDFファイルを選択してください。", "error");
      return;
    }
    if (!client_name) {
      showStatus("upload-status", "利用者名が読み取れていません。PDFを選択してください。", "error");
      return;
    }
    if (!target_month) {
      showStatus("upload-status", "対象月を選択してください。", "error");
      return;
    }
    reportQueue.push({
      id: "q-" + Date.now() + "-" + Math.random().toString(36).slice(2, 9),
      client_name,
      target_month,
      other_notes,
      files,
    });
    $("client_name").value = "";
    $("target_month").value = "";
    $("other_notes").value = "";
    if (fileInput) fileInput.value = "";
    if ($("extract-status")) $("extract-status").textContent = "";
    showStatus("upload-status", "待ちリストに追加しました。下の一覧から「生成」または「すべて生成」で作成できます。", "success");
    renderQueue();
  });

  // 「すべて生成」：待ちリストを先頭から順に1件ずつ生成（一覧のまま表示）
  $("generate-all-btn").addEventListener("click", async () => {
    if (reportQueue.length === 0) return;
    const allItems = reportQueue.slice();
    let done = 0;
    for (let i = 0; i < allItems.length; i++) {
      const item = reportQueue.find((q) => q.id === allItems[i].id);
      if (!item) continue;
      const row = $("queue-list") && $("queue-list").querySelector(`[data-queue-id="${item.id}"]`);
      showStatus("upload-status", `処理中… ${i + 1} / ${allItems.length} 件目（${escapeHtml(item.client_name)} ${item.target_month}）`, "loading");
      await runGenerateQueueItem(item, row, { openReport: false });
      done++;
    }
    showStatus("upload-status", `${done} 件の報告書を生成しました。`, "success");
  });

  // 一覧に戻る
  $("back-list").addEventListener("click", () => {
    window.location.hash = "#";
    showList();
  });

  // 全文コピー（カイポケ転記用）
  $("copy-all").addEventListener("click", async () => {
    const report = {
      "病状の経過": $("edit_病状の経過").value,
      "看護リハビリテーションの内容": $("edit_看護リハビリテーションの内容").value,
      "家庭での介護の状況": $("edit_家庭での介護の状況").value,
    };
    const text = buildCopyText(report);
    try {
      await navigator.clipboard.writeText(text);
      showStatus("edit-status", "クリップボードにコピーしました。カイポケの月次報告書画面に貼り付けてください。", "success");
    } catch {
      showStatus("edit-status", "コピーに失敗しました。画面の内容を手動でコピーしてください。", "error");
    }
  });

  // 編集保存
  $("edit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = $("edit_id").value;
    const form = new FormData();
    form.append("client_name", $("edit_client_name").value);
    form.append("target_month", $("edit_target_month").value);
    form.append("病状の経過", $("edit_病状の経過").value);
    form.append("看護リハビリテーションの内容", $("edit_看護リハビリテーションの内容").value);
    form.append("家庭での介護の状況", $("edit_家庭での介護の状況").value);
    try {
      const res = await fetch(API + "/api/reports/" + id, {
        method: "PUT",
        body: form,
      });
      if (!res.ok) throw new Error("保存に失敗しました");
      showStatus("edit-status", "保存しました。", "success");
    } catch (err) {
      showStatus("edit-status", err.message, "error");
    }
  });

  // 一覧のリンク（ハッシュで開くので route に任せる）
  $("report-list").addEventListener("click", (e) => {
    const a = e.target.closest("a[href^='#/report/']");
    if (a) {
      e.preventDefault();
      window.location.hash = a.getAttribute("href").slice(1);
      route();
    }
  });

  // 並び替え変更時は一覧だけ再描画（再取得しない）
  const sortEl = $("report-sort");
  if (sortEl) sortEl.addEventListener("change", () => renderReportList());
}

function safeInit() {
  try { init(); } catch (e) { console.error("init error:", e); }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", safeInit);
} else {
  safeInit();
}
