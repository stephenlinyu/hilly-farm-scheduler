const statusText = {
  online: "待命",
  working: "作业中",
  idle: "待命",
  offline: "离线",
};

const typeText = {
  tractor: "拖拉机",
  harvester: "收割机",
  seeder: "播种机",
  sprayer: "植保机",
};

const realtimePositionSources = new Set(["jt808", "gpswv"]);

function isRealtimePositionSource(source) {
  return realtimePositionSources.has(String(source || "").toLowerCase());
}

function positionSourceText(source) {
  const normalized = String(source || "").toLowerCase();
  if (normalized === "gpswv") return "商家云平台";
  if (normalized === "jt808") return "JT/T 808";
  return "演示数据";
}

const appState = {
  data: null,
  activeView: "home",
  map: null,
  mapPromise: null,
  markerLayer: null,
  routeLayer: null,
  realtimeTimer: null,
  isRefreshing: false,
};

document.addEventListener("DOMContentLoaded", async () => {
  lucide.createIcons();
  bindWorkerEvents();
  await loadWorkerOverview({ silent: true });
  startRealtimeRefresh();
});

function startRealtimeRefresh() {
  window.clearInterval(appState.realtimeTimer);
  appState.realtimeTimer = window.setInterval(() => {
    if (!document.hidden) {
      void loadWorkerOverview({ silent: true });
    }
  }, 3000);
}

