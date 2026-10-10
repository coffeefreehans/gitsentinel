// GitSentinel Frontend Application Logic

let state = {
  currentTab: 'repos',
  repos: [],
  keys: [],
  gitUser: {},
  identities: [],
  sshHosts: [],
  scanPaths: [],
  scanDepth: 5,
  activeIdentityForApply: null,
  notifications: [],
  settings: {},
  globalHooksEnabled: false,
  ws: null
};

// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  lucide.createIcons();
  initWebSocket();
  await loadAllData();
});

async function loadAllData() {
  await Promise.all([
    fetchRepos(),
    fetchKeys(),
    fetchIdentities(),
    fetchNotifications(),
    fetchSettings()
  ]);
  lucide.createIcons();
}

// --- WebSocket Connection ---
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  try {
    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
      document.getElementById("ws-indicator").className = "w-2 h-2 rounded-full bg-emerald-400";
      document.getElementById("ws-label").textContent = "实时在线";
    };

    state.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "notification") {
          handleIncomingNotification(msg.data);
        }
      } catch (e) {
        console.error("WS message parse error:", e);
      }
    };

    state.ws.onclose = () => {
      document.getElementById("ws-indicator").className = "w-2 h-2 rounded-full bg-rose-500 animate-pulse";
      document.getElementById("ws-label").textContent = "重连中...";
      setTimeout(initWebSocket, 3000);
    };

    state.ws.onerror = () => {
      state.ws.close();
    };
  } catch (e) {
    console.error("WebSocket failed to initialize:", e);
  }
}

function handleIncomingNotification(notif) {
  state.notifications.unshift(notif);
  renderNotifications();
  showWebToast(notif.title, notif.message, notif.type);
  
  // Trigger Native OS Desktop Notification (Windows Action Center / Toast)
  if ("Notification" in window) {
    if (Notification.permission === "granted") {
      try {
        new Notification(notif.title || "GitSentinel 提醒", {
          body: notif.message || "",
          icon: "/assets/icon.png"
        });
      } catch (e) {
        console.warn("Native Notification error:", e);
      }
    } else if (Notification.permission !== "denied") {
      Notification.requestPermission().then(p => {
        if (p === "granted") {
          new Notification(notif.title || "GitSentinel 提醒", {
            body: notif.message || "",
            icon: "/assets/icon.png"
          });
        }
      });
    }
  }

  // Show unread indicator if not on notifs tab
  if (state.currentTab !== 'notifs') {
    const unread = document.getElementById("badge-unread-notif");
    if (unread) unread.classList.remove("hidden");
  }

  // Refresh repos if commit or fetch happened
  if (notif.type === 'commit' || notif.type === 'remote_update') {
    fetchRepos();
  }
}

// --- Tab Switching ---
function switchTab(tabId) {
  state.currentTab = tabId;
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach(el => {
    el.className = "tab-btn px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center space-x-1.5 text-slate-400 hover:text-slate-200";
  });

  const activeContent = document.getElementById(`tab-content-${tabId}`);
  if (activeContent) activeContent.classList.remove("hidden");

  const activeBtn = document.getElementById(`tab-btn-${tabId}`);
  if (activeBtn) {
    activeBtn.className = "tab-btn px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center space-x-1.5 text-sky-400 bg-dark-700 shadow-sm";
  }

  if (tabId === 'notifs') {
    const unread = document.getElementById("badge-unread-notif");
    if (unread) unread.classList.add("hidden");
  }

  lucide.createIcons();
}

// --- Data Fetching ---

async function fetchRepos() {
  try {
    const res = await fetch("/api/repos");
    const data = await res.json();
    state.repos = data.repos || [];
    state.globalHooksEnabled = !!data.global_hooks_enabled;
    updateOverviewStats();
    renderRepos();
  } catch (e) {
    console.error("Fetch repos failed:", e);
  }
}

async function rescanAllRepos() {
  const spinner = document.getElementById("rescan-spinner");
  if (spinner) spinner.classList.add("animate-spin");
  try {
    const res = await fetch("/api/repos/scan", { method: "POST" });
    const data = await res.json();
    state.repos = data.repos || [];
    state.globalHooksEnabled = !!data.global_hooks_enabled;
    updateOverviewStats();
    renderRepos();
    showWebToast("扫描完成", `共检测到 ${state.repos.length} 个 Git 仓库`, "info");
  } catch (e) {
    showWebToast("扫描失败", e.message, "danger");
  } finally {
    if (spinner) spinner.classList.remove("animate-spin");
  }
}

async function fetchKeys() {
  try {
    const res = await fetch("/api/keys");
    const data = await res.json();
    state.keys = data.keys || [];
    state.gitUser = data.git_user || {};
    renderKeys();
    updateGitUserDisplay();
  } catch (e) {
    console.error("Fetch keys failed:", e);
  }
}

async function fetchNotifications() {
  try {
    const res = await fetch("/api/notifications");
    const data = await res.json();
    state.notifications = data.notifications || [];
    renderNotifications();
  } catch (e) {
    console.error("Fetch notifications failed:", e);
  }
}

async function fetchSettings() {
  try {
    const res = await fetch("/api/settings");
    state.settings = await res.json();
    renderSettings();
  } catch (e) {
    console.error("Fetch settings failed:", e);
  }
}

// --- Rendering Repositories ---

