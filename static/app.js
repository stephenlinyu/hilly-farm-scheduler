// ============================================================
//  真实后端数据提供者
// ============================================================

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

const iconByType = {
  tractor: "🚜",
  harvester: "🌾",
  seeder: "🌱",
  sprayer: "💧",
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

// ===== 真实后端数据提供者 =====
class RealDataProvider {
  // 获取当前登录用户
  async getCurrentUser() {
    try {
      const res = await fetch('/api/auth/me');
      if (!res.ok) throw new Error('获取当前用户失败');
      return res.json();
    } catch (err) {
      console.error('getCurrentUser error:', err);
      return { authenticated: false, user: null };
    }
  }

  // 退出登录
  async logout() {
    const res = await fetch('/api/auth/logout', { method: 'POST' });
    if (!res.ok) throw new Error('退出登录失败');
    return res.json();
  }

  // 修改当前登录账号密码
  async changePassword(currentPassword, newPassword) {
    const res = await fetch('/api/auth/change_password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '修改密码失败');
    return data;
  }

  // 获取任务列表
  async getTasks() {
    try {
      const res = await fetch('/api/tasks');
      if (!res.ok) throw new Error('获取任务失败');
      return res.json();
    } catch (err) {
      console.error('getTasks error:', err);
      return [];
    }
  }

  // 管理员手动分配任务
  async addTask(task) {
    const res = await fetch('/api/tasks/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(task),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || '任务分配失败');
    return data;
  }

  async deleteTask(taskId) {
    const res = await fetch(`/api/tasks/delete/${taskId}`, { method: 'DELETE' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || '任务删除失败');
    return data;
  }

  // 获取概览统计
  async getOverviewStats() {
    try {
      const res = await fetch('/api/dashboard');
      if (!res.ok) throw new Error('获取统计失败');
      const data = await res.json();
      return {
        todayArea: (data.completed_tasks || 0) * 12.5,
        online: data.machine_count,
        total: data.total_tasks,
        completion: data.completion_rate,
        alerts: 0
      };
    } catch (err) {
      console.error('getOverviewStats error:', err);
      return { todayArea: 0, online: 0, total: 0, completion: 0, alerts: 0 };
    }
  }

  // 获取农机列表
  async getMachines(filters = {}) {
    try {
      const res = await fetch('/api/machines', { cache: 'no-store' });
      if (!res.ok) throw new Error('获取农机失败');
      const machines = await res.json();
      
      // 前端筛选（类型、状态、关键词）
      let filtered = machines;
      if (filters.type && filters.type !== 'all') {
        filtered = filtered.filter(m => m.type === filters.type);
      }
      if (filters.status && filters.status !== 'all') {
        filtered = filtered.filter(m => m.status === filters.status);
      }
      if (filters.keyword && filters.keyword.trim()) {
        const kw = filters.keyword.trim().toLowerCase();
        filtered = filtered.filter(m => 
          `${m.name} ${m.id} ${m.org} ${m.operator}`.toLowerCase().includes(kw)
        );
      }
      if (filters.scope === 'today') {
        filtered = filtered.filter(m => m.area > 0);
      }
      if (filters.scope === 'alerts') {
        filtered = filtered.filter(m => m.alerts > 0);
      }
      
      return filtered;
    } catch (err) {
      console.error('getMachines error:', err);
      return [];
    }
  }

  // 获取农田列表
  async getFields() {
    try {
      const res = await fetch('/api/fields');
      if (!res.ok) throw new Error('获取农田失败');
      const fields = await res.json();
      return fields.map(f => ({
        id: f.id,
        name: f.name,
        crop: f.crop || '待定',
        area: Number((Number(f.area_sqm || 0) / 666.67).toFixed(2)),
        status: f.status || '待作业',
        lat: f.lat,
        lng: f.lng,
        polygon: Array.isArray(f.polygon) && f.polygon.length
          ? f.polygon
          : [
              [f.lat - 0.005, f.lng - 0.005],
              [f.lat + 0.005, f.lng - 0.005],
              [f.lat + 0.005, f.lng + 0.005],
              [f.lat - 0.005, f.lng + 0.005]
            ]
      }));
    } catch (err) {
      console.error('getFields error:', err);
      return [];
    }
  }

  // 获取农机轨迹（调用真实后端接口）
  async getMachineTrack(machineId, timeRange = null) {
    try {
      const params = new URLSearchParams();
      if (timeRange?.start) params.set('start', timeRange.start);
      if (timeRange?.end) params.set('end', timeRange.end);
      const query = params.size ? `?${params.toString()}` : '';
      const res = await fetch(`/api/tracks/${machineId}${query}`, { cache: 'no-store' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error('获取轨迹失败');
      return data;
    } catch (err) {
      console.error('getMachineTrack error:', err);
      if (timeRange) throw err;
      return null;
    }
  }

  async getMachineTrackHistory(machineId) {
    try {
      const res = await fetch(`/api/tracks/${machineId}/history`, { cache: 'no-store' });
      if (!res.ok) throw new Error('获取历史轨迹失败');
      return res.json();
    } catch (err) {
      console.error('getMachineTrackHistory error:', err);
      return [];
    }
  }

  // 获取终端统计
  async getTerminalStats() {
    try {
      const res = await fetch('/api/terminal/stats');
      if (!res.ok) throw new Error('获取终端统计失败');
      return res.json();
    } catch (err) {
      console.error('getTerminalStats error:', err);
      return { online: 4, working: 2, idle: 1, offline: 1, avgSignal: 88 };
    }
  }

  // 获取视频流
  async getVideoStreams() {
    try {
      const res = await fetch('/api/video/streams');
      if (!res.ok) throw new Error('获取视频流失败');
      return res.json();
    } catch (err) {
      console.error('getVideoStreams error:', err);
      return [
        { id: 'V-1', machineId: 'M-001', machineName: '耕牛 1号', channel: '前视摄像头', protocol: 'WebRTC', status: '待接入' },
        { id: 'V-2', machineId: 'M-002', machineName: '耕牛 2号', channel: '驾驶室摄像头', protocol: 'WebRTC', status: '待接入' }
      ];
    }
  }

  // 获取消息
  async getMessages() {
    try {
      const res = await fetch('/api/messages');
      if (!res.ok) throw new Error('获取消息失败');
      return res.json();
    } catch (err) {
      console.error('getMessages error:', err);
      return [
        { title: '系统通知', time: '09:14', body: '新任务已分配，请及时确认' },
        { title: '任务更新', time: '09:10', body: '任务已更新' }
      ];
    }
  }

  // 发送指令
  async sendCommand(machineId, command) {
    try {
      const res = await fetch('/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ machineId, command })
      });
      if (!res.ok) throw new Error('发送指令失败');
      return res.json();
    } catch (err) {
      console.error('sendCommand error:', err);
      return { accepted: false, machineId, command, reason: '指令发送失败' };
    }
  }
}

// ============================================================
//  初始化
// ============================================================

const dataProvider = new RealDataProvider();

// ============================================================
//  计算两点距离（单位：km）
// ============================================================

function calculateDistance(point1, point2) {
  const lat1 = point1[0], lng1 = point1[1];
  const lat2 = point2[0], lng2 = point2[1];
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLng/2) * Math.sin(dLng/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

// ============================================================
//  State 和地图相关
// ============================================================

const state = {
  map: null,
  machineLayer: null,
  realMachineLayer: null,
  fieldLayer: null,
  trackLayer: null,
  realTrackLayer: null,
  playbackMarker: null,
  selectedMachineId: null,
  activePanel: "dashboard",
  activeScope: "all",
  machineCategory: "all",
  machines: [],
  allMachines: [],
  fields: [],
  tasks: [],
  markers: new Map(),
  fieldMarkers: [],
  playbackTimer: null,
  playbackIndex: 0,
  playbackElapsed: 0,
  playbackLastFrame: 0,
  activeTrack: null,
  playing: false,
  terminalChart: null,
  tileErrors: 0,
  navClickTimer: null,
  demoLayersVisible: true,
  realtimeTracks: new Map(),
  trackCategory: "all",
  trackHistory: new Map(),
  trackVisible: false,
  realtimeTimer: null,
  realtimeRefreshing: false,
};

const mapPadding = {
  topLeft: [500, 126],
  bottomRight: [260, 112],
};

// ============================================================
//  地图初始化
// ============================================================

document.addEventListener("DOMContentLoaded", async () => {
  lucide.createIcons();
  await initMap();
  bindEvents();
  await hydrate();
});

async function initMap() {
  state.map = await FarmMapProvider.create("map", {
    center: [29.56, 106.55],
    zoom: 13,
    minZoom: 4,
    maxZoom: 20,
    toolBar: false,
  });
  state.machineLayer = state.map.createGroup({ clustered: true });
  state.realMachineLayer = state.map.createGroup();
  state.fieldLayer = state.map.createGroup();
  state.trackLayer = state.map.createGroup();
  state.realTrackLayer = state.map.createGroup();
  state.map.on("zoomend", updateFieldMarkerDensity);
  state.map.onError(handleTileError);
  state.map.onLoad(() => {
    if (state.map.provider === "amap") {
      document.getElementById("map-fallback").classList.add("hidden");
    }
  });

  const fallback = document.getElementById("map-fallback");
  const fallbackText = fallback.querySelector("span");
  if (state.map.provider === "amap") {
    fallback.classList.add("hidden");
  } else {
    fallbackText.textContent = `${state.map.fallbackReason}，当前使用兼容地图`;
    fallback.classList.remove("hidden");
  }
}

function handleTileError() {
  state.tileErrors += 1;
  if (state.tileErrors >= 4) {
    document.querySelector("#map-fallback span").textContent = "地图服务加载不稳定，请检查网络或高德配置";
    document.getElementById("map-fallback").classList.remove("hidden");
  }
}

// ============================================================
//  数据加载
// ============================================================

async function hydrate() {
  window.setTimeout(() => state.map.invalidateSize(), 120);
  window.setTimeout(() => state.map.invalidateSize(), 600);
  await loadCurrentUser();
  await refreshStats();
  state.fields = await dataProvider.getFields();
  state.tasks = await dataProvider.getTasks();
  renderFields();
  await refreshMachines();
  renderManualTaskOptions();
  await renderSupportingViews();
  fitAllMachines();
  startRealtimePolling();
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => handleNavClick(button.dataset.panel));
    button.addEventListener("dblclick", () => handleNavDoubleClick(button.dataset.panel));
  });
  document.querySelectorAll("[data-panel-target]").forEach((button) => {
    button.addEventListener("click", () => switchPanel(button.dataset.panelTarget));
  });
  document.querySelectorAll(".mini-tab").forEach((button) => {
    button.addEventListener("click", async () => {
      document.querySelectorAll(".mini-tab").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.activeScope = button.dataset.scope;
      await refreshMachines();
    });
  });
  document.querySelectorAll("[data-machine-category]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-machine-category]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.machineCategory = button.dataset.machineCategory || "all";
      refreshMachines();
    });
  });

  ["type-filter", "status-filter", "machine-search"].forEach((id) => {
    document.getElementById(id).addEventListener("input", refreshMachines);
  });
  document.getElementById("global-search").addEventListener("input", handleGlobalSearch);
  document.getElementById("track-machine-search").addEventListener("input", renderTrackMachineList);
  document.querySelectorAll("[data-track-category]").forEach((button) => {
    button.addEventListener("click", () => {
      setTrackCategory(button.dataset.trackCategory || "all");
    });
  });
  document.getElementById("track-history-select").addEventListener("change", async (event) => {
    const history = state.trackHistory.get(state.selectedMachineId) || [];
    const selected = history.find((item) => String(item.id) === String(event.target.value));
    if (selected) await drawTrackFromData(state.selectedMachineId, selected, true);
  });
  document.querySelectorAll("[data-real-track-range]").forEach((button) => {
    button.addEventListener("click", () => setRealTrackRange(button.dataset.realTrackRange));
  });
  document.getElementById("real-track-query-panel").addEventListener("submit", handleRealTrackQuery);
  document.getElementById("refresh-btn").addEventListener("click", async () => {
    await refreshStats();
    await refreshMachines();
    showToast("数据已刷新");
  });
  document.getElementById("password-btn").addEventListener("click", openPasswordModal);
  document.getElementById("password-close").addEventListener("click", closePasswordModal);
  document.getElementById("password-modal").addEventListener("click", (event) => {
    if (event.target.id === "password-modal") closePasswordModal();
  });
  document.getElementById("password-form").addEventListener("submit", handlePasswordSubmit);
  document.getElementById("logout-btn").addEventListener("click", handleLogout);
  document.getElementById("manual-task-form").addEventListener("submit", handleManualTaskSubmit);
  document.getElementById("task-list").addEventListener("click", handleTaskListClick);
  document.getElementById("panel-collapse").addEventListener("click", () => {
    document.getElementById("panel").classList.toggle("collapsed");
  });
  document.getElementById("layer-satellite").addEventListener("click", () => switchLayer("satellite"));
  document.getElementById("layer-street").addEventListener("click", () => switchLayer("street"));
  document.getElementById("fit-all").addEventListener("click", fitAllMachines);
  document.getElementById("toggle-demo").addEventListener("click", toggleDemoLayers);
  document.getElementById("play-btn").addEventListener("click", togglePlayback);
  document.getElementById("stop-btn").addEventListener("click", stopPlayback);
  document.getElementById("play-progress").addEventListener("input", handleProgressChange);
  document.getElementById("speed-select").addEventListener("change", restartPlaybackIfNeeded);
  document.getElementById("fullscreen-btn").addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen().catch(() => showToast("浏览器暂不允许全屏"));
    }
  });
}