function bindWorkerEvents() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => switchWorkerView(button.dataset.view));
  });

  document.querySelectorAll("[data-view-target]").forEach((button) => {
    button.addEventListener("click", () => switchWorkerView(button.dataset.viewTarget));
  });

  document.getElementById("worker-refresh").addEventListener("click", () => loadWorkerOverview());
  document.getElementById("worker-logout").addEventListener("click", logoutWorker);
  document.getElementById("worker-password-form").addEventListener("submit", submitWorkerPassword);

  document.addEventListener("click", async (event) => {
    const confirmButton = event.target.closest("[data-confirm-task]");
    if (confirmButton) {
      await confirmWorkerTask(confirmButton.dataset.confirmTask);
      return;
    }

    const completeButton = event.target.closest("[data-complete-task]");
    if (completeButton) {
      await completeWorkerTask(completeButton.dataset.completeTask);
      return;
    }

    const deleteButton = event.target.closest("[data-delete-task]");
    if (deleteButton) {
      await deleteWorkerTask(deleteButton.dataset.deleteTask, deleteButton);
      return;
    }

    const mapButton = event.target.closest("[data-open-map]");
    if (mapButton) {
      switchWorkerView("map");
    }
  });
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, { cache: "no-store", ...options });
  const data = await res.json().catch(() => ({}));

  if (res.status === 401) {
    window.location.href = data.redirect || "/worker/login";
    throw new Error(data.error || "未登录");
  }
  if (!res.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function loadWorkerOverview(options = {}) {
  if (appState.isRefreshing) return;
  appState.isRefreshing = true;
  try {
    const data = await apiFetch("/api/worker/overview");
    appState.data = data;
    renderAll();
    if (!options.silent) {
      showToast("数据已刷新");
    }
  } catch (err) {
    if (err.message !== "未登录") {
      showToast(err.message);
    }
  } finally {
    appState.isRefreshing = false;
  }
}

function renderAll() {
  const data = appState.data;
  if (!data) return;

  renderTopbar(data);
  renderHome(data);
  renderTasks(data.tasks);
  renderNotices(data.messages);
  renderMachineDetail(data.machine);
  renderMapSummary(data);

  if (appState.activeView === "map") {
    void renderWorkerMap();
  }
  lucide.createIcons();
}

function renderTopbar(data) {
  const user = data.user || {};
  document.getElementById("worker-name").textContent = user.display_name || user.username || "工作人员";
}

function renderHome(data) {
  const machine = data.machine || {};
  const summary = data.summary || {};

  const status = document.getElementById("machine-status");
  status.textContent = statusText[machine.status] || machine.status || "--";
  status.className = `mobile-status-pill ${machine.status || ""}`;

  document.getElementById("machine-title").textContent = machine.name || "--";
  document.getElementById("machine-subtitle").textContent = `${machine.id || "--"} · ${typeText[machine.type] || machine.type || "农机"} · ${machine.operator || "--"}`;
  document.getElementById("machine-speed").textContent = `${formatNumber(machine.speed)} km/h`;
  document.getElementById("metric-pending").textContent = summary.pending_tasks || 0;
  document.getElementById("metric-received").textContent = summary.completed_tasks || 0;
  document.getElementById("metric-area").textContent = `${formatNumber(summary.total_area_mu)}亩`;
  document.getElementById("metric-signal").textContent = `${machine.signal || 0}%`;

  const pending = data.tasks.filter((task) => task.status === "待接收");
  const previewTasks = pending.length ? pending.slice(0, 3) : data.tasks.slice(0, 3);
  renderTaskCards(document.getElementById("home-task-list"), previewTasks, { compact: true });
}

function renderTasks(tasks) {
  document.getElementById("task-count-label").textContent = `${tasks.length} 个任务`;
  renderTaskCards(document.getElementById("task-list"), tasks, { compact: false });
}

function renderTaskCards(container, tasks, options = {}) {
  if (!tasks.length) {
    container.innerHTML = `<div class="empty-state">暂无任务分配结果</div>`;
    return;
  }

  container.innerHTML = tasks.map((task, index) => {
    const isReceived = task.status === "已接收";
    const isCompleted = task.status === "已完成";
    const statusClass = isCompleted ? "online" : isReceived ? "working" : "idle";
    return `
      <article class="task-item">
        <div class="task-head">
          <div>
            <span class="task-order">${escapeHtml(String(task.task_order || index + 1))}</span>
            <h3>${escapeHtml(task.farmland_name || task.farmland_id)}</h3>
          </div>
          <span class="mobile-status-pill ${statusClass}">${escapeHtml(task.status)}</span>
        </div>
        <p>${escapeHtml(task.operation_type)} · ${escapeHtml(task.crop)} · ${escapeHtml(task.farmland_id)}</p>
        <div class="task-meta">
          <span>${formatNumber(task.area_mu)} 亩</span>
          <span>海拔 ${formatNumber(task.farmland_altitude)} m</span>
          <span>${escapeHtml(task.created_at || "--")}</span>
        </div>
        <div class="task-actions">
          ${renderTaskPrimaryAction(task, isReceived, isCompleted)}
          ${options.compact ? "" : `
            <button class="ghost-action" type="button" data-open-map="${escapeHtml(String(task.id))}">
              <i data-lucide="map-pin"></i>
              <span>地图</span>
            </button>
          `}
        </div>
      </article>
    `;
  }).join("");
}

function renderTaskPrimaryAction(task, isReceived, isCompleted) {
  const taskId = escapeHtml(String(task.id));
  if (isCompleted) {
    return `
      <button class="delete-action" type="button" data-delete-task="${taskId}">
        <i data-lucide="trash-2"></i>
        <span>删除任务</span>
      </button>
    `;
  }

  if (isReceived) {
    return `
      <button class="finish-action" type="button" data-complete-task="${taskId}">
        <i data-lucide="circle-check"></i>
        <span>提交完成</span>
      </button>
    `;
  }

  return `
    <button type="button" data-confirm-task="${taskId}">
      <i data-lucide="check"></i>
      <span>确认接收</span>
    </button>
  `;
}

function renderNotices(messages) {
  document.getElementById("notice-count-label").textContent = `${messages.length} 条`;
  const container = document.getElementById("notice-list");
  if (!messages.length) {
    container.innerHTML = `<div class="empty-state">暂无通知</div>`;
    return;
  }

  container.innerHTML = messages.map((message) => `
    <article class="notice-item ${escapeHtml(message.level || "normal")}">
      <div class="notice-head">
        <h3>${escapeHtml(message.title)}</h3>
        <span>${escapeHtml(message.time || "--:--")}</span>
      </div>
      <p>${escapeHtml(message.body || "")}</p>
    </article>
  `).join("");
}

function renderMachineDetail(machine) {
  const isRealtime = isRealtimePositionSource(machine.position_source);
  const rows = [
    ["农机编号", machine.id],
    ["农机名称", machine.name],
    ["机型", typeText[machine.type] || machine.type],
    ["所属组织", machine.org],
    ["操作人员", machine.operator],
    ["状态", statusText[machine.status] || machine.status],
    ["速度", `${formatNumber(machine.speed)} km/h`],
    ["作业时间", `${formatNumber(machine.work_time)} h`],
    ["信号", `${machine.signal || 0}%`],
    ["预警", `${machine.alerts || 0} 条`],
    ["定位来源", positionSourceText(machine.position_source)],
    ["协议终端号", machine.device_no || "--"],
    ["上报设备号", machine.position_device_no || "--"],
    ["经度", hasCoordinate(machine.lng) ? Number(machine.lng).toFixed(6) : "--"],
    ["纬度", hasCoordinate(machine.lat) ? Number(machine.lat).toFixed(6) : "--"],
    ["定位状态", isRealtime ? (machine.position_fresh ? "实时在线" : "定位已过期") : "演示定位"],
    ["最后状态时间", machine.last_seen || "--"],
  ];

  document.getElementById("machine-detail").innerHTML = rows.map(([label, value]) => `
    <div class="detail-row">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "--")}</strong>
    </div>
  `).join("");
}

function renderMapSummary(data) {
  const machine = data.machine || {};
  const summary = data.summary || {};
  document.getElementById("map-summary").innerHTML = `
    <strong>${escapeHtml(machine.name || "农机位置")}</strong>
    <span>${summary.total_tasks || 0} 个任务 · ${formatNumber(summary.total_area_mu)} 亩 · 完成 ${formatNumber(summary.completion_rate)}%</span>
  `;
}

function switchWorkerView(view) {
  appState.activeView = view;
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.querySelectorAll(".mobile-view").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `view-${view}`);
  });

  if (view === "map") {
    void renderWorkerMap();
    window.setTimeout(() => appState.map?.invalidateSize(), 80);
  }
}