function updateOverviewStats() {
  const total = state.repos.length;
  const dirty = state.repos.filter(r => !r.is_clean).length;
  const sync = state.repos.filter(r => r.ahead > 0 || r.behind > 0).length;

  document.getElementById("stat-total-repos").textContent = total;
  document.getElementById("stat-dirty-repos").textContent = dirty;
  document.getElementById("stat-sync-repos").textContent = sync;
  document.getElementById("badge-repo-count").textContent = total;

  const globalText = document.getElementById("stat-global-intercept-text");
  const globalIcon = document.getElementById("stat-global-intercept-icon");
  const masterBtn = document.getElementById("btn-toggle-global-master");
  const masterBtnText = document.getElementById("btn-toggle-global-master-text");
  const badgeGlobal = document.getElementById("badge-global-status");

  if (state.globalHooksEnabled) {
    globalText.textContent = "已开启 (全系统生效)";
    globalText.className = "text-sm font-semibold text-emerald-400";
    globalIcon.className = "w-12 h-12 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center";
    if (masterBtn) masterBtn.className = "w-full sm:w-auto px-5 py-2.5 rounded-xl text-xs font-bold text-white transition flex items-center justify-center space-x-2 shadow-lg bg-emerald-600 hover:bg-emerald-500";
    if (masterBtnText) masterBtnText.textContent = "全局拦截: 已开启";
    if (badgeGlobal) badgeGlobal.className = "w-2 h-2 rounded-full bg-emerald-400 ml-1";
  } else {
    globalText.textContent = "已关闭 (单仓库模式)";
    globalText.className = "text-sm font-semibold text-slate-400";
    globalIcon.className = "w-12 h-12 rounded-xl bg-slate-500/10 text-slate-400 flex items-center justify-center";
    if (masterBtn) masterBtn.className = "w-full sm:w-auto px-5 py-2.5 rounded-xl text-xs font-bold text-white transition flex items-center justify-center space-x-2 shadow-lg bg-dark-700 hover:bg-dark-600";
    if (masterBtnText) masterBtnText.textContent = "全局拦截: 已关闭";
    if (badgeGlobal) badgeGlobal.className = "w-2 h-2 rounded-full bg-slate-500 ml-1";
  }

}