async function loadCurrentUser() {
  const data = await dataProvider.getCurrentUser();
  if (!data.authenticated || data.user?.role !== 'admin') {
    window.location.href = '/login';
    return;
  }
  const currentUser = document.getElementById("current-user");
  if (currentUser) {
    currentUser.textContent = data.user.display_name || data.user.username || '管理员';
  }
}

async function handleLogout() {
  try {
    await dataProvider.logout();
  } catch (err) {
    console.error('logout error:', err);
  } finally {
    window.location.href = '/login';
  }
}

function openPasswordModal() {
  document.getElementById("password-form").reset();
  document.getElementById("password-message").textContent = "";
  document.getElementById("password-message").classList.remove("error");
  document.getElementById("password-modal").classList.remove("hidden");
  window.setTimeout(() => document.getElementById("current-password").focus(), 50);
}

function closePasswordModal() {
  document.getElementById("password-modal").classList.add("hidden");
}

async function handlePasswordSubmit(event) {
  event.preventDefault();
  const message = document.getElementById("password-message");
  const submit = document.getElementById("password-submit");
  const currentPassword = document.getElementById("current-password").value;
  const newPassword = document.getElementById("new-password").value;
  const confirmPassword = document.getElementById("confirm-password").value;

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
    await dataProvider.changePassword(currentPassword, newPassword);
    closePasswordModal();
    showToast("密码已更新，请妥善保管新密码");
  } catch (err) {
    message.textContent = err.message;
    message.classList.add("error");
  } finally {
    submit.disabled = false;
    submit.textContent = "保存新密码";
  }
}

function renderManualTaskOptions() {
  const machineSelect = document.getElementById("manual-task-machine");
  const fieldSelect = document.getElementById("manual-task-field");
  if (!machineSelect || !fieldSelect) return;

  const machines = state.allMachines.length ? state.allMachines : state.machines;

  machineSelect.innerHTML = machines
    .map((machine) => `
      <option value="${machine.id}">
        ${machine.name} / ${machine.operator || "未分配"}（${machine.id}）
      </option>
    `)
    .join("");

  fieldSelect.innerHTML = state.fields
    .map((field) => `
      <option value="${field.id}">
        ${field.name}（${field.id}）
      </option>
    `)
    .join("");

  if (state.selectedMachineId && machines.some((machine) => machine.id === state.selectedMachineId)) {
    machineSelect.value = state.selectedMachineId;
  }
}

