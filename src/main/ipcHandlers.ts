import { ipcMain, dialog, BrowserWindow } from 'electron'
import { PythonBridge } from './pythonBridge'
import * as fs from 'fs'
import * as path from 'path'
import * as http from 'http'

let _backendUrl = ''

export function registerIpcHandlers(backendUrl: string): void {
  _backendUrl = backendUrl

  // Provide backend URL to renderer
  ipcMain.handle('get-python-url', () => {
    return backendUrl
  })

  // Native file selection dialog for PDFs
  ipcMain.handle('select-pdf-file', async () => {
    const window = BrowserWindow.getFocusedWindow()
    if (!window) return null

    const result = await dialog.showOpenDialog(window, {
      title: '选择PDF合同文件',
      filters: [{ name: 'PDF文件', extensions: ['pdf'] }],
      properties: ['openFile'],
    })

    if (result.canceled || result.filePaths.length === 0) {
      return null
    }

    return result.filePaths[0]
  })

  // Save Excel file dialog
  ipcMain.handle('save-excel-file', async (_event, docId: string, filename: string) => {
    const window = BrowserWindow.getFocusedWindow()
    if (!window) return { success: false, error: 'No window' }

    const result = await dialog.showSaveDialog(window, {
      title: '导出 Excel',
      defaultPath: filename,
      filters: [{ name: 'Excel文件', extensions: ['xlsx'] }],
    })

    if (result.canceled || !result.filePath) {
      return { success: false, canceled: true }
    }

    // Download from backend
    try {
      const data = await downloadFile(docId)
      fs.writeFileSync(result.filePath, data)
      return { success: true, path: result.filePath }
    } catch (e: any) {
      return { success: false, error: e.message }
    }
  })

  // App version
  ipcMain.handle('get-app-version', () => {
    return require('../../package.json').version
  })
}

function downloadFile(docId: string): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const url = `${_backendUrl}/api/export/${docId}`
    http.get(url, (res) => {
      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`))
        return
      }
      const chunks: Buffer[] = []
      res.on('data', (chunk: Buffer) => chunks.push(chunk))
      res.on('end', () => resolve(Buffer.concat(chunks)))
      res.on('error', reject)
    }).on('error', reject)
  })
}