function renderRepos(filteredList = null) {
  const container = document.getElementById("repos-container");
  const emptyState = document.getElementById("repos-empty-state");
  const list = filteredList !== null ? filteredList : state.repos;

  if (list.length === 0) {
    container.innerHTML = "";
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  container.innerHTML = list.map(repo => {
    // Branch & Status
    const isClean = repo.is_clean;
    const cleanBadge = isClean 
      ? `<span class="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs">干净</span>`
      : `<span class="px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-400 border border-amber-500/20 text-xs font-medium">${repo.staged_count + repo.unstaged_count + repo.untracked_count} 项变动</span>`;

    // Sync status (Ahead / Behind)
    let syncBadge = "";
    if (repo.ahead > 0 || repo.behind > 0) {
      syncBadge = `
        <div class="flex items-center space-x-1.5 text-xs">
          ${repo.ahead > 0 ? `<span class="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono" title="超前远程 ${repo.ahead} 个提交">↑ ${repo.ahead}</span>` : ''}
          ${repo.behind > 0 ? `<span class="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono animate-pulse" title="落后远程 ${repo.behind} 个提交，请及时拉取！">↓ ${repo.behind}</span>` : ''}
        </div>
      `;
    }

    // Bound Key
    const boundKey = repo.bound_ssh_key 
      ? `<span class="px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 text-[11px] truncate max-w-[140px]" title="${repo.bound_ssh_key}">🔑 ${repo.bound_ssh_key.split('/').pop().split('\\').pop()}</span>`
      : `<span class="px-2 py-0.5 rounded bg-dark-700 text-slate-400 text-[11px]">系统默认 SSH</span>`;

    // Intercept switch status
    const interceptActive = state.globalHooksEnabled || repo.is_intercept_enabled;
    const interceptBtnClass = repo.is_intercept_enabled 
      ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" 
      : "text-slate-400 bg-dark-800 border-dark-700";

    return `
      <div class="glass-card rounded-2xl p-4 flex flex-col justify-between space-y-3 transition duration-200">
        <!-- Top Bar -->
        <div class="space-y-1">
          <div class="flex items-start justify-between">
            <h3 class="font-bold text-sm text-white truncate max-w-[200px]" title="${repo.path}">${repo.name}</h3>
            <div class="flex items-center space-x-1.5">
              ${cleanBadge}
              ${syncBadge}
            </div>
          </div>
          <p class="text-[11px] text-slate-400 truncate font-mono" title="${repo.path}">${repo.path}</p>
        </div>

        <!-- Branch & Commit Info -->
        <div class="bg-dark-900/60 rounded-xl p-2.5 border border-dark-700/60 space-y-1.5 text-xs">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-1.5 text-slate-300">
              <i data-lucide="git-branch" class="w-3.5 h-3.5 text-sky-400"></i>
              <span class="font-semibold text-sky-300 font-mono">${repo.branch}</span>
            </div>
            <div class="flex items-center space-x-1">
              <span class="text-[10px] text-slate-500">已暂存: ${repo.staged_count}</span>
              <span class="text-slate-600">|</span>
              <span class="text-[10px] text-slate-500">未暂存: ${repo.unstaged_count}</span>
            </div>
          </div>

          <!-- Last Commit info -->
          ${repo.last_commit ? `
            <div class="pt-1 border-t border-dark-800 flex items-center justify-between text-[11px] text-slate-400">
              <span class="truncate max-w-[180px]" title="${repo.last_commit.message}">${repo.last_commit.message}</span>
              <span class="text-[10px] text-slate-500 shrink-0">${repo.last_commit.relative_date}</span>
            </div>
          ` : '<div class="pt-1 border-t border-dark-800 text-[11px] text-slate-500 italic">暂无提交记录</div>'}
        </div>

        <!-- SSH Key & Intercept Toggle Row -->
        <div class="flex items-center justify-between pt-1">
          <div class="flex items-center space-x-1.5 cursor-pointer" onclick="showBindKeyModal('${repo.id}', '${repo.name}', '${repo.bound_ssh_key || ''}')" title="点击更换专属密钥">
            ${boundKey}
          </div>

          <div class="flex items-center space-x-2">
            <button onclick="toggleRepoIntercept('${repo.id}', ${!repo.is_intercept_enabled})" class="px-2 py-1 rounded-lg text-[11px] font-medium border ${interceptBtnClass} flex items-center space-x-1" title="开启/关闭此仓库提交拦截">
              <i data-lucide="shield" class="w-3 h-3"></i>
              <span>${repo.is_intercept_enabled ? '拦截已就绪' : '拦截已旁路'}</span>
            </button>
          </div>
        </div>

        <!-- Action Toolbar Buttons -->
        <div class="pt-2 border-t border-dark-700/60 flex items-center justify-between">
          <div class="flex items-center space-x-1">
            <button onclick="repoGitAction('${repo.id}', 'fetch')" class="px-2.5 py-1 bg-dark-700 hover:bg-dark-600 text-slate-300 hover:text-white rounded-lg text-xs font-medium transition" title="Fetch 远程分支">
              Fetch
            </button>
            <button onclick="repoGitAction('${repo.id}', 'pull')" class="px-2.5 py-1 bg-dark-700 hover:bg-dark-600 text-slate-300 hover:text-white rounded-lg text-xs font-medium transition" title="Pull 拉取远程最新代码">
              Pull
            </button>
            <button onclick="repoGitAction('${repo.id}', 'push')" class="px-2.5 py-1 bg-dark-700 hover:bg-dark-600 text-slate-300 hover:text-white rounded-lg text-xs font-medium transition" title="Push 推送到远程">
              Push
            </button>
          </div>

          <div class="flex items-center space-x-1">
            <button onclick="openRepo('${repo.id}', 'explorer')" class="p-1.5 bg-dark-800 hover:bg-dark-700 text-slate-400 hover:text-white rounded-lg text-xs transition" title="在文件管理器中打开">
              <i data-lucide="folder" class="w-3.5 h-3.5"></i>
            </button>
            <button onclick="openRepo('${repo.id}', 'terminal')" class="p-1.5 bg-dark-800 hover:bg-dark-700 text-slate-400 hover:text-white rounded-lg text-xs transition" title="在此打开命令行终端">
              <i data-lucide="terminal" class="w-3.5 h-3.5"></i>
            </button>
            <button onclick="openRepo('${repo.id}', 'vscode')" class="p-1.5 bg-dark-800 hover:bg-dark-700 text-slate-400 hover:text-white rounded-lg text-xs transition" title="用 VS Code 打开">
              <i data-lucide="code" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        </div>

      </div>
    `;
  }).join("");

  lucide.createIcons();
}

function filterRepos() {
  const query = (document.getElementById("repo-search-input").value || "").toLowerCase().trim();
  const filterType = document.getElementById("repo-status-filter").value;

  const filtered = state.repos.filter(r => {
    const matchesSearch = r.name.toLowerCase().includes(query) ||
                          r.path.toLowerCase().includes(query) ||
                          r.branch.toLowerCase().includes(query) ||
                          (r.bound_ssh_key && r.bound_ssh_key.toLowerCase().includes(query));

    if (!matchesSearch) return false;

    if (filterType === "dirty") return !r.is_clean;
    if (filterType === "ahead_behind") return r.ahead > 0 || r.behind > 0;
    if (filterType === "intercept_on") return r.is_intercept_enabled;
    return true;
  });

  renderRepos(filtered);
}

// --- Repo Actions ---

async function repoGitAction(repoId, action) {
  showWebToast("正在执行...", `正在对仓库执行 git ${action}`, "info");
  try {
    const res = await fetch(`/api/repos/${repoId}/${action}`, { method: "POST" });
    const data = await res.json();
    if (data.result && data.result.success) {
      showWebToast("执行成功", `git ${action} 执行完毕`, "success");
    } else {
      showWebToast("执行返回", data.result ? data.result.output : "已完成", "warning");
    }
    // Update local repo status
    if (data.repo) {
      const idx = state.repos.findIndex(r => r.id === repoId);
      if (idx !== -1) state.repos[idx] = data.repo;
      updateOverviewStats();
      renderRepos();
    }
  } catch (e) {
    showWebToast("操作失败", e.message, "danger");
  }
}

async function openRepo(repoId, target) {
  try {
    await fetch(`/api/repos/${repoId}/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target })
    });
  } catch (e) {
    console.error("Open repo failed:", e);
  }
}

async function toggleRepoIntercept(repoId, enabled) {
  try {
    const res = await fetch(`/api/repos/${repoId}/intercept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled })
    });
    const data = await res.json();
    if (data.repo) {
      const idx = state.repos.findIndex(r => r.id === repoId);
      if (idx !== -1) state.repos[idx] = data.repo;
      renderRepos();
      showWebToast("设置已保存", `该仓库拦截状态已更新为: ${enabled ? '开启' : '旁路'}`, "success");
    }
  } catch (e) {
    showWebToast("设置失败", e.message, "danger");
  }
}

// --- Global Intercept Hook Switch ---