async function handleManualTaskSubmit(event) {
  event.preventDefault();
  const message = document.getElementById("manual-task-message");
  const submit = document.getElementById("manual-task-submit");
  const machineId = document.getElementById("manual-task-machine").value;
  const farmlandId = document.getElementById("manual-task-field").value;
  const operationType = document.getElementById("manual-task-operation").value;
  const machine = state.allMachines.find((item) => item.id === machineId)
    || state.machines.find((item) => item.id === machineId);
  const field = state.fields.find((item) => item.id === farmlandId);

  if (!machineId || !farmlandId) {
    message.textContent = "请选择农机和作业地块";
    message.className = "assignment-terminal offline";
    return;
  }

  submit.disabled = true;
  message.textContent = "正在分配任务...";
  message.className = "assignment-terminal";

  try {
    await dataProvider.addTask({
      machine_id: machineId,
      farmland_id: farmlandId,
      operation_type: operationType,
    });

    state.tasks = await dataProvider.getTasks();
    renderTasks(state.tasks);
    await refreshStats();
    state.allMachines = await dataProvider.getMachines();
    await refreshMachines();
    renderManualTaskOptions();
    await selectMachine(machineId, {
      fitTrack: true,
      showTrack: !machine || !isRealtimePositionSource(machine.position_source),
    });

    message.textContent = `已分配给 ${machine?.operator || machineId}：${field?.name || farmlandId}`;
    message.className = "assignment-terminal online";
    showToast("任务已下发，工作人员手机端刷新后可接收");
  } catch (err) {
    message.textContent = err.message || "任务分配失败";
    message.className = "assignment-terminal offline";
  } finally {
    submit.disabled = false;
  }
}

async function handleTaskListClick(event) {
  const deleteButton = event.target.closest("[data-delete-task]");
  if (!deleteButton) return;

  const taskId = deleteButton.dataset.deleteTask;
  const task = state.tasks.find((item) => String(item.id) === String(taskId));
  const label = task ? `${task.operation_type} · ${task.machine_id} · ${task.farmland_id}` : `任务 ${taskId}`;

  if (!window.confirm(`确定删除已完成的 ${label} 吗？删除后工作人员手机端将不再看到该任务。`)) {
    return;
  }

  deleteButton.disabled = true;
  try {
    await dataProvider.deleteTask(taskId);
    state.tasks = await dataProvider.getTasks();
    renderTasks(state.tasks);
    await refreshStats();
    state.allMachines = await dataProvider.getMachines();
    await refreshMachines();
    renderManualTaskOptions();
    showToast("任务已删除");
  } catch (err) {
    showToast(err.message || "任务删除失败");
  } finally {
    deleteButton.disabled = false;
  }
}

async function refreshStats() {
  const stats = await dataProvider.getOverviewStats();
  document.getElementById("stat-area").textContent = `${stats.todayArea.toFixed(1)} 亩`;
  document.getElementById("stat-online").textContent = `${stats.online}`;
  document.getElementById("stat-complete").textContent = `${stats.completion}%`;
  document.getElementById("stat-alerts").textContent = stats.alerts;
}

async function refreshMachines() {
  const filters = {
    type: document.getElementById("type-filter").value,
    status: document.getElementById("status-filter").value,
    keyword: document.getElementById("machine-search").value,
    scope: state.activeScope,
  };
  state.allMachines = await dataProvider.getMachines();
  state.machines = filterMachines(state.allMachines, filters);
  renderMachineList();
  renderMarkers();
  renderTrackMachineList();
}

function filterMachines(machines, filters) {
  let filtered = [...machines];
  if (state.machineCategory === "real") {
    filtered = filtered.filter((machine) => isRealtimePositionSource(machine.position_source));
  } else if (state.machineCategory === "demo") {
    filtered = filtered.filter((machine) => !isRealtimePositionSource(machine.position_source));
  }
  if (filters.type && filters.type !== "all") {
    filtered = filtered.filter((machine) => machine.type === filters.type);
  }
  if (filters.status && filters.status !== "all") {
    filtered = filtered.filter((machine) => machine.status === filters.status);
  }
  if (filters.keyword && filters.keyword.trim()) {
    const keyword = filters.keyword.trim().toLowerCase();
    filtered = filtered.filter((machine) =>
      `${machine.name} ${machine.id} ${machine.org} ${machine.operator}`.toLowerCase().includes(keyword),
    );
  }
  if (filters.scope === "today") {
    filtered = filtered.filter((machine) => machine.area > 0);
  }
  if (filters.scope === "alerts") {
    filtered = filtered.filter((machine) => machine.alerts > 0);
  }
  return filtered;
}

function startRealtimePolling() {
  window.clearInterval(state.realtimeTimer);
  state.realtimeTimer = window.setInterval(() => {
    if (!document.hidden) void refreshRealtimeData();
  }, 3000);
}

async function refreshRealtimeData() {
  if (state.realtimeRefreshing) return;
  state.realtimeRefreshing = true;
  try {
    await refreshMachines();
  } finally {
    state.realtimeRefreshing = false;
  }
}

function renderMachineList() {
  const container = document.getElementById("machine-list");
  container.innerHTML = "";
  if (!state.machines.length) {
    container.innerHTML = `<div class="timeline-item"><p>暂无符合条件的农机</p></div>`;
    return;
  }

  state.machines.forEach((machine) => {
    const card = document.createElement("button");
    const isRealtime = isRealtimePositionSource(machine.position_source);
    card.className = `machine-card ${isRealtime ? "real-machine" : ""} ${machine.id === state.selectedMachineId ? "active" : ""}`;
    card.type = "button";
    
    // 格式化时间
    const workTime = machine.work_time || 0;
    const timeDisplay = workTime > 0 ? `${workTime.toFixed(1)}h` : '--';
    
    card.innerHTML = `
      <div class="machine-card-head">
        <h3>${machine.name}</h3>
        <span class="status-pill ${machine.status}">${statusText[machine.status]}</span>
      </div>
      <p>${isRealtime ? `<span class="real-source-badge">${positionSourceText(machine.position_source)}</span> · ` : ''}${machine.org} · ${typeText[machine.type]} · ${machine.operator}</p>
      <div class="machine-meta">
        <span>面积<strong>${machine.area.toFixed(1)}亩</strong></span>
        <span>速度<strong>${machine.speed.toFixed(1)}km/h</strong></span>
        <span>信号<strong>${machine.signal}%</strong></span>
        <span>作业时间<strong>${timeDisplay}</strong></span>
      </div>
    `;
    card.addEventListener("click", () => selectMachine(machine.id, { fitTrack: false, openPopup: true, showTrack: false }));
    container.appendChild(card);
  });
}

function renderMarkers() {
  state.machineLayer.clear();
  state.realMachineLayer.clear();
  state.markers.clear();
  state.machines.forEach((machine) => {
    const isRealtime = isRealtimePositionSource(machine.position_source);
    const layer = isRealtime ? state.realMachineLayer : state.machineLayer;
    const marker = layer.addHtmlMarker([machine.lat, machine.lng], {
      html: createMachineMarkerContent(machine),
      title: machine.name,
      size: [40, 40],
      anchor: [20, 20],
      popupAnchor: [0, -20],
      zIndex: machine.id === state.selectedMachineId ? 150 : (isRealtime ? 140 : 110),
    });
    marker.bindPopup(createMachinePopup(machine));
    marker.on("click", () => selectMachine(machine.id, { fitTrack: false, showTrack: false }));
    state.markers.set(machine.id, marker);
  });
}

function createMachineMarkerContent(machine) {
  const isRealtime = isRealtimePositionSource(machine.position_source);
  return `
    <div class="tractor-marker ${isRealtime ? "real-tractor-marker" : ""} ${machine.status} ${machine.id === state.selectedMachineId ? "selected" : ""}">
      <span class="tractor-marker-icon">${iconByType[machine.type]}</span>
      <span class="tractor-status-dot" aria-hidden="true"></span>
      ${isRealtime ? '<span class="realtime-pulse" aria-hidden="true"></span>' : ''}
      <span class="tractor-marker-label">${machine.name}</span>
    </div>
  `;
}

function createMachinePopup(machine) {
  const isRealtime = isRealtimePositionSource(machine.position_source);
  return `
    <div class="machine-popup">
      <h3>${machine.name}</h3>
      <p>${machine.id} · ${machine.operator || "未分配人员"}</p>
      <p>组织：${machine.org}</p>
      <p>状态：${statusText[machine.status]} · ${typeText[machine.type]}</p>
      <p>今日：${machine.area.toFixed(1)} 亩 · ${machine.speed.toFixed(1)} km/h · 信号 ${machine.signal}%</p>
      ${isRealtime ? `<p>定位来源：${positionSourceText(machine.position_source)}</p>` : ''}
      ${isRealtime ? `<p>协议终端号：${machine.device_no || "未绑定"}${machine.position_device_no ? ` · 上报设备 ${machine.position_device_no}` : ''}</p>` : ''}
      ${isRealtime ? `<p>最近上报：${machine.lastSeenAt || "尚未上报"}</p>` : ''}
      <button data-popup-machine="${machine.id}">${isRealtime ? "查看历史轨迹" : "查看计划路线"}</button>
    </div>
  `;
}

