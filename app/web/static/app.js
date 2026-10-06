/* 洛克王国远行商人推送控制台（无框架原生 JS） */
"use strict";

let S = null;          // /api/state 原始数据
let cfg = null;        // 本地工作副本（保存时整体提交）
let editingTaskId = null;   // null=新建
let editingChannelId = null;

const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* ---------- 图标（Lucide 风格描边 SVG） ---------- */
const ICONS = {
  hat:'<path d="M8.2 15 9.5 4h5L15.8 15"/><path d="M4 15h16"/><path d="M4 18.5h16"/><path d="M9.5 11h5"/>',
  activity:'<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  send:'<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  bell:'<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  sliders:'<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  history:'<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  file:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  logout:'<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  play:'<polygon points="6 3 20 12 6 21 6 3"/>',
  plus:'<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  refresh:'<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
  edit:'<path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
  trash:'<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  zap:'<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  eye:'<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  undo:'<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  check:'<polyline points="20 6 9 17 4 12"/>',
  clock:'<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  list:'<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  key:'<path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
  archive:'<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
  user:'<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  chev:'<polyline points="6 9 12 15 18 9"/>',
};
const ic = (name) => ICONS[name] ? `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>` : "";
document.querySelectorAll("[data-ic]").forEach(el => { el.innerHTML = ic(el.dataset.ic); });

const pad2 = (n) => String(n).padStart(2, "0");
function parseLocal(v) {  // "2026-10-06 16:05" / ISO 时间 → 本地 Date（后端用空格分隔，Safari 不能直接 new Date）
  const m = String(v || "").match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
}

/* ---------- 确认弹窗（替代原生 confirm） ---------- */
function confirmBox(msg, onOk, { danger = false, okText = "确定" } = {}) {
  const ov = $("confirm-overlay");
  $("confirm-msg").textContent = msg;
  const ok = $("confirm-ok");
  ok.textContent = okText;
  ok.className = danger ? "btn danger" : "btn primary";
  ok.onclick = () => { ov.hidden = true; onOk(); };
  ov.hidden = false;
  $("confirm-cancel").focus();
}

function toast(msg, ms = 2600) {
  const el = $("toast");
  el.textContent = msg; el.hidden = false;
  clearTimeout(el._t); el._t = setTimeout(() => el.hidden = true, ms);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 401) { location.href = "/login"; throw new Error("未登录"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.message || `请求失败(${r.status})`);
  return data;
}

async function refresh(silent = false) {
  S = await api("/api/state");
  cfg = S.config;
  if (S.config_issue) { $("issue").textContent = "⚠ " + S.config_issue; $("issue").hidden = false; }
  else $("issue").hidden = true;
  renderAll();
  if (!silent) toast("已刷新");
}

function renderAll() {
  renderStatus(); renderTasks(); renderChannels(); renderSettings(); renderAccount();
  $("nav-tasks-num").textContent = cfg.tasks.filter(t => t.enabled).length || "";
  $("nav-ch-num").textContent = cfg.channels.filter(c => c.enabled).length || "";
  $("user-name").textContent = S.auth_username || "admin";
  const ld = $("log-days");   // 日志页保留天数控件：用户正在编辑时不覆盖
  if (ld && !ld.matches(":focus")) ld.value = cfg.log_retention_days;
  const hr = $("his-retention");   // 历史页保留天数控件
  if (hr && !hr.matches(":focus")) hr.value = cfg.history_days;
}

/* ---------- 状态 ---------- */

