const { app, BrowserWindow, Tray, Menu, nativeImage, shell, Notification } = require('electron');
const path = require('path');
const http = require('http');
const fs = require('fs');
const { spawn } = require('child_process');

// Set Application User Model ID for native Windows Action Center notifications
if (process.platform === 'win32') {
  app.setAppUserModelId(app.isPackaged ? 'com.gitsentinel.app' : process.execPath);
}

let mainWindow = null;
let tray = null;
let pythonProcess = null;
const BACKEND_PORT = 28888;
const APP_URL = `http://127.0.0.1:${BACKEND_PORT}`;

// Prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    } else {
      createMainWindow();
    }
  });
}

function findPythonBackend() {
  const isPackaged = app.isPackaged;

  if (isPackaged) {
    const winExe = path.join(process.resourcesPath, 'GitSentinel', 'GitSentinel.exe');
    const macUnixExe = path.join(process.resourcesPath, 'GitSentinel', 'GitSentinel');

    if (process.platform === 'win32' && fs.existsSync(winExe)) {
      return {
        cmd: winExe,
        args: ['server'],
        cwd: path.dirname(winExe)
      };
    }
    if (fs.existsSync(macUnixExe)) {
      return {
        cmd: macUnixExe,
        args: ['server'],
        cwd: path.dirname(macUnixExe)
      };
    }
  }

  // Development mode: run sentinel.py with system python
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
  const scriptPath = path.join(__dirname, 'sentinel.py');
  return {
    cmd: pythonCmd,
    args: [scriptPath, 'server'],
    cwd: path.dirname(scriptPath)
  };
}

function checkBackendAlive(callback) {
  const req = http.get(`${APP_URL}/api/settings`, (res) => {
    callback(res.statusCode === 200);
  });
  req.on('error', () => callback(false));
  req.setTimeout(800, () => {
    req.destroy();
    callback(false);
  });
}

function startBackend() {
  checkBackendAlive((alive) => {
    if (alive) {
      console.log(`[GitSentinel] Backend is already running on port ${BACKEND_PORT}`);
      return;
    }

    const backend = findPythonBackend();
    console.log(`[GitSentinel] Starting backend: ${backend.cmd} ${backend.args.join(' ')} (cwd: ${backend.cwd})`);

    try {
      pythonProcess = spawn(backend.cmd, backend.args, {
        cwd: backend.cwd,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true
      });

      pythonProcess.on('error', (err) => {
        console.error('[GitSentinel] Backend process error:', err);
      });

      pythonProcess.stdout.on('data', (data) => {
        console.log(`[Backend]: ${data.toString().trim()}`);
      });

      pythonProcess.stderr.on('data', (data) => {
        console.error(`[Backend ERR]: ${data.toString().trim()}`);
      });

      pythonProcess.on('close', (code) => {
        console.log(`[GitSentinel] Backend exited with code ${code}`);
      });
    } catch (err) {
      console.error('[GitSentinel] Failed to spawn backend process:', err);
    }
  });
}

function waitForBackend(callback, maxAttempts = 60) {
  let attempts = 0;
  const interval = setInterval(() => {
    attempts++;
    checkBackendAlive((alive) => {
      if (alive) {
        clearInterval(interval);
        callback(true);
      } else if (attempts >= maxAttempts) {
        clearInterval(interval);
        callback(false);
      }
    });
  }, 250);
}

function createMainWindow() {
  const iconPath = process.platform === 'win32'
    ? path.join(__dirname, 'assets', 'icon.ico')
    : path.join(__dirname, 'assets', 'icon.png');

  mainWindow = new BrowserWindow({
    width: 1240,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    title: 'GitSentinel - Git 统一管理与安全提交拦截系统',
    backgroundColor: '#0f172a',
    icon: iconPath,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false
    }
  });

  mainWindow.removeMenu();

  mainWindow.loadURL(APP_URL);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  // Fallback: If ready-to-show hasn't fired within 2.5 seconds, force show
  setTimeout(() => {
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
      mainWindow.show();
      mainWindow.focus();
    }
  }, 2500);

  // Automatically retry loading if backend was still booting
  mainWindow.webContents.on('did-fail-load', () => {
    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.loadURL(APP_URL);
      }
    }, 1000);
  });

  // Handle external links (open in system default browser)
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http:') || url.startsWith('https:')) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'tray_icon.png');
  let trayIcon;
  if (fs.existsSync(iconPath)) {
    trayIcon = nativeImage.createFromPath(iconPath).resize({ width: 18, height: 18 });
  } else {
    trayIcon = nativeImage.createEmpty();
  }

  tray = new Tray(trayIcon);
  tray.setToolTip('GitSentinel 哨兵系统');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '🛡️ 打开 GitSentinel 控制面板',
      click: () => {
        if (mainWindow) {
          if (mainWindow.isMinimized()) mainWindow.restore();
          mainWindow.show();
          mainWindow.focus();
        } else {
          createMainWindow();
        }
      }
    },
    { type: 'separator' },
    {
      label: '⚡ 切换全局提交前拦截',
      click: () => {
        const req = http.request(`${APP_URL}/api/repos`, (res) => {
          let data = '';
          res.on('data', chunk => data += chunk);
          res.on('end', () => {
            try {
              const info = JSON.parse(data);
              const nextState = !info.global_hooks_enabled;
              const postData = JSON.stringify({ enabled: nextState });
              const toggleReq = http.request(`${APP_URL}/api/hooks/global`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'Content-Length': Buffer.byteLength(postData)
                }
              });
              toggleReq.write(postData);
              toggleReq.end();
            } catch (e) {}
          });
        });
        req.end();
      }
    },
    {
      label: '🔄 立即检测远程更新',
      click: () => {
        http.get(`${APP_URL}/api/repos/scan`).end();
      }
    },
    {
      label: '🔔 发送测试通知',
      click: () => {
        if (Notification.isSupported()) {
          const iconPath = process.platform === 'win32'
            ? path.join(__dirname, 'assets', 'icon.ico')
            : path.join(__dirname, 'assets', 'icon.png');
          new Notification({
            title: '🔔 GitSentinel 桌面提醒',
            body: 'Windows 原生系统桌面通知已成功触发！',
            icon: iconPath
          }).show();
        }
      }
    },
    { type: 'separator' },
    {
      label: '❌ 退出 GitSentinel',
      click: () => {
        app.isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    } else {
      createMainWindow();
    }
  });
}

app.whenReady().then(() => {
  startBackend();
  createTray();

  waitForBackend((ready) => {
    createMainWindow();
    if (Notification.isSupported()) {
      const iconPath = process.platform === 'win32'
        ? path.join(__dirname, 'assets', 'icon.ico')
        : path.join(__dirname, 'assets', 'icon.png');
      new Notification({
        title: '🛡️ GitSentinel 哨兵已就绪',
        body: 'Git 统一纳管与安全拦截已启动，点击托盘可随时管理。',
        icon: iconPath
      }).show();
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('before-quit', () => {
  app.isQuitting = true;
  if (pythonProcess) {
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t']);
      } else {
        pythonProcess.kill('SIGTERM');
      }
    } catch (e) {}
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