// ============================================================
//  农田渲染（显示为点，而不是绿色框框）
// ============================================================

function renderFields() {
  state.fieldLayer.clear();
  state.fieldMarkers = [];
  const taskFieldIds = new Set(state.tasks.map((task) => String(task.farmland_id)));
  const visibleFields = state.tasks.length
    ? state.fields.filter((field) => taskFieldIds.has(String(field.id)))
    : [];
  visibleFields.forEach((field) => {
    const marker = state.fieldLayer.addCircleMarker([field.lat, field.lng], {
      radius: getFieldMarkerRadius(),
      color: "#ffffff",
      fillColor: "#ff3b30",
      fillOpacity: 0.76,
      weight: 1.5,
      opacity: 0.92,
    });
    marker.bindTooltip(`${field.name} · ${field.crop} · ${field.area.toFixed(1)}亩`, {
      direction: "top",
      sticky: true,
      offset: [0, -5],
    });
    marker.on("click", () => {
      switchPanel("farms");
      highlightFieldCard(field.id);
    });
    state.fieldMarkers.push(marker);
  });
}

function getFieldMarkerRadius() {
  const zoom = state.map?.getZoom?.() || 13;
  if (zoom <= 10) return 2.5;
  if (zoom <= 12) return 3.5;
  if (zoom <= 14) return 5;
  return 7;
}

function updateFieldMarkerDensity() {
  const radius = getFieldMarkerRadius();
  const zoom = state.map.getZoom();
  state.fieldMarkers.forEach((marker) => {
    marker.setRadius(radius);
    marker.setStyle({
      color: "#ffffff",
      fillColor: "#ff3b30",
      fillOpacity: zoom <= 10 ? 0.48 : zoom <= 12 ? 0.62 : 0.76,
      weight: 1.5,
      opacity: 0.92,
    });
  });
}

async function refreshRealtimeTracks() {
  state.realTrackLayer.clear();
  state.realtimeTracks.clear();
  state.realTrackLayer.setVisible(false);
}

async function focusRealtimeTrack(machine, fitTrack, suppliedTrack = null) {
  stopPlayback({ keepTrack: false });
  state.activeTrack = null;
  if (suppliedTrack) {
    state.realtimeTracks.set(machine.id, suppliedTrack);
  } else {
    showToast("请先选择时间段查询历史轨迹");
    return false;
  }
  const track = suppliedTrack || state.realtimeTracks.get(machine.id);
  const points = Array.isArray(track?.points) ? track.points : [];
  if (!points.length) {
    state.realTrackLayer.clear();
    state.realTrackLayer.setVisible(false);
    showToast(`${machine.name} 尚未收到有效定位`);
    return false;
  }
  showSelectedRealtimeTrack(machine, track);
  const apiElapsedSeconds = Array.isArray(track?.elapsedSeconds) ? track.elapsedSeconds.map(Number) : [];
  const apiDuration = Number(track?.duration) || 0;
  const fallbackDuration = Math.max(1, (points.length - 1) * 5);
  const measuredDuration = Math.max(apiDuration, apiElapsedSeconds.at(-1) || 0);
  const sourceDuration = measuredDuration > 0 ? measuredDuration : fallbackDuration;
  const duration = Math.min(sourceDuration, 360);
  const sourceElapsedSeconds = apiElapsedSeconds.length === points.length && (points.length === 1 || apiElapsedSeconds.at(-1) > 0)
    ? apiElapsedSeconds
    : points.map((_, index) => (sourceDuration * index) / Math.max(1, points.length - 1));
  const elapsedSeconds = sourceElapsedSeconds.map((seconds) => (seconds / Math.max(1, sourceDuration)) * duration);

  state.activeTrack = {
    machineId: machine.id,
    points,
    duration,
    elapsedSeconds,
    actualDuration: sourceDuration,
    distance: Number(track?.distance) || 0,
    history: true,
  };
  state.playbackMarker = state.trackLayer.addHtmlMarker(points[0], {
    html: `<div class="playback-machine-marker realtime-playback-marker">🚜</div>`,
    size: [34, 34],
    anchor: [17, 17],
    zIndex: 160,
  }).bindTooltip(`${machine.name} 历史轨迹回放`);
  state.playbackElapsed = 0;
  document.getElementById("play-total").title = sourceDuration > duration
    ? `历史轨迹时长 ${formatTime(sourceDuration)}，已压缩为 ${formatTime(duration)} 回放`
    : `轨迹时长 ${formatTime(sourceDuration)}`;
  updatePlaybackElapsed(0);
  if (fitTrack) {
    fitBoundsWithUiPadding(points, { maxZoom: 17 });
  }
  return true;
}

function showSelectedRealtimeTrack(machine, track) {
  state.realTrackLayer.clear();
  const points = Array.isArray(track?.points) ? track.points : [];
  if (points.length > 1) {
    state.realTrackLayer.addPolyline(points, { color: "#ffffff", weight: 9, opacity: 0.78, zIndex: 69 });
    state.realTrackLayer.addPolyline(points, { color: "#d946ef", weight: 5, opacity: 0.96, showDir: true, zIndex: 70 });
  }
  if (points.length) {
    state.realTrackLayer.addCircleMarker(points[0], { radius: 5, fillColor: "#7e22ce", color: "#ffffff", weight: 2, zIndex: 71 });
  }
  state.realTrackLayer.setVisible(points.length > 0);
}

// ============================================================
//  轨迹渲染（农机 → 任务点的连线）
// ============================================================

async function selectMachine(machineId, options = {}) {
  const machine = state.allMachines.find((item) => item.id === machineId)
    || state.machines.find((item) => item.id === machineId);
  if (!machine) {
    return false;
  }
  state.selectedMachineId = machineId;
  state.trackVisible = options.showTrack !== false;
  renderMachineList();
  renderMarkers();
  if (!isRealtimePositionSource(machine.position_source)) {
    state.realTrackLayer.clear();
    state.realTrackLayer.setVisible(false);
  }
  if (options.showTrack === false) {
    stopPlayback({ keepTrack: false });
    state.trackLayer.clear();
    state.realTrackLayer.clear();
    state.realTrackLayer.setVisible(false);
  }
  const hasTrack = options.showTrack === false ? false : await drawTrack(machineId, options.fitTrack);
  if (options.openPopup) {
    const marker = state.markers.get(machineId);
    if (marker) {
      state.map.setView([machine.lat, machine.lng], Math.max(state.map.getZoom(), 9));
      marker.openPopup();
    }
  }
  return hasTrack;
}

async function drawTrackFromData(machineId, track, fitTrack = false) {
  if (!track) return false;
  return drawTrack(machineId, fitTrack, track);
}

// ============================================================
//  轨迹渲染（农机 → 任务点1 → 任务点2 → ...）
// ============================================================

// ============================================================
//  轨迹渲染（农机 → 任务点1 → 任务点2 → ... → 返回起点）
// ============================================================