async function toggleGlobalHook() {
  const target = !state.globalHooksEnabled;
  try {
    const res = await fetch("/api/hooks/global", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: target })
    });
    const data = await res.json();
    state.globalHooksEnabled = !!data.global_hooks_enabled;
    updateOverviewStats();
    renderRepos();
    showWebToast(
      state.globalHooksEnabled ? "全局拦截已开启" : "全局拦截已关闭",
      state.globalHooksEnabled 
        ? "现在全系统任何终端/IDE执行 git commit 都会触发安全拦截弹窗！" 
        : "已解除全局 hooksPath 设置，已退回单仓库模式。",
      state.globalHooksEnabled ? "success" : "info"
    );
  } catch (e) {
    showWebToast("操作失败", e.message, "danger");
  }
}


// --- Rendering Keys ---

function renderKeys() {
  const container = document.getElementById("keys-container");
  const emptyState = document.getElementById("keys-empty-state");
  document.getElementById("badge-key-count").textContent = state.keys.length;

  if (state.keys.length === 0) {
    container.innerHTML = "";
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  container.innerHTML = state.keys.map(key => {
    return `
      <div class="glass-card rounded-2xl p-4 flex flex-col justify-between space-y-3">
        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="p-1.5 rounded-lg bg-amber-500/10 text-amber-400">
                <i data-lucide="key" class="w-4 h-4"></i>
              </span>
              <h3 class="font-bold text-sm text-white">${key.name}</h3>
            </div>
            <span class="px-2 py-0.5 rounded-md bg-sky-500/10 text-sky-400 border border-sky-500/20 text-xs font-semibold">${key.type} ${key.size ? `(${key.size}b)` : ''}</span>
          </div>

          <p class="text-xs text-slate-400 font-mono break-all bg-dark-900/60 p-2 rounded-xl border border-dark-800" title="密钥指纹">
            ${key.fingerprint || '无指纹信息'}
          </p>

          ${key.comment ? `<p class="text-[11px] text-slate-500">注释: <span class="text-slate-300">${key.comment}</span></p>` : ''}
        </div>

        <!-- Action Row -->
        <div class="pt-2 border-t border-dark-700/60 flex items-center justify-between text-xs">
          <button onclick="copyPublicKey('${key.public_key}')" class="px-3 py-1.5 bg-dark-700 hover:bg-dark-600 text-slate-200 rounded-lg flex items-center space-x-1.5 transition">
            <i data-lucide="copy" class="w-3.5 h-3.5"></i>
            <span>复制公钥</span>
          </button>

          <div class="flex items-center space-x-1.5">
            <button onclick="testKeyConnection('github', '${key.private_path}')" class="px-2 py-1 bg-dark-800 hover:bg-dark-700 text-slate-300 hover:text-white rounded-lg text-[11px] border border-dark-700 transition" title="测试向 git@github.com 发起 SSH 握手">
              握手 GitHub
            </button>
            <button onclick="testKeyConnection('gitlab', '${key.private_path}')" class="px-2 py-1 bg-dark-800 hover:bg-dark-700 text-slate-300 hover:text-white rounded-lg text-[11px] border border-dark-700 transition" title="测试向 git@gitlab.com 发起 SSH 握手">
              握手 GitLab
            </button>
            <button onclick="testKeyConnection('gitee', '${key.private_path}')" class="px-2 py-1 bg-dark-800 hover:bg-dark-700 text-slate-300 hover:text-white rounded-lg text-[11px] border border-dark-700 transition" title="测试向 git@gitee.com 发起 SSH 握手">
              握手 Gitee
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");

  lucide.createIcons();
}

function updateGitUserDisplay() {
  const nameEl = document.getElementById("git-user-name-display");
  const emailEl = document.getElementById("git-user-email-display");
  if (nameEl) nameEl.textContent = state.gitUser.global_user_name || "未配置全局用户名";
  if (emailEl) emailEl.textContent = state.gitUser.global_user_email || "未配置全局邮箱";
}

function copyPublicKey(pubKey) {
  if (!pubKey) {
    showWebToast("错误", "此密钥未找到对应的公钥内容", "warning");
    return;
  }
  navigator.clipboard.writeText(pubKey).then(() => {
    showWebToast("已复制到剪贴板", "你可以直接粘贴到 GitHub / GitLab 的 SSH Keys 页面中", "success");
  }).catch(() => {
    showWebToast("复制失败", "浏览器剪贴板权限受限", "danger");
  });
}

// --- Git Identities Management ---

async function fetchIdentities() {
  try {
    const res = await fetch("/api/git/identities");
    const data = await res.json();
    state.identities = data.identities || [];
    state.sshHosts = data.ssh_hosts || [];
    if (data.global_user) {
      state.gitUser = {
        global_user_name: data.global_user.name,
        global_user_email: data.global_user.email
      };
      updateGitUserDisplay();
    }
    renderIdentities();
    renderSshHosts();
  } catch (e) {
    console.error("Fetch identities failed:", e);
  }
}

function renderIdentities() {
  const container = document.getElementById("identities-container");
  if (!container) return;

  if (state.identities.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-6 text-center text-slate-400 text-xs">
        未检测到 Git 作者身份，请点击右上角“自定义新身份”添加
      </div>
    `;
    return;
  }

  container.innerHTML = state.identities.map(idn => {
    const initial = (idn.name || idn.email || "?").charAt(0).toUpperCase();
    const isGlobal = idn.is_global;

    let badgeHtml = "";
    if (isGlobal) {
      badgeHtml += `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">全局默认</span>`;
    }
    if (idn.local_repos && idn.local_repos.length > 0) {
      badgeHtml += `<span class="px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-500/20 text-sky-300 border border-sky-500/30" title="在这些仓库本地单独配置: ${idn.local_repos.join(', ')}">单仓专属 (${idn.local_repos.length})</span>`;
    }
    if (idn.author_repos && idn.author_repos.length > 0) {
      badgeHtml += `<span class="px-2 py-0.5 rounded-full text-[10px] font-medium bg-indigo-500/20 text-indigo-300 border border-indigo-500/30" title="在这些仓库包含历史提交: ${idn.author_repos.join(', ')}">提交历史 (${idn.commit_count || idn.author_repos.length})</span>`;
    }

    const safeName = (idn.name || "").replace(/'/g, "\\'");
    const safeEmail = (idn.email || "").replace(/'/g, "\\'");

    return `
      <div class="glass-card rounded-2xl p-4 flex flex-col justify-between space-y-3 border ${isGlobal ? 'border-sky-500/40 bg-sky-500/5' : 'border-dark-700/80'}">
        <div class="space-y-2">
          <div class="flex items-start justify-between gap-2">
            <div class="flex items-center space-x-2.5 min-w-0">
              <div class="w-9 h-9 rounded-xl ${isGlobal ? 'bg-gradient-to-tr from-sky-500 to-indigo-600 text-white' : 'bg-dark-750 text-slate-300'} flex items-center justify-center font-bold text-sm shrink-0 shadow-sm">
                ${initial}
              </div>
              <div class="min-w-0">
                <h4 class="font-bold text-xs text-white truncate" title="${idn.name || '未命名'}">${idn.name || '未命名'}</h4>
                <p class="text-[11px] text-slate-400 font-mono truncate" title="${idn.email || ''}">${idn.email || '无邮箱'}</p>
              </div>
            </div>
            <div class="flex flex-wrap gap-1 justify-end shrink-0">
              ${badgeHtml}
            </div>
          </div>

          <div class="text-[11px] text-slate-400 space-y-0.5 bg-dark-900/60 p-2 rounded-xl border border-dark-800">
            ${idn.local_repos && idn.local_repos.length > 0 ? `<div class="truncate"><strong>仓库专属:</strong> <span class="text-slate-300">${idn.local_repos.join(', ')}</span></div>` : ''}
            ${idn.author_repos && idn.author_repos.length > 0 ? `<div class="truncate"><strong>历史提交仓库:</strong> <span class="text-slate-300">${idn.author_repos.join(', ')}</span></div>` : ''}
            ${(!idn.local_repos || idn.local_repos.length === 0) && (!idn.author_repos || idn.author_repos.length === 0) ? `<div class="text-slate-500">全局默认作者，适用于所有通用仓库</div>` : ''}
          </div>
        </div>

        <div class="pt-2 border-t border-dark-700/60 flex items-center justify-between text-xs gap-1">
          <div class="flex items-center space-x-1">
            ${!isGlobal ? `
              <button onclick="applyIdentityGlobal('${safeName}', '${safeEmail}')" class="px-2 py-1 bg-sky-600/30 hover:bg-sky-600/50 text-sky-300 border border-sky-500/30 rounded-lg text-[11px] font-medium transition" title="设为系统全局默认提交者">
                设为全局
              </button>
            ` : `
              <span class="px-2 py-1 text-[11px] font-semibold text-emerald-400 flex items-center space-x-1">
                <i data-lucide="check" class="w-3 h-3"></i>
                <span>当前全局</span>
              </span>
            `}
            <button onclick="openApplyIdentityModal('${safeName}', '${safeEmail}')" class="px-2 py-1 bg-dark-750 hover:bg-dark-700 text-slate-300 hover:text-white border border-dark-650 rounded-lg text-[11px] transition" title="将此身份应用到选定仓库">
              应用到仓库...
            </button>
          </div>
          <button onclick="copyIdentityConfig('${safeName}', '${safeEmail}')" class="px-2 py-1 bg-dark-800 hover:bg-dark-700 text-slate-400 hover:text-slate-200 rounded-lg text-[11px] border border-dark-700 transition" title="复制 Git 终端配置命令">
            <i data-lucide="terminal" class="w-3 h-3"></i>
          </button>
        </div>
      </div>
    `;
  }).join("");

  lucide.createIcons();
}

function renderSshHosts() {
  const section = document.getElementById("ssh-hosts-section");
  const container = document.getElementById("ssh-hosts-container");
  if (!section || !container) return;

  if (!state.sshHosts || state.sshHosts.length === 0) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  container.innerHTML = state.sshHosts.map(h => `
    <div class="p-3 bg-dark-900 rounded-xl border border-dark-750 space-y-1 text-xs">
      <div class="flex items-center justify-between">
        <span class="font-bold text-sky-400 font-mono">${h.host}</span>
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-dark-800 text-slate-400 font-mono">${h.user || 'git'}</span>
      </div>
      <div class="text-[11px] text-slate-400 truncate">主机: <span class="text-slate-200 font-mono">${h.hostname || h.host}</span></div>
      ${h.identity_file ? `<div class="text-[11px] text-slate-400 truncate">私钥: <span class="text-amber-300 font-mono">${h.identity_file}</span></div>` : ''}
    </div>
  `).join("");
  lucide.createIcons();
}

function openApplyIdentityModal(name, email) {
  state.activeIdentityForApply = { name, email };
  const avatar = document.getElementById("apply-identity-avatar");
  const nameEl = document.getElementById("apply-identity-name");
  const emailEl = document.getElementById("apply-identity-email");
  const repoSelect = document.getElementById("apply-target-repo-select");

  if (avatar) avatar.textContent = (name || email || "?").charAt(0).toUpperCase();
  if (nameEl) nameEl.textContent = name || "未指定用户名";
  if (emailEl) emailEl.textContent = email || "未指定邮箱";

  if (repoSelect) {
    repoSelect.innerHTML = state.repos.map(r => `
      <option value="${r.path}">${r.name} (${r.path})</option>
    `).join("");
  }

  // Reset radio to global
  const globalRadio = document.querySelector("input[name='apply_scope'][value='global']");
  if (globalRadio) globalRadio.checked = true;
  toggleApplyScope("global");

  openModal("modal-apply-identity-repo");
}

function toggleApplyScope(val) {
  const container = document.getElementById("apply-repo-select-container");
  if (!container) return;
  if (val === "local") {
    container.classList.remove("hidden");
  } else {
    container.classList.add("hidden");
  }
}

async function confirmApplyIdentity() {
  if (!state.activeIdentityForApply) return;
  const { name, email } = state.activeIdentityForApply;
  const scope = document.querySelector("input[name='apply_scope']:checked")?.value || "global";

  try {
    if (scope === "global") {
      const res = await fetch("/api/git/identities/apply-global", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email })
      });
      if (res.ok) {
        showWebToast("已设为全局作者", `全局 user.name=${name}, user.email=${email}`, "success");
      }
    } else {
      const repoPath = document.getElementById("apply-target-repo-select").value;
      const res = await fetch("/api/git/identities/apply-repo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_path: repoPath, name, email })
      });
      if (res.ok) {
        showWebToast("已应用到仓库", `仓库 ${repoPath.split(/[\\/]/).pop()} 本地作者已设置为 ${name}`, "success");
      }
    }
    closeModal("modal-apply-identity-repo");
    await Promise.all([fetchRepos(), fetchIdentities()]);
  } catch (e) {
    showWebToast("应用失败", e.message, "danger");
  }
}

