import { app, BrowserWindow, shell } from 'electron'
import { join } from 'path'
import { PythonBridge } from './pythonBridge'
import { registerIpcHandlers } from './ipcHandlers'

let mainWindow: BrowserWindow | null = null
let pythonBridge: PythonBridge | null = null

function createWindow(): void {
  const windowIcon = app.isPackaged
    ? join(process.resourcesPath, 'assets', 'contract-analysis.ico')
    : join(__dirname, '../../assets/contract-analysis.ico')

  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: '合同分析系统',
    icon: windowIcon,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // Handle external links
  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // Load renderer
  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  // Start Python backend
  pythonBridge = new PythonBridge()
  const backendUrl = await pythonBridge.start()

  // Register IPC handlers
  registerIpcHandlers(backendUrl)

  // Create window
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (pythonBridge) {
    pythonBridge.stop()
  }
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  if (pythonBridge) {
    pythonBridge.stop()
  }
})