async function drawTrack(machineId, fitTrack = false, suppliedTrack = null) {
  state.trackLayer.clear();
  state.playbackMarker = null;
  stopPlayback({ keepTrack: true });
  
  // 获取农机位置
  const machine = state.allMachines.find(m => m.id === machineId)
    || state.machines.find(m => m.id === machineId);
  if (!machine) {
    showToast('未找到该农机');
    return false;
  }

  if (isRealtimePositionSource(machine.position_source)) {
    if (!suppliedTrack) {
      state.realTrackLayer.clear();
      state.realTrackLayer.setVisible(false);
      state.trackVisible = false;
      showRealTrackQuery(machine);
      showToast("请先选择时间段查询历史轨迹");
      return false;
    }
    return focusRealtimeTrack(machine, fitTrack, suppliedTrack);
  }

  if (suppliedTrack?.points?.length) {
    state.activeTrack = { ...suppliedTrack, machineId, realtime: false };
    const points = suppliedTrack.points;
    state.trackLayer.addPolyline(points, { color: "#ffffff", weight: 9, opacity: 0.78, zIndex: 61 });
    state.trackLayer.addPolyline(points, { color: "#2f9df4", weight: 5, opacity: 0.92, showDir: true, zIndex: 62 });
    state.playbackMarker = state.trackLayer.addHtmlMarker(points[0], { html: `<div class="playback-machine-marker">🚜</div>`, size: [30, 30], anchor: [15, 15], zIndex: 140 });
    if (fitTrack) fitBoundsWithUiPadding(points, { maxZoom: 15 });
    return true;
  }
  
  // 获取该农机的所有任务（按 id 排序）
  const allTasks = await dataProvider.getTasks();
  const machineTasks = allTasks
    .filter(t => t.machine_id === machineId)
    .sort((a, b) => a.id - b.id);
  
  if (machineTasks.length === 0) {
    showToast('该农机暂无任务');
    state.trackLayer.addHtmlMarker([machine.lat, machine.lng], {
      html: `<div class="tractor-marker selected">🚜</div>`,
      size: [40, 40],
      anchor: [20, 20],
    }).bindPopup(`🚜 ${machine.name} (无任务)`);
    state.activeTrack = null;
    return false;
  }
  
  // ============================================================
  // 构建路径点列表：起点 → 任务点1 → 任务点2 → ... → 返回起点
  // ============================================================
  const allPoints = [];
  const allFieldInfo = [];
  
  // 起点：农机位置
  const startPoint = [machine.lat, machine.lng];
  allPoints.push(startPoint);
  allFieldInfo.push({
    type: 'start',
    name: machine.name,
    label: '🚜 出发地',
    lat: machine.lat,
    lng: machine.lng
  });
  
  // 依次添加任务点
  let totalDistance = 0;
  for (let i = 0; i < machineTasks.length; i++) {
    const task = machineTasks[i];
    const field = state.fields.find(f => f.id === task.farmland_id);
    if (!field) continue;
    
    allPoints.push([field.lat, field.lng]);
    allFieldInfo.push({
      type: 'task',
      taskId: task.id,
      name: field.name,
      label: `${i + 1}. 📍 ${field.name}`,
      operation: task.operation_type,
      status: task.status,
      lat: field.lat,
      lng: field.lng,
      index: i + 1,
      total: machineTasks.length
    });
    
    // 计算距离（累加）
    if (i === 0) {
      totalDistance += calculateDistance(
        [machine.lat, machine.lng],
        [field.lat, field.lng]
      );
    } else {
      const prevField = state.fields.find(f => f.id === machineTasks[i - 1].farmland_id);
      if (prevField) {
        totalDistance += calculateDistance(
          [prevField.lat, prevField.lng],
          [field.lat, field.lng]
        );
      }
    }
  }
  
  // ============================================================
  // ✅ 新增：添加返回起点的路径
  // ============================================================
  const lastTask = machineTasks[machineTasks.length - 1];
  const lastField = state.fields.find(f => f.id === lastTask.farmland_id);
  if (lastField) {
    // 添加返回起点的点
    allPoints.push(startPoint);
    allFieldInfo.push({
      type: 'return',
      name: '返回',
      label: '🏠 返回车库',
      lat: machine.lat,
      lng: machine.lng,
      index: machineTasks.length + 1,
      total: machineTasks.length + 1
    });
    
    // 累加返回距离
    totalDistance += calculateDistance(
      [lastField.lat, lastField.lng],
      [machine.lat, machine.lng]
    );
  }
  
  // ============================================================
  // 画轨迹线（分段颜色）
  // ============================================================
  const colors = ['#2f9df4', '#22b573', '#f6b73c', '#ff6b35', '#805ad5'];
  
  for (let i = 0; i < allPoints.length - 1; i++) {
    const segmentPoints = [allPoints[i], allPoints[i + 1]];
    const color = colors[i % colors.length];
    const isReturnSegment = (i === allPoints.length - 2);  // 最后一段是返回
    
    state.trackLayer.addPolyline(segmentPoints, {
      color: "#ffffff",
      weight: isReturnSegment ? 10 : 8,
      opacity: 0.6,
      zIndex: 61,
    });
    state.trackLayer.addPolyline(segmentPoints, {
      color: isReturnSegment ? '#e53e3e' : color,  // 返回段用红色
      weight: isReturnSegment ? 5 : 4,
      opacity: isReturnSegment ? 0.7 : 0.9,
      dashArray: isReturnSegment ? '8, 6' : (i === 0 ? '10, 5' : '8, 4'),
      showDir: !isReturnSegment,
      zIndex: 62,
    });
    
    // 在每段中间添加方向指示（返回段用特殊标记）
    const midPoint = [
      (segmentPoints[0][0] + segmentPoints[1][0]) / 2,
      (segmentPoints[0][1] + segmentPoints[1][1]) / 2
    ];
    const arrowColor = isReturnSegment ? '#e53e3e' : color;
    const arrowSymbol = isReturnSegment ? '↩' : '➜';
    state.trackLayer.addHtmlMarker(midPoint, {
      html: `<div class="route-arrow" style="color:${arrowColor};font-size:${isReturnSegment ? '16px' : '20px'};">${arrowSymbol}</div>`,
      size: [20, 20],
      anchor: [10, 10],
      zIndex: 80,
    });
  }
  
  // ============================================================
  // 显示标记点
  // ============================================================
  allFieldInfo.forEach((info, index) => {
    const isStart = info.type === 'start';
    const isTask = info.type === 'task';
    const isReturn = info.type === 'return';
    
    if (isStart) {
      state.trackLayer.addHtmlMarker([info.lat, info.lng], {
        html: `<div class="tractor-marker selected">🚜</div>`,
        size: [40, 40],
        anchor: [20, 20],
        zIndex: 120,
      }).bindPopup(`
        <strong>🚜 ${info.name}</strong><br>
        出发地/返回地
      `);
    }
    
    if (isTask) {
      const color = ['#ff6b35', '#22b573', '#f6b73c', '#2f9df4', '#805ad5'][info.index % 5];
      state.trackLayer.addHtmlMarker([info.lat, info.lng], {
        html: `<div class="route-task-marker" style="background:${color};">${info.index}</div>`,
        size: [26, 26],
        anchor: [13, 13],
        zIndex: 115,
      }).bindPopup(`
        <strong>📍 ${info.name}</strong><br>
        作业：${info.operation}<br>
        状态：${info.status}<br>
        第 ${info.index}/${info.total - 1} 个任务
      `);
    }
    
    if (isReturn) {
      state.trackLayer.addHtmlMarker([info.lat, info.lng], {
        html: `<div class="route-return-marker">🏠</div>`,
        size: [24, 24],
        anchor: [12, 12],
        zIndex: 116,
      }).bindPopup(`
        <strong>🏠 返回车库</strong><br>
        农机完成任务后返回出发位置
      `);
    }
  });

  state.playbackMarker = state.trackLayer.addHtmlMarker(startPoint, {
    html: `<div class="playback-machine-marker">🚜</div>`,
    size: [30, 30],
    anchor: [15, 15],
    zIndex: 140,
  });
  
  // ============================================================
  // 显示总距离信息（包含返回距离）
  // ============================================================
  const midPoint = [
    (allPoints[0][0] + allPoints[allPoints.length - 1][0]) / 2,
    (allPoints[0][1] + allPoints[allPoints.length - 1][1]) / 2
  ];
  state.trackLayer.addHtmlMarker(midPoint, {
    html: `<div class="route-distance-label">📏 计划直线距离 ${totalDistance.toFixed(2)} km · ${machineTasks.length}个任务</div>`,
    size: [240, 32],
    anchor: [120, 16],
    zIndex: 118,
  });
  
  // ============================================================
  // 图例（显示任务顺序 + 返回）
  // ============================================================
  const taskItems = allFieldInfo.filter(f => f.type === 'task');
  const legendHtml = `
    <div style="position:absolute;bottom:100px;right:20px;z-index:1000;background:rgba(255,255,255,0.95);padding:10px 14px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.15);font-size:12px;border:1px solid #e2e8f0;max-width:200px;">
      <div style="font-weight:bold;margin-bottom:6px;">📋 任务顺序</div>
      ${taskItems.map((f, i) => `
        <div style="display:flex;align-items:center;gap:8px;margin:3px 0;">
          <span style="display:inline-block;width:16px;height:16px;border-radius:50%;background:${['#ff6b35','#22b573','#f6b73c','#2f9df4','#805ad5'][i % 5]};color:white;text-align:center;font-size:10px;font-weight:bold;line-height:16px;">${i+1}</span>
          <span>${f.name}</span>
          <span style="color:#718096;font-size:11px;">${f.operation}</span>
        </div>
      `).join('')}
      <div style="display:flex;align-items:center;gap:8px;margin:3px 0;border-top:1px dashed #e2e8f0;padding-top:4px;">
        <span style="color:#e53e3e;">↩</span>
        <span style="color:#e53e3e;">返回车库</span>
      </div>
    </div>
  `;
  
  // 保存轨迹数据用于播放
  state.activeTrack = {
    machineId: machineId,
    points: allPoints,
    duration: allPoints.length * 60,
    elapsedSeconds: allPoints.map((_, index) => index * 60),
    actualDuration: allPoints.length * 60,
    distance: totalDistance,
    taskCount: machineTasks.length
  };
  
  if (fitTrack) {
    fitBoundsWithUiPadding(allPoints, { maxZoom: 13 });
  }
  return true;
}
// ============================================================
//  轨迹播放控制
// ============================================================

