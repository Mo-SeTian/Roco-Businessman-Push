/* 洛克王国远行商人推送控制台（无框架原生 JS） */
"use strict";

let S = null;          // /api/state 原始数据
let cfg = null;        // 本地工作副本（保存时整体提交）
let editingTaskId = null;   // null=新建
let editingChannelId = null;

const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

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

function renderAll() { renderStatus(); renderTasks(); renderChannels(); renderSettings(); renderAccount(); }

/* ---------- 状态 ---------- */

function renderStatus() {
  const s = S.scheduler;
  const fmt = (v) => v ? String(v).replace("T", " ") : "—";
  $("status-cards").innerHTML = [
    ["下次执行", fmt(s.next_run_at)],
    ["上次执行", fmt(s.last_fire_at)],
    ["当前状态", esc(s.in_progress ? "执行中…" : (s.running ? "运行中" : "已停止"))],
    ["结果", esc(s.last_message)],
  ].map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");

  const rows = (s.last_results || []);
  $("last-results").innerHTML = rows.length ? `<table>
    <tr><th>任务</th><th>商店</th><th>渠道结果</th></tr>` + rows.map(e => `<tr>
      <td>${esc(e.task)}${e.skipped ? ' <span class="tag off">无变化跳过</span>' : ""}</td>
      <td>${esc(e.shop)}</td>
      <td>${e.channels.map(c => `<span class="${c.ok ? "ok" : "bad"}">${c.ok ? "✔" : "✘"}</span> ${esc(c.channel)}` +
        (c.ok ? "" : ` <span class="bad">${esc(c.detail)}</span>`)).join("<br>") || "—"}</td>
    </tr>`).join("") + "</table>"
    : `<div class="empty">还没有执行记录</div>`;
}

/* ---------- 任务 ---------- */

function renderTasks() {
  const list = $("task-list");
  list.innerHTML = cfg.tasks.length ? cfg.tasks.map(t => {
    const chNames = t.channel_ids.map(id => { const c = cfg.channels.find(x => x.id === id); return c ? c.name : id + "?"; });
    return `<div class="item">
      <div class="info">
        <div class="title">${esc(t.name)} ${t.enabled ? "" : '<span class="tag off">已停用</span>'}
          ${t.only_on_change ? '<span class="tag">去重</span>' : '<span class="tag">每次都推</span>'}</div>
        <div class="meta">⏰ ${t.times.join("、")} ｜ 📤 ${chNames.length ? esc(chNames.join("、")) : "未选渠道"}</div>
      </div>
      <div class="actions" style="margin:0">
        <button onclick="runTask('${t.id}')">▶ 立即执行</button>
        <button onclick="editTask('${t.id}')">编辑</button>
        <button class="danger" onclick="delTask('${t.id}')">删除</button>
      </div>
    </div>`;
  }).join("") : `<div class="empty">还没有任务，点右上角「新建任务」</div>`;
}