function renderStatus() {
  const s = S.scheduler;
  const nowBase = parseLocal(S.now) || new Date();
  const next = parseLocal(s.next_run_at);

  // Hero：下次执行 + 客户端倒计时
  if (s.in_progress) {
    $("hero-next").textContent = "执行中…";
    $("hero-sub").textContent = s.last_message || "正在拉取数据并推送";
  } else if (next && s.running) {
    $("hero-next").innerHTML = `${pad2(next.getHours())}:${pad2(next.getMinutes())} <small>${next.getMonth() + 1}-${pad2(next.getDate())}</small>`;
    const diffMin = Math.round((next - nowBase) / 60000);
    if (diffMin > 0) {
      const h = Math.floor(diffMin / 60), m = diffMin % 60;
      $("hero-sub").innerHTML = `距下次执行还有 <b>${h > 0 ? h + " 小时 " : ""}${m} 分钟</b>，启用任务将按时推送`;
    } else {
      $("hero-sub").textContent = "即将执行…";
    }
  } else if (!s.running) {
    $("hero-next").textContent = "已停止";
    $("hero-sub").textContent = s.last_message || "调度器未运行";
  } else {
    $("hero-next").textContent = "—";
    $("hero-sub").textContent = s.last_message || "暂无调度计划";
  }

  // KPI 卡
  const last = parseLocal(s.last_fire_at);
  const lastStr = last ? `${pad2(last.getHours())}:${pad2(last.getMinutes())}` : "—";
  const lastSub = last ? `${last.getFullYear()}-${pad2(last.getMonth() + 1)}-${pad2(last.getDate())}` : "尚未执行";
  const statePill = s.in_progress
    ? '<span class="status-pill busy"><i></i>执行中</span>'
    : s.running ? '<span class="status-pill"><i></i>运行中</span>' : '<span class="status-pill stopped"><i></i>已停止</span>';
  const okN = (s.last_results || []).reduce((n, e) => n + (e.channels || []).filter(c => c.ok).length, 0);
  const badN = (s.last_results || []).reduce((n, e) => n + (e.channels || []).filter(c => !c.ok).length, 0);
  const resultV = okN + badN
    ? `<span class="${badN ? "txt-warn" : "ok2"}">${okN} / ${okN + badN} 成功</span>` : '<span class="dim">—</span>';
  const enTasks = cfg.tasks.filter(t => t.enabled).length;
  const enCh = cfg.channels.filter(c => c.enabled).length;
  const offTasks = cfg.tasks.length - enTasks;
  $("status-cards").innerHTML = [
    ["上次执行", lastStr, lastSub, "clock", "amber"],
    ["当前状态", statePill, s.running ? "调度器正常 · 30s 自动刷新" : "调度器未运行", "activity", "purple"],
    ["启用任务 / 渠道", `${enTasks}<small>/</small>${enCh}`, offTasks ? `${offTasks} 个任务已停用` : "全部任务已启用", "send", "purple"],
    ["最近结果", resultV, esc(s.last_message || "—"), "check", "green"],
  ].map(([k, v, sub, icon, color]) => `
    <div class="b"><span class="deco ${color}">${ic(icon)}</span>
      <div class="k">${k}</div><div class="v txt">${v}</div><div class="s">${sub}</div></div>`).join("");

  // 执行记录（最近 50 次，每次含各渠道成功/失败），分页展示
  const runs = s.run_history || [];
  const runTotalPages = Math.max(1, Math.ceil(runs.length / runPageSize));
  if (runPage > runTotalPages) runPage = runTotalPages;
  if (runPage < 1) runPage = 1;
  const rows = runs.slice((runPage - 1) * runPageSize, runPage * runPageSize).flatMap(run => (run.results || []).map(e => `
    <tr><td class="nowrap mono">${esc(String(run.time || "").slice(5, 19))}${run.reason ? `<div class="dim">${esc(run.reason)}</div>` : ""}</td>
      <td>${esc(e.task)}${e.skipped ? ' <span class="tag off">无变化跳过</span>' : ""}</td>
      <td class="mono">${esc(e.shop)}</td>
      <td>${e.channels.map(c => `<span class="${c.ok ? "ok2" : "bad"}">${c.ok ? "✔" : "✘"}</span> ${esc(c.channel)}` +
        (c.ok ? "" : ` <span class="bad mono">${esc(c.detail)}</span>`)).join("<br>") || "—"}</td>
    </tr>`));
  const runPager = runs.length > runPageSize ? `<div class="pager">
    <select id="run-page-size" class="sel" aria-label="每页执行次数">
      ${[5, 10, 20, 50].map(n => `<option value="${n}" ${n === runPageSize ? "selected" : ""}>每页 ${n} 次</option>`).join("")}
    </select>
    <button id="run-prev" class="btn sm" ${runPage <= 1 ? "disabled" : ""}>‹ 上一页</button>
    <span class="pager-info">第 ${runPage} / ${runTotalPages} 页 · 共 ${runs.length} 次</span>
    <button id="run-next" class="btn sm" ${runPage >= runTotalPages ? "disabled" : ""}>下一页 ›</button>
  </div>` : "";
  $("last-results").innerHTML = rows.length ? `<table>
    <thead><tr><th>执行时间</th><th>任务</th><th>商店</th><th>渠道结果</th></tr></thead><tbody>${rows.join("")}</tbody></table>${runPager}`
    : `<div class="empty">还没有执行记录——执行一次后这里会显示每次各渠道的推送结果</div>`;
}

/* ---------- 任务 ---------- */

function renderTasks() {
  const list = $("task-list");
  list.innerHTML = cfg.tasks.length ? cfg.tasks.map(t => {
    const chNames = t.channel_ids.map(id => { const c = cfg.channels.find(x => x.id === id); return c ? c.name : id + "?"; });
    return `<div class="item">
      <div class="info">
        <div class="title">${esc(t.name)} ${t.enabled ? "" : '<span class="tag off">已停用</span>'}
          ${t.only_on_change ? '<span class="tag">去重</span>' : '<span class="tag blue">每次都推</span>'}</div>
        <div class="meta"><span>${ic("clock")}${esc(t.times.join(" · "))}</span>
          <span>${ic("bell")}${chNames.length ? esc(chNames.join("、")) : "未选渠道"}</span></div>
      </div>
      <div class="ops">
        <button class="btn sm" onclick="runTask('${t.id}')">${ic("play")}立即执行</button>
        <button class="btn sm" onclick="editTask('${t.id}')">${ic("edit")}编辑</button>
        <button class="btn sm danger" onclick="delTask('${t.id}')">${ic("trash")}删除</button>
      </div>
    </div>`;
  }).join("") : `<div class="empty">还没有任务，点右上角「新建任务」</div>`;
}