function setTrackCategory(category, options = {}) {
  state.trackCategory = category;
  document.querySelectorAll("[data-track-category]").forEach((button) => {
    button.classList.toggle("active", button.dataset.trackCategory === category);
  });
  if (options.render !== false) {
    renderTrackMachineList();
  }
}

function setTrackPanelTitle(title) {
  if (state.activePanel !== "tracks") return;
  document.getElementById("panel-kicker").textContent = "农机轨迹";
  document.getElementById("panel-title").textContent = title;
  const sectionTitle = document.querySelector("#tracks-view .section-title span");
  if (sectionTitle) {
    sectionTitle.textContent = title;
  }
}

function focusMachinePosition(machine, options = {}) {
  if (!machine || !state.map) return;
  const zoom = Math.max(state.map.getZoom(), options.zoom || 15);
  state.map.setView([machine.lat, machine.lng], zoom);
  if (options.openPopup) {
    const marker = state.markers.get(machine.id);
    marker?.openPopup();
  }
}

async function openRealTrackQuery(machineId, options = {}) {
  const machine = state.allMachines.find((item) => item.id === machineId)
    || state.machines.find((item) => item.id === machineId);
  if (!machine) {
    showToast("未找到该实机");
    return false;
  }
  switchPanel("tracks");
  setTrackCategory("real", { render: false });
  await selectMachine(machine.id, { fitTrack: false, showTrack: false });
  showRealTrackQuery(machine);
  renderTrackMachineList();
  focusMachinePosition(machine, options);
  document.getElementById("real-track-query-panel")?.scrollIntoView({ block: "nearest" });
  showToast(`已打开 ${machine.name} 历史轨迹查询`);
  return true;
}

function renderTrackMachineList() {
  const container = document.getElementById("track-machine-list");
  const summary = document.getElementById("track-machine-summary");
  const search = (document.getElementById("track-machine-search")?.value || "").trim().toLowerCase();
  const allMachines = state.allMachines.length ? state.allMachines : state.machines;
  const machines = allMachines.filter((machine) => {
    const isRealtime = isRealtimePositionSource(machine.position_source);
    if (state.trackCategory === "real" && !isRealtime) return false;
    if (state.trackCategory === "demo" && isRealtime) return false;
    if (!search) return true;
    return `${machine.id} ${machine.name} ${machine.operator || ""}`.toLowerCase().includes(search);
  });
  container.innerHTML = "";
  summary.textContent = search
    ? `共 ${allMachines.length} 台农机，当前匹配 ${machines.length} 台`
    : `共 ${allMachines.length} 台农机，全部可查询`;

  const demoCount = allMachines.filter((machine) => !isRealtimePositionSource(machine.position_source)).length;
  const realCount = allMachines.length - demoCount;
  summary.textContent = search
    ? `共 ${demoCount} 台样机、${realCount} 台实机，当前匹配 ${machines.length} 台`
    : `共 ${demoCount} 台样机、${realCount} 台实机，可选择查看轨迹`;

  if (!machines.length) {
    container.innerHTML = `<div class="timeline-item"><p>没有匹配的农机</p></div>`;
    return;
  }

  machines.forEach((machine) => {
    const taskCount = state.tasks.filter((task) => task.machine_id === machine.id).length;
    const isRealtime = isRealtimePositionSource(machine.position_source);
    const trackLabel = isRealtime
      ? (machine.has_realtime_position ? "历史轨迹" : "暂无定位")
      : (taskCount ? `${taskCount}个任务` : "暂无任务");
    const row = document.createElement("button");
    row.className = `compact-row ${machine.id === state.selectedMachineId ? "active" : ""}`;
    row.type = "button";
    row.innerHTML = `
      <span class="track-machine-info">
        <strong>${machine.name}</strong>
        <small>${machine.id} · ${machine.operator || "未绑定工作人员"}</small>
      </span>
      <span class="track-machine-meta">
        <span class="status-pill ${machine.status}">${statusText[machine.status] || machine.status}</span>
        <small class="${(isRealtime && machine.has_realtime_position) || taskCount ? "has-track" : "no-track"}">${trackLabel}</small>
      </span>
    `;
    row.addEventListener("click", async () => {
      if (isRealtime) {
        await openRealTrackQuery(machine.id, { zoom: 16 });
        return;
      }
      const hasTrack = await selectMachine(machine.id, { fitTrack: true, showTrack: true });
      await loadTrackHistory(machine);
      showToast(hasTrack
        ? `已载入 ${machine.name} 计划路线`
        : `${machine.name} 当前暂无任务路线`);
    });
    container.appendChild(row);
  });
}

async function loadTrackHistory(machine) {
  const panel = document.getElementById("track-history-panel");
  const realPanel = document.getElementById("real-track-query-panel");
  if (isRealtimePositionSource(machine.position_source)) {
    panel?.classList.add("hidden");
    showRealTrackQuery(machine);
    return;
  }
  setTrackPanelTitle("计划路线");
  realPanel?.classList.add("hidden");
  const select = document.getElementById("track-history-select");
  const title = document.getElementById("track-history-title");
  const status = document.getElementById("track-history-status");
  if (!panel || !select) return;
  title.textContent = `${machine.name} 历史轨迹`;
  status.textContent = "正在加载";
  panel.classList.remove("hidden");
  const history = await dataProvider.getMachineTrackHistory(machine.id);
  state.trackHistory.set(machine.id, history);
  select.innerHTML = history.length
    ? history.map((item, index) => `<option value="${item.id}">${item.label || item.trackDate || `轨迹 ${index + 1}`} · ${Number(item.distance || 0).toFixed(2)} km</option>`).join("")
    : `<option value="">暂无历史轨迹</option>`;
  status.textContent = history.length ? `共 ${history.length} 条记录` : "暂无历史记录";
}