function editTask(id) {
  editingTaskId = id || null;
  const t = id ? cfg.tasks.find(x => x.id === id) : { name: "", times: ["08:05", "12:05", "16:05", "20:05"], channel_ids: [], enabled: true, only_on_change: true };
  if (!cfg.channels.length) { toast("请先在「推送渠道」里至少创建一个渠道"); return; }
  $("task-editor").innerHTML = `
    <h2>${id ? "编辑任务" : "新建任务"}</h2>
    <label>任务名称</label><input type="text" id="te-name" value="${esc(t.name)}" placeholder="例如：早间推送">
    <label>触发时间（HH:MM，逗号分隔，可多个）</label>
    <input type="text" id="te-times" value="${esc(t.times.join(","))}">
    <label>推送到哪些渠道</label>
    <div class="checks">${cfg.channels.map(c => `
      <label><input type="checkbox" class="ch-check" value="${c.id}" ${t.channel_ids.includes(c.id) ? "checked" : ""}>
        ${esc(c.name)} <span class="tag">${esc(S.channel_types[c.type]?.label || c.type)}</span></label>`).join("")}
    </div>
    <div class="checkbox"><input type="checkbox" id="te-ooc" ${t.only_on_change ? "checked" : ""}>
      去重：接口返回与上次完全一致时跳过推送（默认每次都推）</div>
    <div class="checkbox"><input type="checkbox" id="te-en" ${t.enabled ? "checked" : ""}>启用该任务</div>
    <div class="actions">
      <button class="primary" onclick="saveTask()">保存</button>
      <button onclick="$('task-editor').hidden=true">取消</button>
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
async function delTask(id) {
  if (!confirm("确定删除该任务？")) return;
  try { await api("/api/config", { method: "POST", body: buildPayload(null, "task-del", id) }); await refresh(true); toast("已删除"); }
  catch (e) { toast("删除失败：" + e.message, 4000); }
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
        <div class="title">${esc(c.name)} <span class="tag">${esc(S.channel_types[c.type]?.label || c.type)}</span>
          ${c.enabled ? "" : '<span class="tag off">已停用</span>'}</div>
        <div class="meta">${meta}</div>
      </div>
      <div class="actions" style="margin:0">
        <button onclick="testChannel('${c.id}')">发送测试</button>
        <button onclick="editChannel('${c.id}')">编辑</button>
        <button class="danger" onclick="delChannel('${c.id}')">删除</button>
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
      <button id="ce-test" onclick="testChannelDraft()">发送测试</button>
      <button class="primary" onclick="saveChannel()">保存</button>
      <button onclick="$('channel-editor').hidden=true">取消</button>
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

async function delChannel(id) {
  if (!confirm("删除后，引用它的任务将推送失败，确定？")) return;
  try { await api("/api/config", { method: "POST", body: buildPayload(null, "ch-del", id) }); await refresh(true); toast("已删除"); }
  catch (e) { toast("删除失败：" + e.message, 4000); }
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
  ["rocom_api_key", "RoCom API Key（官网开发者控制台获取）", "password", "接口设置"],
  ["shop_ids_text", "商店 ID（逗号分隔，留空 = 默认远行商店 3009）", "text", "接口设置"],
  ["wait_ms", "接口同步等待毫秒数（wait_ms）", "number", "接口设置"],
  ["http_timeout", "HTTP 超时（秒）", "number", "接口设置"],
  ["max_retries", "202/网络错误重试次数", "number", "接口设置"],
  ["retry_delay", "重试间隔（秒）", "number", "接口设置"],
  ["log_retention_days", "文件日志保留天数（/logs 按天滚动，保存即生效）", "number", "数据保留"],
  ["history_days", "调用历史保留天数（过期自动清理）", "number", "数据保留"],
];

const SETTING_GROUPS = [
  ["接口设置", "🔑 对接洛克魔法书开放 API 的基础参数"],
  ["推送行为", "📤 标题前缀与启动行为"],
  ["通知模板", "📝 模板已预填内置默认，可直接修改。标题：{prefix} {shop_id} {refresh_count} {max_refresh_count}；正文：{goods_count} {goods_names} {countdown} {goods_list} 等；商品条目：{index} {name} {period} {price} {limit} {total} 等；{nl} 或 \\n 表示换行；全天商品 {period} 显示为「全天」"],
  ["数据保留", "🗄 文件日志与调用历史的保留天数，保存即生效"],
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
  for (const [group, desc] of SETTING_GROUPS) {
    html += `<div class="group"><h3>${esc(group)}</h3><p class="hint">${esc(desc)}</p>`;
    for (const [key, label, type, grp] of SETTING_FIELDS) {
      if (grp !== group) continue;
      const ph = key === "rocom_api_key" && cfg.has_rocom_api_key ? "已配置（留空保持不变）" : "";
      html += `<label>${label}</label><input type="${type}" id="set-${key}" value="${esc(values[key])}" placeholder="${esc(ph)}">`;
    }
    if (group === "推送行为") {
      html += `<label>推送标题前缀（模板中 {prefix} 占位符的值）</label>
        <input type="text" id="set-title_prefix" value="${esc(cfg.title_prefix)}">
        <div class="checkbox"><input type="checkbox" id="set-run-on-start" ${cfg.run_on_start ? "checked" : ""}>
        启动容器时立即执行一轮（默认关闭；开启后每次重启都会先拉一次数据并按任务推送）</div>`;
    }
    if (group === "通知模板") {
      html += `
        <label>标题模板</label><textarea id="set-title-template" rows="2">${esc(tv)}</textarea>
        <label>正文模板（Markdown）</label><textarea id="set-body-template" rows="8">${esc(bv)}</textarea>
        <label>商品行模板（每件商品一行）</label><textarea id="set-goods-line-template" rows="2">${esc(gv)}</textarea>
        <div class="actions" style="margin-top:12px">
          <button id="tpl-preview">👁 用示例数据预览</button>
          <button id="tpl-restore">↺ 还原默认模板</button>
        </div>
        <pre id="tpl-preview-out" class="mono" hidden></pre>`;
    }
    html += `</div>`;
  }
  form.innerHTML = html;
  $("tpl-preview").onclick = previewTemplate;
  $("tpl-restore").onclick = restoreTemplate;
}

function restoreTemplate() {
  const td = S.template_defaults || {};
  if (!confirm("确定将三个模板还原为内置默认？\n当前编辑内容将被覆盖（还原后还需点击底部“保存设置”才会生效）。")) return;
  $("set-title-template").value = td.title || "";
  $("set-body-template").value = td.body || "";
  $("set-goods-line-template").value = td.goods_line || "";
  toast("已还原为默认模板，记得点击“保存设置”");
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
  form.innerHTML = `
    <label>当前用户名</label><input type="text" id="acc-cur" value="${esc(S.auth_username || "admin")}" disabled>
    <label>当前密码（验证身份）</label><input type="password" id="acc-old" autocomplete="current-password">
    <label>新用户名</label><input type="text" id="acc-user" value="${esc(S.auth_username || "admin")}">
    <label>新密码（至少 4 位）</label><input type="password" id="acc-pass" autocomplete="new-password">
    <label>确认新密码</label><input type="password" id="acc-pass2" autocomplete="new-password">`;
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
    log_retention_days: +v("log_retention_days") || 7,
    history_days: +v("history_days") || 30,
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

  $("history-list").innerHTML = dates.length ? dates.map(day => {
    const rows = slots.map(slot => {
      const e = (byDay[day] || {})[slot];
      if (!e) return `<tr><td class="slot-cell">${slot}</td><td class="dim">— 无数据（未调用）</td></tr>`;
      const goods = (e.goods || []).map(g => {
        const bits = [esc(g.name)];
        if (g.price) bits.push(esc(g.price));
        if (g.limit != null) bits.push(`限购${esc(g.limit)}`);
        if (g.window) bits.push(esc(g.window));
        return `<div class="goods-line">${bits.join("｜")}</div>`;
      }).join("") || `<span class="dim">无商品</span>`;
      return `<tr><td class="slot-cell">${slot}<div class="dim" style="font-weight:400">${esc(e.queried || "")}${e.source ? " · " + esc(e.source) : ""}</div></td>
        <td>${goods}</td><td class="slot-cell">${e.count ?? 0} 件${e.refresh ? `<div class="dim" style="font-weight:400">刷新 ${esc(e.refresh)}</div>` : ""}</td></tr>`;
    }).join("");
    return `<h2 style="margin-top:16px">${esc(day)}</h2>
      <table><tr><th>档位</th><th>商品明细</th><th>数量</th></tr>${rows}</table>`;
  }).join("") : `<div class="empty">还没有历史数据——每次成功调用接口后会自动记录（每档一条）</div>`;
}

/* ---------- 初始化 ---------- */

$("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b === btn));
  document.querySelectorAll("main section").forEach(s => s.hidden = s.id !== "tab-" + btn.dataset.tab);
  if (btn.dataset.tab === "logs") refreshLogs().catch(err => toast(err.message, 4000));
  if (btn.dataset.tab === "history") refreshHistory().catch(err => toast(err.message, 4000));
});
$("logout").onclick = async () => { await fetch("/api/logout", { method: "POST" }); location.href = "/login"; };
$("run-all").onclick = async () => {
  try { const r = await api("/api/run-all", { method: "POST" }); toast(r.message); await refresh(true); }
  catch (e) { toast(e.message, 4000); }
};
$("task-add").onclick = () => editTask(null);
$("ch-add").onclick = () => editChannel(null);
$("settings-save").onclick = saveSettings;
$("account-save").onclick = saveAccount;
$("log-refresh").onclick = () => refreshLogs().catch(e => toast(e.message, 4000));
$("log-level").onchange = () => refreshLogs().catch(e => toast(e.message, 4000));
$("his-refresh").onclick = () => refreshHistory().catch(e => toast(e.message, 4000));
$("his-days").onchange = () => refreshHistory().catch(e => toast(e.message, 4000));
$("his-shop").onchange = (e) => { hisShop = e.target.value; refreshHistory().catch(err => toast(err.message, 4000)); };

refresh().catch(e => console.error(e));
setInterval(() => {
  refresh(true).catch(() => {});
  if (!$("tab-logs").hidden) refreshLogs().catch(() => {});   // 日志页可见时跟随刷新
}, 30000);
