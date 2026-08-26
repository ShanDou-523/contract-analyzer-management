/// <reference types="vite/client" />

interface Window {
  electronAPI?: {
    getPythonBaseUrl(): Promise<string>
    selectPdfFile(): Promise<string | null>
    saveExcelFile(docId: string, filename: string): Promise<{
      success: boolean
      canceled?: boolean
      path?: string
      error?: string
    }>
    getAppVersion(): Promise<string>
  }
}