async function applyIdentityGlobal(name, email) {
  try {
    const res = await fetch("/api/git/identities/apply-global", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email })
    });
    if (res.ok) {
      showWebToast("全局身份已切换", `默认作者已变更为: ${name} <${email}>`, "success");
      await Promise.all([fetchRepos(), fetchIdentities()]);
    }
  } catch (e) {
    showWebToast("切换失败", e.message, "danger");
  }
}

function copyIdentityConfig(name, email) {
  const cmd = `git config user.name "${name}" && git config user.email "${email}"`;
  navigator.clipboard.writeText(cmd).then(() => {
    showWebToast("配置命令已复制", cmd, "info");
  });
}

// --- Scan Paths & Depth Modal Logic ---

async function showScanPathsModal() {
  try {
    const res = await fetch("/api/scan/paths");
    const data = await res.json();
    state.scanPaths = data.monitored_paths || [];
    state.scanDepth = data.scan_depth || 5;

    const slider = document.getElementById("scan-depth-slider");
    const valEl = document.getElementById("scan-depth-val");
    if (slider) slider.value = state.scanDepth;
    if (valEl) valEl.textContent = state.scanDepth;

    renderScanPathsList();
    openModal("modal-scan-paths");
  } catch (e) {
    showWebToast("加载扫描路径失败", e.message, "danger");
  }
}