function editTask(id) {
  editingTaskId = id || null;
  const t = id ? cfg.tasks.find(x => x.id === id) : { name: "", times: ["08:05", "12:05", "16:05", "20:05"], channel_ids: [], enabled: true, only_on_change: true };
  if (!cfg.channels.length) { toast("请先在「推送渠道」里至少创建一个渠道"); return; }
  $("task-editor").innerHTML = `
    <h2>${ic("send")}${id ? "编辑任务" : "新建任务"}</h2>
    <label>任务名称</label><input type="text" id="te-name" value="${esc(t.name)}" placeholder="例如：早间推送">
    <label>触发时间（HH:MM，逗号分隔，可多个）</label>
    <input type="text" id="te-times" value="${esc(t.times.join(","))}">
    <label>推送到哪些渠道</label>
    <div class="checks">${cfg.channels.map(c => `
      <label><input type="checkbox" class="ch-check" value="${c.id}" ${t.channel_ids.includes(c.id) ? "checked" : ""}>
        ${esc(c.name)} <span class="tag purple">${esc(S.channel_types[c.type]?.label || c.type)}</span></label>`).join("")}
    </div>
    <div class="checkbox"><input type="checkbox" id="te-ooc" ${t.only_on_change ? "checked" : ""}>
      去重：接口返回与上次完全一致时跳过推送（默认每次都推）</div>
    <div class="checkbox"><input type="checkbox" id="te-en" ${t.enabled ? "checked" : ""}>启用该任务</div>
    <div class="actions">
      <button class="btn primary" onclick="saveTask()">${ic("check")}保存</button>
      <button class="btn" onclick="$('task-editor').hidden=true">取消</button>
    </div>`;
  $("task-editor").hidden = false;
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

async function saveTask() {
  const times = $("te-times").value.split(",").map(s => s.trim()).filter(Boolean);
  const channel_ids = [...document.querySelectorAll("#task-editor .ch-check")]
    .filter(c => c.checked).map(c => c.value);
  const data = {
    id: editingTaskId || undefined,
    name: $("te-name").value.trim(),
    times, channel_ids,
    only_on_change: $("te-ooc").checked,
    enabled: $("te-en").checked,
  };
  try {
    await api("/api/config", { method: "POST", body: buildPayload(data, "task") });
    $("task-editor").hidden = true;
    await refresh(true);
    toast("任务已保存");
  } catch (e) { toast("保存失败：" + e.message, 4000); }
}
function delTask(id) {
  confirmBox("确定删除该任务？删除后不可恢复。", async () => {
    try { await api("/api/config", { method: "POST", body: buildPayload(null, "task-del", id) }); await refresh(true); toast("已删除"); }
    catch (e) { toast("删除失败：" + e.message, 4000); }
  }, { danger: true, okText: "删除" });
}

async function runTask(id) {
  try { const r = await api("/api/run-task", { method: "POST", body: { id } }); toast(r.message); await refresh(true); }
  catch (e) { toast(e.message, 4000); }
}

/* ---------- 渠道 ---------- */

function renderChannels() {
  const list = $("channel-list");
  list.innerHTML = cfg.channels.length ? cfg.channels.map(c => {
    const hasSecret = Object.entries(c.config).some(([k, v]) => k.startsWith("has_") && v);
    const filled = Object.entries(c.config).filter(([k]) => !k.startsWith("has_") && c.config[k]).map(([k]) => esc(k));
    const meta = [...(hasSecret ? ["密钥已配置"] : []), ...filled].join(" · ") || "未填写配置";
    return `
    <div class="item">
      <div class="info">
        <div class="title">${esc(c.name)} <span class="tag purple">${esc(S.channel_types[c.type]?.label || c.type)}</span>
          ${c.enabled ? "" : '<span class="tag off">已停用</span>'}</div>
        <div class="meta">${meta}</div>
      </div>
      <div class="ops">
        <button class="btn sm" onclick="testChannel('${c.id}')">${ic("zap")}发送测试</button>
        <button class="btn sm" onclick="editChannel('${c.id}')">${ic("edit")}编辑</button>
        <button class="btn sm danger" onclick="delChannel('${c.id}')">${ic("trash")}删除</button>
      </div>
    </div>`;
  }).join("") : `<div class="empty">还没有渠道实例，点右上角「新建渠道」</div>`;
}

/* ---------- 日志 ---------- */

const LOG_MSG_FOLD = 160;  // 超过此长度的日志折叠，点击展开全部

function logContentHTML(msg) {
  if (msg.length <= LOG_MSG_FOLD) return esc(msg);
  return `<details><summary>${esc(msg.slice(0, LOG_MSG_FOLD))}…（展开全部 ${msg.length} 字）</summary><pre>${esc(msg)}</pre></details>`;
}

async function refreshLogs() {
  const data = await api(`/api/logs?level=${$("log-level").value}&limit=2000`);
  const st = $("file-log-status");
  const fl = data.file_log || {};
  if (fl.error) {
    st.textContent = "⚠ 文件日志不可用：" + fl.error + "——当前仅控制台与内存日志，请检查挂载目录权限或 LOG_DIR 设置";
    st.classList.add("warn");
    st.hidden = false;
  } else if (fl.path) {
    st.textContent = "文件日志写入 " + fl.path + "，按天滚动";
    st.classList.remove("warn");
    st.hidden = false;
  } else {
    st.hidden = true;
  }
  const rows = data.logs || [];
  $("log-list").innerHTML = rows.length
    ? `<table><tr><th class="nowrap">时间</th><th class="nowrap">等级</th><th class="nowrap">来源</th><th>内容</th></tr>` +
      rows.map(l => `<tr><td class="nowrap mono">${esc(l.ts)}</td>` +
        `<td class="nowrap lv-${esc(l.level.toLowerCase())}">${esc(l.level)}</td>` +
        `<td class="nowrap">${esc(l.logger)}</td><td class="log-msg">${logContentHTML(l.message)}</td></tr>`).join("") +
      `</table>`
    : `<div class="empty">暂无日志</div>`;
  const box = $("log-list");
  box.scrollTop = box.scrollHeight;
}

function channelFieldsHTML(type, config) {
  const spec = S.channel_types[type];
  return spec.fields.map(f => {
    const val = config[f.name] || "";
    const has = config[`has_${f.name}`];
    const placeholder = has ? "已配置（留空保持不变）" : (f.default ? `默认 ${f.default}` : "");
    const input = `<input type="text" id="cf-${f.name}" value="${esc(val)}" placeholder="${esc(placeholder)}"
      ${f.secret ? 'autocomplete="off"' : ""}>`;
    return `<label>${esc(f.label)}${f.required ? " *" : ""}${f.secret ? "（密钥）" : ""}</label>${input}`;
  }).join("");
}

function editChannel(id) {
  editingChannelId = id || null;
  const c = id ? cfg.channels.find(x => x.id === id) : null;
  const type = c ? c.type : Object.keys(S.channel_types)[0];
  $("channel-editor").innerHTML = `
    <h2>${id ? "编辑渠道" : "新建渠道"}</h2>
    <label>渠道类型</label>
    <select id="ce-type" ${id ? "disabled" : ""} onchange="ceRebuildFields()">
      ${Object.entries(S.channel_types).map(([k, v]) => `<option value="${k}" ${k === type ? "selected" : ""}>${esc(v.label)}</option>`).join("")}
    </select>
    <label>实例名称（用于任务里区分）</label>
    <input type="text" id="ce-name" value="${esc(c ? c.name : "")}" placeholder="例如：我的 iPhone">
    <div id="ce-fields">${channelFieldsHTML(type, c ? c.config : {})}</div>
    <div class="checkbox"><input type="checkbox" id="ce-en" ${!c || c.enabled ? "checked" : ""}>启用该渠道</div>
    <div class="actions">
      <button id="ce-test" class="btn" onclick="testChannelDraft()">${ic("zap")}发送测试</button>
      <button class="btn primary" onclick="saveChannel()">${ic("check")}保存</button>
      <button class="btn" onclick="$('channel-editor').hidden=true">取消</button>
    </div>`;
  $("channel-editor").hidden = false;
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function ceRebuildFields() {
  $("ce-fields").innerHTML = channelFieldsHTML($("ce-type").value, {});
}

function collectChannelDraft() {
  const type = $("ce-type").value;
  const config = {};
  for (const f of S.channel_types[type].fields) {
    const el = $(`cf-${f.name}`);
    if (el) config[f.name] = el.value.trim();
  }
  return { id: editingChannelId || undefined, type, name: $("ce-name").value.trim(), enabled: $("ce-en").checked, config };
}

async function saveChannel() {
  try {
    const draft = collectChannelDraft();
    await api("/api/config", { method: "POST", body: buildPayload(draft, "channel") });
    $("channel-editor").hidden = true;
    await refresh(true);
    toast("渠道已保存");
  } catch (e) { toast("保存失败：" + e.message, 4000); }
}

function delChannel(id) {
  confirmBox("确定删除该渠道？删除后，引用它的任务将推送失败。", async () => {
    try { await api("/api/config", { method: "POST", body: buildPayload(null, "ch-del", id) }); await refresh(true); toast("已删除"); }
    catch (e) { toast("删除失败：" + e.message, 4000); }
  }, { danger: true, okText: "删除" });
}

async function testChannel(id) {
  try { const r = await api("/api/test-channel", { method: "POST", body: { id } }); toast(r.ok ? "测试已发送 ✔" : "测试失败：" + r.message, 4000); }
  catch (e) { toast(e.message, 4000); }
}

async function testChannelDraft() {
  try {
    const draft = collectChannelDraft();
    // 编辑已保存实例时带上 id：后端会用已保存密钥补齐表单里留空（保持不变）的字段
    const body = editingChannelId ? { id: editingChannelId, instance: draft } : { instance: draft };
    const r = await api("/api/test-channel", { method: "POST", body });
    toast(r.ok ? "测试已发送 ✔" : "测试失败：" + r.message, 4000);
  } catch (e) { toast(e.message, 4000); }
}

/* ---------- 设置 ---------- */

const SETTING_FIELDS = [
  ["rocom_api_key", "RoCom API Key", "password", "接口设置", "官网开发者控制台获取；留空保持已配置密钥", "full"],
  ["shop_ids_text", "商店 ID", "text", "接口设置", "逗号分隔；留空 = 默认远行商店 3009", "full"],
  ["wait_ms", "接口同步等待", "number", "接口设置", "毫秒（wait_ms）", ""],
  ["http_timeout", "HTTP 超时", "number", "接口设置", "秒", ""],
  ["max_retries", "202/网络错误重试", "number", "接口设置", "次数", ""],
  ["retry_delay", "重试间隔", "number", "接口设置", "秒", ""],
];

const SETTING_GROUPS = [
  ["接口设置", "对接洛克魔法书开放 API 的基础参数", "key"],
  ["推送行为", "标题前缀与启动行为", "send"],
  ["通知模板", "模板已预填内置默认，可直接修改；{nl} 或 \\n 表示换行，空字段行会自动清理；全天商品 {period} 显示为「全天」", "file"],
];

function renderSettings() {
  const form = $("settings-form");
  if (form.contains(document.activeElement)) return;  // 正在填写时跳过自动刷新重渲染
  const td = S.template_defaults || {};
  const tv = cfg.title_template || td.title || "";
  const bv = cfg.body_template || td.body || "";
  const gv = cfg.goods_line_template || td.goods_line || "";
  const values = {
    rocom_api_key: "", shop_ids_text: (cfg.shop_ids || []).join(","),
    title_prefix: cfg.title_prefix, wait_ms: cfg.wait_ms, http_timeout: cfg.http_timeout,
    max_retries: cfg.max_retries, retry_delay: cfg.retry_delay,
    log_retention_days: cfg.log_retention_days, history_days: cfg.history_days,
  };
  let html = "";
  for (const [group, desc, icon] of SETTING_GROUPS) {
    html += `<div class="group"><h3><span class="gi">${ic(icon)}</span>${esc(group)}</h3><p class="hint">${esc(desc)}</p>`;
    let gridOpen = false;
    for (const [key, label, type, grp, helper, span] of SETTING_FIELDS) {
      if (grp !== group) continue;
      if (!gridOpen) { html += `<div class="fgrid">`; gridOpen = true; }
      const ph = key === "rocom_api_key" && cfg.has_rocom_api_key ? "已配置（留空保持不变）" : "";
      html += `<div${span === "full" ? ` class="full"` : ""}><label>${esc(label)}</label>` +
        `<input type="${type}" id="set-${key}" value="${esc(values[key])}" placeholder="${esc(ph)}">` +
        `<p class="fhint">${esc(helper)}</p></div>`;
    }
    if (gridOpen) html += `</div>`;
    if (group === "推送行为") {
      html += `<div class="fgrid"><div class="full"><label>推送标题前缀</label>
        <input type="text" id="set-title_prefix" value="${esc(cfg.title_prefix)}">
        <p class="fhint">模板中 {prefix} 占位符的值</p></div></div>
        <div class="check"><input type="checkbox" id="set-run-on-start" ${cfg.run_on_start ? "checked" : ""}>
        启动容器时立即执行一轮（默认关闭；开启后每次重启都会先拉一次数据并按任务推送）</div>`;
    }
    if (group === "通知模板") {
      html += `
        <label>标题模板</label><textarea id="set-title-template" rows="2">${esc(tv)}</textarea>
        <p class="fhint">可用：{prefix} {shop_id} {refresh_count} {max_refresh_count} {date} {goods_count}</p>
        <label>正文模板（Markdown）</label><textarea id="set-body-template" rows="7">${esc(bv)}</textarea>
        <p class="fhint">可用：{queried} {source} {date} {shop_id} {refresh_count} {max_refresh_count} {goods_count} {goods_names} {goods_list} {countdown}</p>
        <label>商品行模板（每件商品一段）</label><textarea id="set-goods-line-template" rows="6">${esc(gv)}</textarea>
        <p class="fhint">可用：{index} {name} {period} {price} {price_num} {limit} {total} {item_num} {goods_id} {nl}</p>
        <div class="tpl-actions">
          <button id="tpl-preview" class="btn">${ic("eye")}用示例数据预览</button>
          <button id="tpl-restore" class="btn">${ic("undo")}还原默认模板</button>
        </div>
        <pre id="tpl-preview-out" class="tpl-out" hidden></pre>`;
    }
    html += `</div>`;
  }
  form.innerHTML = html;
  $("tpl-preview").onclick = previewTemplate;
  $("tpl-restore").onclick = restoreTemplate;
}

function restoreTemplate() {
  const td = S.template_defaults || {};
  confirmBox("确定将三个模板还原为内置默认？\n当前编辑内容将被覆盖（还原后还需点击底部「保存设置」才会生效）。", () => {
    $("set-title-template").value = td.title || "";
    $("set-body-template").value = td.body || "";
    $("set-goods-line-template").value = td.goods_line || "";
    toast("已还原为默认模板，记得点击「保存设置」");
  }, { danger: true, okText: "还原" });
}

async function previewTemplate() {
  try {
    const r = await api("/api/template-preview", { method: "POST", body: {
      title_prefix: cfg.title_prefix,
      title_template: $("set-title-template").value,
      body_template: $("set-body-template").value,
      goods_line_template: $("set-goods-line-template").value,
    } });
    const out = $("tpl-preview-out");
    out.hidden = false;
    out.textContent = `【标题】${r.title}\n\n【Markdown 正文】\n${r.markdown}\n\n【纯文本（Bark）】\n${r.text}`;
  } catch (e) { toast(e.message, 4000); }
}

function renderAccount() {
  const form = $("account-form");
  if (form.contains(document.activeElement)) return;
  form.innerHTML = `<div class="fgrid">
    <div class="full"><label>当前用户名</label><input type="text" id="acc-cur" value="${esc(S.auth_username || "admin")}" disabled></div>
    <div><label>当前密码（验证身份）</label><input type="password" id="acc-old" autocomplete="current-password"></div>
    <div><label>新用户名</label><input type="text" id="acc-user" value="${esc(S.auth_username || "admin")}"></div>
    <div><label>新密码（至少 4 位）</label><input type="password" id="acc-pass" autocomplete="new-password"></div>
    <div><label>确认新密码</label><input type="password" id="acc-pass2" autocomplete="new-password"></div>
  </div>`;
}

async function saveAccount() {
  const p1 = $("acc-pass").value, p2 = $("acc-pass2").value;
  if (p1 !== p2) { toast("两次输入的新密码不一致"); return; }
  if (p1.length < 4) { toast("新密码至少 4 位"); return; }
  try {
    const r = await api("/api/account", { method: "POST", body: {
      old_password: $("acc-old").value,
      username: $("acc-user").value.trim(),
      new_password: p1,
    } });
    toast(r.message);
    $("acc-old").value = ""; $("acc-pass").value = ""; $("acc-pass2").value = "";
    $("account-modal").hidden = true;
    await refresh(true);
  } catch (e) { toast(e.message, 4000); }
}

async function saveSettings() {
  const v = (k) => $(`set-${k}`).value.trim();
  const body = {
    ...cfg,
    rocom_api_key: v("rocom_api_key"),
    shop_ids: v("shop_ids_text"),
    title_prefix: v("title_prefix"),
    wait_ms: +v("wait_ms") || 8000,
    http_timeout: +v("http_timeout") || 30,
    max_retries: +v("max_retries") || 3,
    retry_delay: +v("retry_delay") || 20,
    run_on_start: $("set-run-on-start").checked,
    title_template: $("set-title-template").value,
    body_template: $("set-body-template").value,
    goods_line_template: $("set-goods-line-template").value,
  };
  try {
    await api("/api/config", { method: "POST", body });
    await refresh(true);
    toast("设置已保存，调度计划已更新");
  } catch (e) { toast("保存失败：" + e.message, 4000); }
}

/* ---------- 配置整体提交 ---------- */

function buildPayload(item, mode, delId) {
  let channels = [...cfg.channels];
  let tasks = [...cfg.tasks];
  if (mode === "channel") {
    channels = item.id ? channels.map(c => c.id === item.id ? item : c) : [...channels, item];
  } else if (mode === "ch-del") {
    channels = channels.filter(c => c.id !== delId);
  } else if (mode === "task") {
    if (item.id) tasks = tasks.map(t => t.id === item.id ? item : t);
    else tasks = [...tasks, item];
  } else if (mode === "task-del") {
    tasks = tasks.filter(t => t.id !== delId);
  }
  return {
    ...cfg, channels, tasks,
    // 商店 ID 统一以字符串提交，避免数组被后端 str() 序列化污染
    shop_ids: Array.isArray(cfg.shop_ids) ? cfg.shop_ids.join(",") : (cfg.shop_ids || ""),
  };
}

/* ---------- 历史记录 ---------- */

let hisShop = "";
let hisPage = 1;
let hisPageSize = 10;
let runPage = 1, runPageSize = 10;   // 执行记录翻页状态（模块级，避免自动刷新重置）

async function refreshHistory() {
  const data = await api(`/api/history?days=${$("his-days").value}`);
  const shopIds = Object.keys(data.history || {});
  const sel = $("his-shop");
  if (shopIds.length > 1) {
    sel.hidden = false;
    if (!shopIds.includes(hisShop)) hisShop = shopIds.includes("default") ? "default" : shopIds[0];
    sel.innerHTML = shopIds.map(id => `<option value="${esc(id)}" ${id === hisShop ? "selected" : ""}>商店 ${esc(id)}</option>`).join("");
  } else {
    sel.hidden = true;
    hisShop = shopIds[0] || "";
  }
  const byDay = (data.history || {})[hisShop] || {};
  const dates = Object.keys(byDay).sort().reverse();
  const slots = data.slots || [];

  if (!dates.length) {
    $("history-list").innerHTML = `<div class="empty">还没有历史数据——每次成功调用接口后会自动记录（每档一条）</div>`;
    return;
  }

  // 分页：按天切块，翻页只在当前查询范围内
  const totalPages = Math.max(1, Math.ceil(dates.length / hisPageSize));
  if (hisPage > totalPages) hisPage = totalPages;
  if (hisPage < 1) hisPage = 1;
  const pageDates = dates.slice((hisPage - 1) * hisPageSize, hisPage * hisPageSize);

  const iso = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  const today = iso(new Date()), yesterday = iso(new Date(Date.now() - 86400000));

  const dayHtml = pageDates.map(day => {
    const filled = slots.filter(slot => (byDay[day] || {})[slot]).length;
    const totalGoods = slots.reduce((n, slot) => n + ((byDay[day] || {})[slot]?.count ?? 0), 0);
    const dayBadge = day === today ? ' <span class="tag">今天</span>'
      : day === yesterday ? ' <span class="tag blue">昨天</span>' : "";
    const cards = slots.map(slot => {
      const e = (byDay[day] || {})[slot];
      if (!e) return `<div class="slot-card empty-slot">
        <div class="slot-head"><span class="slot-time">${esc(slot)}</span></div>
        <div class="slot-empty">${ic("clock")}<span>无数据（未调用）</span></div>
      </div>`;
      const goods = (e.goods || []).map(g => {
        const tags = [];
        if (g.limit != null) tags.push(`<span class="g-tag">限购 ${esc(g.limit)}</span>`);
        if (g.window) tags.push(`<span class="g-tag ${g.window === "全天" ? "" : "blue"} g-window">${esc(g.window)}</span>`);
        return `<div class="g"><span class="g-name">${esc(g.name)}</span>` +
          (g.price ? `<span class="g-price">${esc(g.price)}</span>` : "") + tags.join("") + `</div>`;
      }).join("") || `<div class="dim">无商品</div>`;
      return `<div class="slot-card">
        <div class="slot-head"><span class="slot-time">${esc(slot)}</span>
          <span class="slot-cnt ${e.count ? "" : "zero"}">${e.count ?? 0} 件</span></div>
        <div class="slot-meta">${e.refresh ? `刷新 ${esc(e.refresh)}` : ""}${e.queried ? ` · ${esc(e.queried)}` : ""}${e.source ? ` · ${esc(e.source)}` : ""}</div>
        <div class="goods-scroll">${goods}</div>
      </div>`;
    }).join("");
    return `<div class="day">
      <div class="day-head"><span class="day-date">${esc(day)}</span>${dayBadge}
        <span class="day-stat">记录 ${filled}/${slots.length} 档 · 商品 ${totalGoods} 件</span></div>
      <div class="slots">${cards}</div>
    </div>`;
  }).join("");

  const pager = totalPages > 1 ? `<div class="pager">
    <select id="his-page-size" class="sel" aria-label="每页天数">
      ${[5, 10, 20, 30].map(n => `<option value="${n}" ${n === hisPageSize ? "selected" : ""}>每页 ${n} 天</option>`).join("")}
    </select>
    <button id="his-prev" class="btn sm" ${hisPage <= 1 ? "disabled" : ""}>‹ 上一页</button>
    <span class="pager-info">第 ${hisPage} / ${totalPages} 页 · 共 ${dates.length} 天</span>
    <button id="his-next" class="btn sm" ${hisPage >= totalPages ? "disabled" : ""}>下一页 ›</button>
  </div>` : "";

  $("history-list").innerHTML = dayHtml + pager;
}

/* ---------- 初始化 ---------- */

function activateTab(name) {
  const btn = document.querySelector(`#tabs button[data-tab="${name}"]`);
  if (!btn) return false;
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b === btn));
  document.querySelectorAll("main section").forEach(s => s.hidden = s.id !== "tab-" + name);
  if (name === "logs") refreshLogs().catch(() => {});
  if (name === "history") refreshHistory().catch(() => {});
  history.replaceState(null, "", "#" + name);   // 刷新后停留在当前页
  try { localStorage.setItem("rocom_tab", name); } catch (_) {}
  return true;
}

