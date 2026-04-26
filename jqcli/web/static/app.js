let page = 1;
let total = 0;

function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3500);
}

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function fmtPct(value) {
  if (value === null || value === undefined || value === "") return "";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function fmtNum(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "";
  return Number(value).toFixed(digits);
}

function params() {
  const p = new URLSearchParams({ page, page_size: 50 });
  const q = document.getElementById("q")?.value.trim();
  const period = document.getElementById("period")?.value;
  const minSharpe = document.getElementById("minSharpe")?.value;
  const label = document.getElementById("label")?.value;
  if (q) p.set("q", q);
  if (period) p.set("min_period_years", period);
  if (minSharpe) p.set("min_sharpe", minSharpe);
  if (label) p.set("label", label);
  return p;
}

async function loadPosts() {
  const data = await api(`/api/posts?${params()}`);
  total = data.total;
  const body = document.getElementById("postsBody");
  body.innerHTML = "";
  for (const item of data.items) {
    const tr = document.createElement("tr");
    const labels = (item.labels || []).map(label => `<span class="tag">${escapeHtml(label)}</span>`).join("");
    const status = [
      item.download_status === "downloaded" ? "已下载" : "未下载",
      item.last_backtest_status ? `回测:${item.last_backtest_status}` : ""
    ].filter(Boolean).join("<br>");
    tr.innerHTML = `
      <td class="muted">${escapeHtml(item.published_at || "")}</td>
      <td><a class="title" href="/posts/${item.id}">${escapeHtml(item.title || "")}</a><br><a class="muted" href="${item.url}" target="_blank">原帖</a></td>
      <td>${fmtNum(item.period_years)}</td>
      <td>${fmtPct(item.annual_return)}</td>
      <td>${fmtNum(item.sharpe, 2)}</td>
      <td><div class="tags">${labels}</div></td>
      <td>${status}</td>
      <td><div class="actions"><button data-download="${item.id}">${item.download_status === "downloaded" ? "已下载" : "下载"}</button><button data-backtest="${item.id}">回测</button></div></td>
    `;
    body.appendChild(tr);
  }
  document.getElementById("pageInfo").textContent = `第 ${page} 页 / ${Math.max(1, Math.ceil(total / 50))} 页，共 ${total} 条`;
}

async function pollJob(jobId) {
  for (;;) {
    const job = await api(`/api/jobs/${jobId}`);
    if (job.status === "done") {
      toast("任务完成");
      if (window.JQCLI_PAGE === "posts") loadPosts();
      return job;
    }
    if (job.status === "failed") {
      toast(`任务失败：${job.error || ""}`.slice(0, 180));
      return job;
    }
    await new Promise(resolve => setTimeout(resolve, 1500));
  }
}

function showBacktestDialog(postId) {
  const dialog = document.createElement("dialog");
  dialog.innerHTML = `
    <form method="dialog">
      <label>开始日期<input name="start_date" value="2021-01-01"></label>
      <label>结束日期<input name="end_date" value="2025-12-12"></label>
      <label>初始资金<input name="capital" type="number" value="500000"></label>
      <label>频率<select name="frequency"><option value="day">day</option><option value="minute">minute</option></select></label>
      <div class="actions"><button value="cancel">取消</button><button class="primary" value="ok">提交回测</button></div>
    </form>
  `;
  document.body.appendChild(dialog);
  dialog.addEventListener("close", async () => {
    if (dialog.returnValue === "ok") {
      const form = new FormData(dialog.querySelector("form"));
      const payload = Object.fromEntries(form.entries());
      const data = await api(`/api/posts/${postId}/backtests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast("回测任务已提交");
      pollJob(data.job_id);
    }
    dialog.remove();
  });
  dialog.showModal();
}

async function loadDetail() {
  const post = await api(`/api/posts/${window.JQCLI_POST_ID}`);
  const el = document.getElementById("postDetail");
  const labels = (post.labels || []).map(item => `<span class="tag" title="${escapeHtml(item.reason || "")}">${escapeHtml(item.label)}</span>`).join("");
  el.innerHTML = `
    <h1>${escapeHtml(post.title)}</h1>
    <div class="muted">${escapeHtml(post.published_at || "")} · ${escapeHtml(post.author_name || "")} · <a href="${post.url}" target="_blank">原帖</a></div>
    <div class="metrics">
      <span>周期 ${fmtNum(post.period_years)} 年</span>
      <span>年化 ${fmtPct(post.annual_return)}</span>
      <span>夏普 ${fmtNum(post.sharpe)}</span>
      <span>最大回撤 ${fmtPct(post.max_drawdown)}</span>
    </div>
    <div class="tags">${labels}</div>
    <div class="actions" style="margin-top:14px"><button data-download="${post.id}">下载策略</button><button data-backtest="${post.id}">提交回测</button></div>
    <div class="content">${escapeHtml(post.content || post.content_preview || "")}</div>
  `;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

document.addEventListener("click", async event => {
  const download = event.target.dataset?.download;
  const backtest = event.target.dataset?.backtest;
  if (download) {
    const data = await api(`/api/posts/${download}/download`, { method: "POST" });
    toast("下载任务已提交");
    pollJob(data.job_id);
  }
  if (backtest) showBacktestDialog(backtest);
});

document.getElementById("refreshBtn")?.addEventListener("click", async () => {
  const data = await api("/api/refresh", { method: "POST" });
  toast("刷新任务已提交");
  pollJob(data.job_id);
});

if (window.JQCLI_PAGE === "posts") {
  document.getElementById("searchBtn").addEventListener("click", () => { page = 1; loadPosts(); });
  document.getElementById("reindexBtn").addEventListener("click", async () => { await api("/api/posts/reindex", { method: "POST" }); toast("索引已重建"); loadPosts(); });
  document.getElementById("prevPage").addEventListener("click", () => { if (page > 1) { page -= 1; loadPosts(); } });
  document.getElementById("nextPage").addEventListener("click", () => { if (page * 50 < total) { page += 1; loadPosts(); } });
  loadPosts();
}

if (window.JQCLI_PAGE === "detail") loadDetail();