function formatDateTimeLocal(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function localDayStart(date) {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  return result;
}

function setRealTrackRange(range) {
  const startInput = document.getElementById("real-track-start");
  const endInput = document.getElementById("real-track-end");
  if (!startInput || !endInput) return;
  const now = new Date();
  let start = new Date(now);
  let end = new Date(now);
  const today = localDayStart(now);
  const dayOfWeek = (today.getDay() + 6) % 7;
  const thisWeek = new Date(today);
  thisWeek.setDate(thisWeek.getDate() - dayOfWeek);
  if (range === "today") {
    start = today;
  } else if (range === "yesterday") {
    start = new Date(today);
    start.setDate(start.getDate() - 1);
    end = new Date(today);
  } else if (range === "this-week") {
    start = thisWeek;
  } else if (range === "last-week") {
    end = new Date(thisWeek);
    start = new Date(thisWeek);
    start.setDate(start.getDate() - 7);
    end.setMinutes(end.getMinutes() - 1);
  } else {
    start = new Date(now.getTime() - 60 * 60 * 1000);
  }
  startInput.value = formatDateTimeLocal(start);
  endInput.value = formatDateTimeLocal(end);
  document.querySelectorAll("[data-real-track-range]").forEach((button) => {
    button.classList.toggle("active", button.dataset.realTrackRange === range);
  });
}

function showRealTrackQuery(machine) {
  const panel = document.getElementById("real-track-query-panel");
  const title = document.getElementById("real-track-query-title");
  const status = document.getElementById("real-track-query-status");
  const result = document.getElementById("real-track-query-result");
  if (!panel) return;
  panel.classList.remove("hidden");
  setTrackPanelTitle("实机轨迹查询");
  if (title) title.textContent = `${machine.name} 实机轨迹查询`;
  if (status) status.textContent = "请选择时间段后查询历史轨迹";
  if (result) result.textContent = "";
  setRealTrackRange("last-hour");
}

async function handleRealTrackQuery(event) {
  event.preventDefault();
  const machine = state.allMachines.find((item) => item.id === state.selectedMachineId);
  const start = document.getElementById("real-track-start").value;
  const end = document.getElementById("real-track-end").value;
  const submit = document.getElementById("real-track-query-submit");
  const status = document.getElementById("real-track-query-status");
  const result = document.getElementById("real-track-query-result");
  if (!machine || !isRealtimePositionSource(machine.position_source)) return;
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (!start || !end || Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    status.textContent = "请选择完整的开始和结束时间";
    return;
  }
  if (startDate >= endDate) {
    status.textContent = "开始时间必须早于结束时间";
    return;
  }
  if (endDate - startDate > 7 * 24 * 60 * 60 * 1000) {
    status.textContent = "单次最多查询 7 天";
    return;
  }
  submit.disabled = true;
  status.textContent = "正在查询实机轨迹...";
  result.textContent = "";
  try {
    const track = await dataProvider.getMachineTrack(machine.id, { start, end });
    if (!track || !track.points?.length) {
      status.textContent = "该时间段没有定位记录";
      stopPlayback({ keepTrack: false });
      state.activeTrack = null;
      state.trackLayer.clear();
      state.realTrackLayer.clear();
      state.realTrackLayer.setVisible(false);
      return;
    }
    state.trackVisible = true;
    await drawTrackFromData(machine.id, track, true);
    status.textContent = track.sampled ? "轨迹点较多，已自动抽稀显示" : "查询完成";
    result.textContent = `${track.points.length} 个点 · ${Number(track.distance || 0).toFixed(2)} km`;
  } catch (error) {
    status.textContent = error.message || "轨迹查询失败";
  } finally {
    submit.disabled = false;
  }
}

async function togglePlayback() {
  if (!state.activeTrack) {
    const selectedMachine = state.allMachines.find((machine) => machine.id === state.selectedMachineId);
    if (!selectedMachine) {
      showToast("请先选择要播放的轨迹");
      return;
    }
    if (isRealtimePositionSource(selectedMachine.position_source)) {
      await openRealTrackQuery(selectedMachine.id);
      showToast("请先查询历史轨迹后再播放");
      return;
    }
    const loaded = await selectMachine(selectedMachine.id, { fitTrack: true, showTrack: true });
    if (!loaded || !state.activeTrack) return;
  }
  if (state.playing) {
    pausePlayback();
  } else {
    startPlayback();
  }
}

function startPlayback() {
  if (!state.activeTrack || state.activeTrack.points.length < 2) {
    showToast("轨迹至少需要两个点才能播放");
    return;
  }
  if (state.playbackElapsed >= state.activeTrack.duration) {
    updatePlaybackElapsed(0);
  }
  state.playing = true;
  document.getElementById("play-btn").innerHTML = `<i data-lucide="pause"></i>`;
  lucide.createIcons();
  state.playbackLastFrame = performance.now();
  state.playbackTimer = window.requestAnimationFrame(animatePlayback);
}

function pausePlayback() {
  state.playing = false;
  window.cancelAnimationFrame(state.playbackTimer);
  state.playbackTimer = null;
  document.getElementById("play-btn").innerHTML = `<i data-lucide="play"></i>`;
  lucide.createIcons();
}

function stopPlayback(options = {}) {
  pausePlayback();
  state.playbackIndex = 0;
  state.playbackElapsed = 0;
  document.getElementById("play-progress").value = 0;
  if (state.activeTrack) {
    updatePlaybackElapsed(0);
  }
  if (!options.keepTrack && state.trackLayer) {
    state.trackLayer.clear();
    state.playbackMarker = null;
  }
}

function animatePlayback(timestamp) {
  if (!state.playing || !state.activeTrack) return;
  const speed = Number(document.getElementById("speed-select").value) || 1;
  const deltaSeconds = Math.max(0, (timestamp - state.playbackLastFrame) / 1000) * speed;
  state.playbackLastFrame = timestamp;
  updatePlaybackElapsed(state.playbackElapsed + deltaSeconds);
  if (state.playbackElapsed >= state.activeTrack.duration) {
    pausePlayback();
    return;
  }
  state.playbackTimer = window.requestAnimationFrame(animatePlayback);
}

function updatePlaybackPosition(index) {
  if (!state.activeTrack) {
    return;
  }
  const safeIndex = Math.min(Math.max(index, 0), state.activeTrack.points.length - 1);
  const elapsedSeconds = state.activeTrack.elapsedSeconds || [];
  updatePlaybackElapsed(elapsedSeconds[safeIndex] ?? 0);
}

function updatePlaybackElapsed(elapsedSeconds) {
  if (!state.activeTrack) return;
  const points = state.activeTrack.points;
  const duration = Math.max(1, state.activeTrack.duration);
  const timeline = Array.isArray(state.activeTrack.elapsedSeconds)
    && state.activeTrack.elapsedSeconds.length === points.length
    ? state.activeTrack.elapsedSeconds
    : points.map((_, index) => (duration * index) / Math.max(1, points.length - 1));
  const safeElapsed = Math.min(Math.max(Number(elapsedSeconds) || 0, 0), duration);
  let segmentIndex = Math.max(0, points.length - 1);
  for (let index = 0; index < timeline.length - 1; index += 1) {
    if (safeElapsed <= timeline[index + 1]) {
      segmentIndex = index;
      break;
    }
  }

  const startPoint = points[segmentIndex];
  const endPoint = points[Math.min(segmentIndex + 1, points.length - 1)];
  const segmentStart = timeline[segmentIndex] ?? 0;
  const segmentEnd = timeline[Math.min(segmentIndex + 1, timeline.length - 1)] ?? duration;
  const segmentDuration = Math.max(0.001, segmentEnd - segmentStart);
  const ratio = Math.min(1, Math.max(0, (safeElapsed - segmentStart) / segmentDuration));
  const point = [
    startPoint[0] + (endPoint[0] - startPoint[0]) * ratio,
    startPoint[1] + (endPoint[1] - startPoint[1]) * ratio,
  ];

  state.playbackIndex = segmentIndex;
  state.playbackElapsed = safeElapsed;
  if (state.playbackMarker) {
    state.playbackMarker.setPosition(point);
  }
  const progress = (safeElapsed / duration) * 100;
  document.getElementById("play-progress").value = progress;
  updatePlaybackClock(Math.round(safeElapsed), state.activeTrack.duration);
}

function handleProgressChange(event) {
  if (!state.activeTrack) {
    return;
  }
  const value = Number(event.target.value);
  updatePlaybackElapsed((state.activeTrack.duration * value) / 100);
}

function restartPlaybackIfNeeded() {
  if (state.playing) {
    pausePlayback();
    startPlayback();
  }
}

function updatePlaybackClock(currentSeconds, totalSeconds) {
  document.getElementById("play-current").textContent = formatTime(currentSeconds);
  document.getElementById("play-total").textContent = formatTime(totalSeconds);
}

function formatTime(seconds) {
  const date = new Date(seconds * 1000);
  return date.toISOString().slice(11, 19);
}

// ============================================================
//  其他渲染函数
// ============================================================

async function renderSupportingViews() {
  renderTrackMachineList();
  renderVideos(await dataProvider.getVideoStreams());
  renderHistoryVideos();
  await renderTerminals();
  renderMessages(await dataProvider.getMessages());
  renderTasks(await dataProvider.getTasks());
  renderFieldList();
}

function renderVideos(streams) {
  const container = document.getElementById("video-grid");
  container.innerHTML = "";
  streams.forEach((stream) => {
    const card = document.createElement("article");
    card.className = "video-card";
    card.innerHTML = `
      <div class="video-screen">
        <i data-lucide="video-off"></i>
      </div>
      <footer>
        <span>${stream.machineName}</span>
        <span>${stream.status}</span>
      </footer>
    `;
    container.appendChild(card);
  });
  lucide.createIcons();
}

function renderHistoryVideos() {
  const list = document.getElementById("history-video-list");
  list.innerHTML = [
    ["08:30", "耕牛 1号", "试验田 A 作业片段 · HLS 待接入"],
    ["昨日 17:42", "耕牛 2号", "驾驶室录像 · 对象存储待接入"],
  ]
    .map(
      ([time, title, body]) => `
        <article class="timeline-item">
          <div class="timeline-head"><strong>${title}</strong><span>${time}</span></div>
          <p>${body}</p>
        </article>
      `,
    )
    .join("");
}

async function renderTerminals() {
  const stats = await dataProvider.getTerminalStats();
  const chart = echarts.init(document.getElementById("terminal-chart"));
  state.terminalChart = chart;
  chart.setOption({
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#5b7486" } },
    color: ["#22b573", "#2f9df4", "#f6b73c", "#99a7b2"],
    series: [
      {
        name: "终端状态",
        type: "pie",
        radius: ["42%", "68%"],
        center: ["50%", "42%"],
        label: { formatter: "{b}\n{c}" },
        data: [
          { name: "作业中", value: stats.working },
          { name: "待命", value: stats.idle },
          { name: "离线", value: stats.offline },
        ],
      },
    ],
  });
  document.getElementById("terminal-list").innerHTML = `
    <div class="metric-row"><span>平均信号强度</span><strong>${stats.avgSignal}%</strong></div>
    <div class="metric-row"><span>连接正常终端</span><strong>${stats.online}</strong></div>
    <div class="metric-row"><span>离线终端</span><strong>${stats.offline}</strong></div>
  `;
}

function renderMessages(messages) {
  document.getElementById("messages-list").innerHTML = messages
    .map(
      (message) => `
        <article class="timeline-item">
          <div class="timeline-head"><strong>${message.title}</strong><span>${message.time}</span></div>
          <p>${message.body}</p>
        </article>
      `,
    )
    .join("");
}

function renderTasks(tasks) {
  const container = document.getElementById("task-list");
  if (!tasks.length) {
    container.innerHTML = `<div class="empty-panel">暂无任务，可使用上方表单手动分配给工作人员。</div>`;
    return;
  }

  container.innerHTML = tasks
    .map((task) => {
      const machine = state.allMachines.find((item) => item.id === task.machine_id)
        || state.machines.find((item) => item.id === task.machine_id);
      const statusClass = task.status === '已完成' ? 'complete' : task.status === '已接收' ? 'working' : 'pending';
      const deleteAction = task.status === '已完成' ? `
        <button class="task-delete-button" type="button" data-delete-task="${task.id}" title="删除已完成任务">
          <i data-lucide="trash-2"></i>
          <span>删除</span>
        </button>
      ` : '';
      return `
        <article class="task-card">
          <div class="task-card-head">
            <h3>${task.operation_type}</h3>
            <span class="status-pill ${statusClass}">${task.status}</span>
          </div>
          <div class="task-card-body">
            <p>${machine?.name || task.machine_id} · ${task.farmland_id}</p>
            ${deleteAction}
          </div>
        </article>
      `;
    })
    .join("");
  lucide.createIcons();
}

function renderFieldList() {
  const container = document.getElementById("field-list");
  container.innerHTML = "";
  state.fields.forEach((field) => {
    const card = document.createElement("button");
    card.className = "field-card";
    card.id = `field-card-${field.id}`;
    card.type = "button";
    card.innerHTML = `
      <div class="field-card-head">
        <h3>${field.name}</h3>
        <span class="status-pill">${field.status}</span>
      </div>
      <p>${field.crop} · ${field.area} 亩</p>
    `;
    card.addEventListener("click", () => {
      fitBoundsWithUiPadding([[field.lat - 0.01, field.lng - 0.01], [field.lat + 0.01, field.lng + 0.01]], { maxZoom: 13 });
      highlightFieldCard(field.id);
    });
    container.appendChild(card);
  });
}

function highlightFieldCard(fieldId) {
  document.querySelectorAll(".field-card").forEach((item) => item.classList.remove("active"));
  const target = document.getElementById(`field-card-${fieldId}`);
  if (target) {
    target.classList.add("active");
    target.scrollIntoView({ block: "nearest" });
  }
}

// ============================================================
//  UI 控制函数
// ============================================================

function switchPanel(panel) {
  state.activePanel = panel;
  document.getElementById("panel").classList.remove("collapsed");
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.panel === panel);
  });
  document.querySelectorAll(".panel-view").forEach((view) => view.classList.remove("active"));
  document.getElementById(`${panel}-view`).classList.add("active");
  const labels = {
    dashboard: ["工作台", "农机列表"],
    assignment: ["调度中心", "任务分配"], 
    tracks: ["农机轨迹", "轨迹查询"],
    video: ["视频中心", "农机视频"],
    historyVideo: ["视频中心", "历史视频"],
    terminals: ["监管中心", "终端状态"],
    messages: ["消息中心", "站内消息"],
    tasks: ["作业中心", "作业管理"],
    farms: ["农场中心", "农场管理"],
    system: ["系统中心", "接口与权限"],
  };
  document.getElementById("panel-kicker").textContent = labels[panel][0];
  document.getElementById("panel-title").textContent = labels[panel][1];
  if (panel === "terminals" && state.terminalChart) {
    setTimeout(() => state.terminalChart.resize(), 50);
  }
}