$("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  activateTab(btn.dataset.tab);
});
$("logout").onclick = async () => { await fetch("/api/logout", { method: "POST" }); location.href = "/login"; };
$("refresh-status").onclick = () => refresh().catch(e => toast(e.message, 4000));

// 右上角用户菜单：点击展开/收起，点外部或 Esc 收起
const userDrop = $("user-drop");
$("user-btn").onclick = () => { userDrop.hidden = !userDrop.hidden; };
document.addEventListener("click", (e) => {
  if (!userDrop.hidden && !e.target.closest(".user-menu")) userDrop.hidden = true;
});
$("menu-account").onclick = () => {
  userDrop.hidden = true;
  if (document.activeElement) document.activeElement.blur();
  renderAccount();
  $("account-modal").hidden = false;
  $("acc-old").focus();
};

// 确认弹窗：取消 / 点遮罩 / Esc 均关闭
$("confirm-cancel").onclick = () => $("confirm-overlay").hidden = true;
$("confirm-overlay").addEventListener("click", (e) => { if (e.target === e.currentTarget) $("confirm-overlay").hidden = true; });
// 账号弹窗：取消 / 点遮罩关闭
$("account-cancel").onclick = () => $("account-modal").hidden = true;
$("account-modal").addEventListener("click", (e) => { if (e.target === e.currentTarget) $("account-modal").hidden = true; });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    $("confirm-overlay").hidden = true;
    $("account-modal").hidden = true;
    userDrop.hidden = true;
  }
});
$("run-all").onclick = async () => {
  try { const r = await api("/api/run-all", { method: "POST" }); toast(r.message); await refresh(true); }
  catch (e) { toast(e.message, 4000); }
};
$("task-add").onclick = () => editTask(null);
$("ch-add").onclick = () => editChannel(null);
$("settings-save").onclick = saveSettings;
$("account-save").onclick = saveAccount;
$("log-refresh").onclick = () => refreshLogs().catch(e => toast(e.message, 4000));
$("log-days-save").onclick = async () => {
  const days = +$("log-days").value || 7;
  try {
    await api("/api/config", { method: "POST", body: { ...buildPayload(null, ""), log_retention_days: days } });
    await refresh(true);
    toast(`日志保留已更新为 ${days} 天`);
  } catch (e) { toast("保存失败：" + e.message, 4000); }
};
$("log-level").onchange = () => refreshLogs().catch(e => toast(e.message, 4000));
$("his-refresh").onclick = () => refreshHistory().catch(e => toast(e.message, 4000));
$("his-days").onchange = () => { hisPage = 1; refreshHistory().catch(e => toast(e.message, 4000)); };
$("his-shop").onchange = (e) => { hisShop = e.target.value; hisPage = 1; refreshHistory().catch(err => toast(err.message, 4000)); };
// 执行记录翻页条事件委托（数据已在内存，翻页只重渲染不重新请求）
$("last-results").addEventListener("click", (e) => {
  if (e.target.closest("#run-prev")) { runPage--; renderStatus(); }
  if (e.target.closest("#run-next")) { runPage++; renderStatus(); }
});
$("last-results").addEventListener("change", (e) => {
  if (e.target.id === "run-page-size") { runPageSize = +e.target.value || 10; runPage = 1; renderStatus(); }
});