function renderScanPathsList() {
  const listEl = document.getElementById("scan-paths-list");
  if (!listEl) return;

  if (state.scanPaths.length === 0) {
    listEl.innerHTML = `<div class="p-3 text-slate-500 text-center bg-dark-900 rounded-xl">未设置任何监控路径</div>`;
    return;
  }

  listEl.innerHTML = state.scanPaths.map((p, idx) => `
    <div class="flex items-center justify-between p-2 rounded-xl bg-dark-900 border border-dark-750 text-xs">
      <span class="font-mono text-slate-200 truncate flex-1 mr-2" title="${p}">${p}</span>
      <button onclick="removeScanPath(${idx})" class="p-1 text-slate-400 hover:text-rose-400 transition" title="移除此路径">
        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
      </button>
    </div>
  `).join("");
  lucide.createIcons();
}

function addNewScanPath() {
  const input = document.getElementById("new-scan-path");
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;
  if (!state.scanPaths.includes(val)) {
    state.scanPaths.push(val);
    renderScanPathsList();
    input.value = "";
  } else {
    showWebToast("提示", "该路径已在监控列表中", "warning");
  }
}

function removeScanPath(idx) {
  state.scanPaths.splice(idx, 1);
  renderScanPathsList();
}

async function saveScanPathsSettings() {
  const slider = document.getElementById("scan-depth-slider");
  const depth = slider ? parseInt(slider.value) : 5;

  try {
    const res = await fetch("/api/scan/paths", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        monitored_paths: state.scanPaths,
        scan_depth: depth
      })
    });
    const data = await res.json();
    if (res.ok) {
      state.repos = data.repos || [];
      renderRepos();
      updateOverviewStats();
      closeModal("modal-scan-paths");
      showWebToast("扫描设置已保存", `共扫描并发现 ${data.total_repos} 个 Git 仓库`, "success");
      fetchIdentities();
    }
  } catch (e) {
    showWebToast("保存失败", e.message, "danger");
  }
}

async function triggerFullRescan() {
  showWebToast("正在全盘深度扫描...", "正在检索所有磁盘与监控目录下的 Git 仓库", "info");
  await saveScanPathsSettings();
}