function handleNavClick(panel) {
  window.clearTimeout(state.navClickTimer);
  state.navClickTimer = window.setTimeout(() => switchPanel(panel), 180);
}

function handleNavDoubleClick(panel) {
  window.clearTimeout(state.navClickTimer);
  if (state.activePanel !== panel) {
    switchPanel(panel);
    return;
  }
  document.getElementById("panel").classList.toggle("collapsed");
}

function switchLayer(type) {
  document.getElementById("layer-satellite").classList.toggle("active", type === "satellite");
  document.getElementById("layer-street").classList.toggle("active", type === "street");
  state.map.setBaseLayer(type);
}

function fitAllMachines() {
  const visibleMachines = state.demoLayersVisible
    ? state.machines
    : state.allMachines.filter((machine) => isRealtimePositionSource(machine.position_source));
  if (visibleMachines.length === 0) return;
  const points = visibleMachines.map((machine) => [machine.lat, machine.lng]);
  fitBoundsWithUiPadding(points);
}

function toggleDemoLayers() {
  state.demoLayersVisible = !state.demoLayersVisible;
  state.machineLayer.setVisible(state.demoLayersVisible);
  state.fieldLayer.setVisible(state.demoLayersVisible);
  state.trackLayer.setVisible(state.demoLayersVisible);
  const button = document.getElementById("toggle-demo");
  button.classList.toggle("active", state.demoLayersVisible);
  button.title = state.demoLayersVisible ? "隐藏演示农机、农田和计划轨迹" : "显示演示农机、农田和计划轨迹";
  button.querySelector("span").textContent = state.demoLayersVisible ? "演示开" : "演示关";
  if (!state.demoLayersVisible) {
    pausePlayback();
  }
  showToast(state.demoLayersVisible ? "已恢复演示农机、农田和计划轨迹" : "已隐藏演示图层，真实农机继续显示");
}

async function handleGlobalSearch(event) {
  const keyword = event.target.value.trim().toLowerCase();
  if (keyword.length < 2) {
    return;
  }
  const machine = state.allMachines.find((item) =>
    `${item.name} ${item.id} ${item.org}`.toLowerCase().includes(keyword),
  );
  if (machine) {
    await selectMachine(machine.id, { fitTrack: false, openPopup: true, showTrack: false });
    switchPanel("dashboard");
    showToast(`已定位 ${machine.name}`);
    return;
  }
  const field = state.fields.find((item) => `${item.name} ${item.crop}`.toLowerCase().includes(keyword));
  if (field) {
    switchPanel("farms");
    fitBoundsWithUiPadding([[field.lat - 0.01, field.lng - 0.01], [field.lat + 0.01, field.lng + 0.01]], { maxZoom: 13 });
    highlightFieldCard(field.id);
    showToast(`已定位 ${field.name}`);
  }
}

function fitBoundsWithUiPadding(boundsLike, options = {}) {
  if (!boundsLike || (Array.isArray(boundsLike) && boundsLike.length === 0)) return;
  state.map.fitBounds(boundsLike, {
    animate: true,
    maxZoom: options.maxZoom || 15,
    paddingTopLeft: mapPadding.topLeft,
    paddingBottomRight: mapPadding.bottomRight,
  });
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-popup-machine]");
  if (button) {
    event.preventDefault();
    const machineId = button.dataset.popupMachine;
    const machine = state.allMachines.find((item) => item.id === machineId)
      || state.machines.find((item) => item.id === machineId);
    if (machine && isRealtimePositionSource(machine.position_source)) {
      await openRealTrackQuery(machineId, { zoom: 16 });
      return;
    }
    switchPanel("tracks");
    const hasTrack = await selectMachine(machineId, { fitTrack: true, showTrack: true });
    if (machine) {
      await loadTrackHistory(machine);
    }
    showToast(hasTrack ? "已载入计划路线" : "当前暂无任务路线");
  }
});

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2200);
}

window.addEventListener("resize", () => {
  state.map?.invalidateSize();
  state.terminalChart?.resize();
});