// 历史页保留天数：与日志页控件同款，保存即生效
$("his-retention-save").onclick = async () => {
  const days = +$("his-retention").value || 30;
  try {
    await api("/api/config", { method: "POST", body: { ...buildPayload(null, ""), history_days: days } });
    await refresh(true);
    toast(`调用历史保留已更新为 ${days} 天`);
  } catch (e) { toast("保存失败：" + e.message, 4000); }
};
// 翻页条事件委托（翻页条随渲染重建）
$("history-list").addEventListener("click", (e) => {
  if (e.target.closest("#his-prev")) { hisPage--; refreshHistory().catch(err => toast(err.message, 4000)); }
  if (e.target.closest("#his-next")) { hisPage++; refreshHistory().catch(err => toast(err.message, 4000)); }
});
$("history-list").addEventListener("change", (e) => {
  if (e.target.id === "his-page-size") { hisPageSize = +e.target.value || 10; hisPage = 1; refreshHistory().catch(err => toast(err.message, 4000)); }
});

// 恢复上次所在标签页：优先 URL hash，其次 localStorage，默认「状态」
let initialTab = decodeURIComponent(location.hash.slice(1)) || "";
try { initialTab = initialTab || localStorage.getItem("rocom_tab") || ""; } catch (_) {}
if (!activateTab(initialTab)) activateTab("status");

refresh().catch(e => console.error(e));
setInterval(() => {
  refresh(true).catch(() => {});
  if (!$("tab-logs").hidden) refreshLogs().catch(() => {});   // 日志页可见时跟随刷新
}, 30000);