async function ensureWorkerMap() {
  if (appState.map) return;
  if (!appState.mapPromise) {
    appState.mapPromise = FarmMapProvider.create("worker-map", {
      center: [29.56, 106.55],
      zoom: 13,
      minZoom: 4,
      maxZoom: 20,
      toolBar: true,
    }).then((map) => {
      appState.map = map;
      appState.markerLayer = map.createGroup();
      appState.routeLayer = map.createGroup();
      document.getElementById("worker-map").dataset.provider = map.provider;
      return map;
    }).finally(() => {
      appState.mapPromise = null;
    });
  }
  await appState.mapPromise;
}

async function renderWorkerMap() {
  if (!appState.data) return;
  await ensureWorkerMap();

  const { machine, tasks, map } = appState.data;
  appState.markerLayer.clear();
  appState.routeLayer.clear();

  const points = [];
  if (hasCoordinate(machine?.lat) && hasCoordinate(machine?.lng)) {
    const machinePoint = [machine.lat, machine.lng];
    points.push(machinePoint);
    appState.markerLayer.addHtmlMarker(machinePoint, {
      html: `<div class="machine-marker">机</div>`,
      size: [34, 34],
      anchor: [17, 17],
      title: machine.name,
      zIndex: 120,
    }).bindPopup(`${escapeHtml(machine.name)}<br>${escapeHtml(statusText[machine.status] || machine.status)}`);
  }

  tasks.forEach((task, index) => {
    if (!hasCoordinate(task.farmland_lat) || !hasCoordinate(task.farmland_lng)) return;
    const point = [task.farmland_lat, task.farmland_lng];
    points.push(point);
    appState.markerLayer.addHtmlMarker(point, {
      html: `<div class="field-marker">${index + 1}</div>`,
      size: [26, 26],
      anchor: [13, 13],
      title: task.farmland_name,
      zIndex: 110,
    }).bindPopup(`${escapeHtml(task.farmland_name)}<br>${escapeHtml(task.operation_type)} · ${escapeHtml(task.status)}`);
  });

  const routePoints = map?.route_points || points;
  if (routePoints.length > 1) {
    appState.routeLayer.addPolyline(routePoints, {
      color: "#1eaa72",
      weight: 4,
      opacity: 0.86,
      dashArray: "8, 6",
      showDir: true,
    });
  }

  if (points.length > 1) {
    appState.map.fitBounds(points, { padding: [34, 34], maxZoom: 14 });
  } else if (points.length === 1) {
    appState.map.setView(points[0], 14);
  }
}

async function confirmWorkerTask(taskId) {
  try {
    await apiFetch(`/api/worker/tasks/${taskId}/confirm`, { method: "POST" });
    showToast("任务已确认接收");
    await loadWorkerOverview({ silent: true });
  } catch (err) {
    showToast(err.message);
  }
}

async function completeWorkerTask(taskId) {
  try {
    await apiFetch(`/api/worker/tasks/${taskId}/complete`, { method: "POST" });
    showToast("任务已提交完成");
    await loadWorkerOverview({ silent: true });
  } catch (err) {
    showToast(err.message);
  }
}

async function deleteWorkerTask(taskId, button) {
  if (!window.confirm("确定删除这条已完成任务吗？删除后任务列表中将不再显示。")) {
    return;
  }

  button.disabled = true;
  try {
    await apiFetch(`/api/worker/tasks/${taskId}`, { method: "DELETE" });
    showToast("已完成任务已删除");
    await loadWorkerOverview({ silent: true });
  } catch (err) {
    showToast(err.message);
    button.disabled = false;
  }
}

async function logoutWorker() {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    console.error("logout error:", err);
  } finally {
    window.location.href = "/worker/login";
  }
}

async function submitWorkerPassword(event) {
  event.preventDefault();
  const message = document.getElementById("worker-password-message");
  const submit = document.getElementById("worker-password-submit");
  const currentPassword = document.getElementById("worker-current-password").value;
  const newPassword = document.getElementById("worker-new-password").value;
  const confirmPassword = document.getElementById("worker-confirm-password").value;

  message.textContent = "";
  message.classList.remove("error");

  if (newPassword !== confirmPassword) {
    message.textContent = "两次输入的新密码不一致";
    message.classList.add("error");
    return;
  }

  submit.disabled = true;
  submit.textContent = "保存中...";
  try {
    const data = await apiFetch("/api/auth/change_password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    message.textContent = data.message || "密码已更新";
    document.getElementById("worker-password-form").reset();
  } catch (err) {
    message.textContent = err.message;
    message.classList.add("error");
  } finally {
    submit.disabled = false;
    submit.textContent = "保存密码";
  }
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function hasCoordinate(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showToast(message) {
  const toast = document.getElementById("worker-toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 1800);
}
