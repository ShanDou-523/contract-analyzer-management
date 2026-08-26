import { contextBridge, ipcRenderer } from 'electron'

const electronAPI = {
  getPythonBaseUrl: (): Promise<string> => ipcRenderer.invoke('get-python-url'),
  selectPdfFile: (): Promise<string | null> => ipcRenderer.invoke('select-pdf-file'),
  saveExcelFile: (docId: string, filename: string): Promise<{ success: boolean; canceled?: boolean; path?: string; error?: string }> =>
    ipcRenderer.invoke('save-excel-file', docId, filename),
  getAppVersion: (): Promise<string> => ipcRenderer.invoke('get-app-version'),
}

contextBridge.exposeInMainWorld('electronAPI', electronAPI)

export type ElectronAPI = typeof electronAPI