async function testKeyConnection(host, privateKeyPath) {
  openModal('modal-test-conn');
  const content = document.getElementById("test-conn-content");
  content.innerHTML = `
    <div class="flex items-center space-x-3 py-6 justify-center">
      <i data-lucide="loader-2" class="w-6 h-6 text-sky-400 animate-spin"></i>
      <span class="text-sm text-slate-300">正在与 ${host} 建立 SSH 握手并验证身份...</span>
    </div>
  `;
  lucide.createIcons();

  try {
    const res = await fetch("/api/keys/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, key_path: privateKeyPath })
    });
    const data = await res.json();

    const isSuccess = data.success;
    content.innerHTML = `
      <div class="p-4 rounded-xl ${isSuccess ? 'bg-emerald-500/10 border border-emerald-500/30' : 'bg-rose-500/10 border border-rose-500/30'} space-y-2">
        <div class="flex items-center space-x-2">
          <i data-lucide="${isSuccess ? 'check-circle' : 'alert-circle'}" class="w-5 h-5 ${isSuccess ? 'text-emerald-400' : 'text-rose-400'}"></i>
          <h4 class="font-bold text-sm ${isSuccess ? 'text-emerald-400' : 'text-rose-400'}">${isSuccess ? '身份认证成功' : '认证未通过'}</h4>
        </div>
        <p class="text-xs text-slate-200">${data.message}</p>
        ${data.username ? `<p class="text-xs text-sky-300 font-semibold">认证账号: ${data.username}</p>` : ''}
      </div>
      <div class="space-y-1">
        <label class="text-[11px] text-slate-400 font-semibold uppercase">原始输出终端日志 (Raw Output):</label>
        <pre class="bg-dark-900 p-3 rounded-xl text-[11px] text-slate-300 font-mono overflow-x-auto max-h-48 whitespace-pre-wrap">${data.raw_output || '无输出'}</pre>
      </div>
    `;
    lucide.createIcons();
  } catch (e) {
    content.innerHTML = `<p class="text-xs text-rose-400">请求错误: ${e.message}</p>`;
  }
}

// --- Rendering Sentinel Security Rules ---

function renderSettings() {
  const sensitiveContainer = document.getElementById("sensitive-files-tags");
  const patternsContainer = document.getElementById("secret-patterns-list");
  const rules = state.settings.security_rules || {};

  if (sensitiveContainer && rules.sensitive_files) {
    sensitiveContainer.innerHTML = rules.sensitive_files.map(item => `
      <span class="px-2.5 py-1 rounded-lg bg-rose-500/10 text-rose-300 border border-rose-500/20 text-xs font-mono">
        ${item}
      </span>
    `).join("");
  }

  if (patternsContainer && rules.secret_patterns) {
    patternsContainer.innerHTML = rules.secret_patterns.map(p => `
      <div class="bg-dark-900/60 p-2.5 rounded-xl border border-dark-800 flex items-center justify-between">
        <div>
          <span class="font-semibold text-slate-200">${p.name}</span>
          <span class="text-slate-500 block font-mono text-[10px] truncate max-w-[260px]">${p.regex}</span>
        </div>
        <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase ${p.level === 'critical' ? 'bg-rose-500/20 text-rose-400' : 'bg-amber-500/20 text-amber-400'}">${p.level}</span>
      </div>
    `).join("");
  }
}

// --- Notifications ---

function renderNotifications() {
  const container = document.getElementById("notifications-list");
  if (!container) return;

  if (state.notifications.length === 0) {
    container.innerHTML = `<div class="p-8 text-center text-xs text-slate-500">暂无任何通知记录</div>`;
    return;
  }

  container.innerHTML = state.notifications.map(n => {
    let icon = "bell";
    let iconColor = "text-sky-400";
    if (n.type === "commit") { icon = "git-commit"; iconColor = "text-emerald-400"; }
    else if (n.type === "remote_update") { icon = "cloud-download"; iconColor = "text-amber-400"; }
    else if (n.type === "alert") { icon = "shield-alert"; iconColor = "text-rose-400"; }

    return `
      <div class="p-4 flex items-start space-x-3 hover:bg-dark-800/40 transition">
        <div class="p-2 rounded-xl bg-dark-900 border border-dark-700 shrink-0 ${iconColor}">
          <i data-lucide="${icon}" class="w-4 h-4"></i>
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center justify-between">
            <h4 class="text-sm font-semibold text-white truncate">${n.title}</h4>
            <span class="text-[11px] text-slate-500 font-mono">${n.time_str}</span>
          </div>
          <p class="text-xs text-slate-300 mt-0.5 break-words">${n.message}</p>
          ${n.repo_path ? `<p class="text-[10px] text-slate-500 font-mono mt-1">${n.repo_path}</p>` : ''}
        </div>
      </div>
    `;
  }).join("");

  lucide.createIcons();
}

async function testToastNotification() {
  try {
    if ("Notification" in window) {
      if (Notification.permission === "default") {
        await Notification.requestPermission();
      }
      if (Notification.permission === "granted") {
        try {
          new Notification("🔔 GitSentinel 系统桌面提醒", {
            body: "Windows 原生系统通知测试成功！提交与更新提醒已就绪。",
            icon: "/assets/icon.png"
          });
        } catch (e) {
          console.warn("Direct Notification error:", e);
        }
      }
    }
    await fetch("/api/notifications/test-toast", { method: "POST" });
    showWebToast("已发送", "已向操作系统发送原生桌面通知", "info");
  } catch (e) {
    showWebToast("发送失败", e.message, "danger");
  }
}

// --- Modals Logic ---

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
  lucide.createIcons();
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
}

function showGenerateKeyModal() {
  document.getElementById("gen-key-name").value = "";
  document.getElementById("gen-key-comment").value = state.gitUser.global_user_email || "";
  document.getElementById("gen-key-passphrase").value = "";
  openModal("modal-gen-key");
}

async function submitGenerateKey(e) {
  e.preventDefault();
  const name = document.getElementById("gen-key-name").value.trim();
  const key_type = document.getElementById("gen-key-type").value;
  const comment = document.getElementById("gen-key-comment").value.trim();
  const passphrase = document.getElementById("gen-key-passphrase").value;

  const btn = document.getElementById("btn-submit-gen-key");
  btn.disabled = true;
  btn.textContent = "生成中...";

  try {
    const res = await fetch("/api/keys/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, key_type, comment, passphrase })
    });
    const data = await res.json();
    if (res.ok) {
      closeModal("modal-gen-key");
      showWebToast("密钥生成成功", `密钥对 ${name} 已保存至 ~/.ssh/`, "success");
      await fetchKeys();
    } else {
      showWebToast("生成失败", data.detail || "发生错误", "danger");
    }
  } catch (err) {
    showWebToast("请求异常", err.message, "danger");
  } finally {
    btn.disabled = false;
    btn.textContent = "生成密钥";
  }
}

function showBindKeyModal(repoId, repoName, currentKey) {
  document.getElementById("bind-repo-id").value = repoId;
  document.getElementById("bind-repo-name").value = repoName;

  const select = document.getElementById("bind-key-select");
  let options = `<option value="">-- 解除绑定 (恢复系统默认 SSH) --</option>`;
  
  state.keys.forEach(k => {
    if (k.private_path) {
      const selected = currentKey && (currentKey === k.private_path || currentKey.includes(k.name));
      options += `<option value="${k.private_path}" ${selected ? 'selected' : ''}>${k.name} (${k.type}) - ${k.private_path}</option>`;
    }
  });

  select.innerHTML = options;
  openModal("modal-bind-key");
}

async function submitBindKey() {
  const repoId = document.getElementById("bind-repo-id").value;
  const keyPath = document.getElementById("bind-key-select").value;

  try {
    const res = await fetch(`/api/repos/${repoId}/bind-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key_path: keyPath })
    });
    const data = await res.json();
    if (data.repo) {
      const idx = state.repos.findIndex(r => r.id === repoId);
      if (idx !== -1) state.repos[idx] = data.repo;
      renderRepos();
      closeModal("modal-bind-key");
      showWebToast("绑定已更新", keyPath ? `已为仓库指定专属私钥: ${keyPath.split('/').pop()}` : "已恢复默认 SSH 配置", "success");
    }
  } catch (e) {
    showWebToast("绑定失败", e.message, "danger");
  }
}

function showEditGitUserModal() {
  document.getElementById("edit-user-name").value = state.gitUser.global_user_name || "";
  document.getElementById("edit-user-email").value = state.gitUser.global_user_email || "";
  openModal("modal-edit-user");
}

async function submitEditGitUser(e) {
  e.preventDefault();
  const user_name = document.getElementById("edit-user-name").value.trim();
  const user_email = document.getElementById("edit-user-email").value.trim();

  try {
    const res = await fetch("/api/git/user", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_name, user_email, is_global: true })
    });
    if (res.ok) {
      closeModal("modal-edit-user");
      await fetchKeys();
      showWebToast("身份更新成功", `全局作者已变更为: ${user_name} <${user_email}>`, "success");
    }
  } catch (err) {
    showWebToast("更新失败", err.message, "danger");
  }
}

function showAddManualRepoModal() {
  document.getElementById("manual-repo-path").value = "";
  openModal("modal-add-repo");
}

async function submitAddManualRepo(e) {
  e.preventDefault();
  const path = document.getElementById("manual-repo-path").value.trim();

  try {
    const res = await fetch("/api/repos/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      closeModal("modal-add-repo");
      await fetchRepos();
      showWebToast("导入成功", `仓库 ${data.repo.name} 已纳入监控`, "success");
    } else {
      showWebToast("导入失败", data.detail || "路径无效", "danger");
    }
  } catch (err) {
    showWebToast("导入异常", err.message, "danger");
  }
}

// --- Web In-Page Floating Toast ---
function showWebToast(title, message, type = "info") {
  const container = document.getElementById("web-toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  let bg = "bg-dark-850 border-dark-700 text-slate-200";
  let icon = "info";
  let iconColor = "text-sky-400";

  if (type === "success") {
    bg = "bg-emerald-950/90 border-emerald-600/40 text-emerald-100";
    icon = "check-circle";
    iconColor = "text-emerald-400";
  } else if (type === "danger") {
    bg = "bg-rose-950/90 border-rose-600/40 text-rose-100";
    icon = "alert-circle";
    iconColor = "text-rose-400";
  } else if (type === "warning") {
    bg = "bg-amber-950/90 border-amber-600/40 text-amber-100";
    icon = "alert-triangle";
    iconColor = "text-amber-400";
  }

  toast.className = `p-3.5 rounded-xl border shadow-xl flex items-start space-x-3 pointer-events-auto transform transition duration-300 translate-y-2 opacity-0 max-w-sm ${bg}`;
  toast.innerHTML = `
    <i data-lucide="${icon}" class="w-5 h-5 ${iconColor} shrink-0 mt-0.5"></i>
    <div class="flex-1 min-w-0">
      <h5 class="font-bold text-xs">${title}</h5>
      <p class="text-[11px] opacity-80 mt-0.5 break-words">${message}</p>
    </div>
  `;

  container.appendChild(toast);
  lucide.createIcons();

  // Animate in
  setTimeout(() => {
    toast.classList.remove("translate-y-2", "opacity-0");
  }, 10);

  // Auto remove
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-x-4");
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}
