import { defineStore } from 'pinia'
import { ref } from 'vue'
import { deleteDocument, getDocument, listDocuments, uploadPdf } from '../api'
import type { DocumentDetail, DocumentListItem } from '../types'

export const useDocumentsStore = defineStore('documents', () => {
  const documents = ref<DocumentListItem[]>([])
  const total = ref(0)
  const currentDocument = ref<DocumentDetail | null>(null)
  const loading = ref(false)
  const processingStep = ref('idle')
  const progressPercent = ref(0)

  async function fetchDocuments(templateId?: string, search?: string) {
    loading.value = true
    try {
      const result = await listDocuments(templateId, search)
      documents.value = result.documents
      total.value = result.total
    } finally {
      loading.value = false
    }
  }

  async function fetchDocument(id: string) {
    loading.value = true
    try {
      currentDocument.value = await getDocument(id)
    } finally {
      loading.value = false
    }
  }

  async function uploadDocument(file: File, templateId?: string): Promise<DocumentListItem | null> {
    processingStep.value = 'uploading'
    progressPercent.value = 10
    try {
      const result = await uploadPdf(file, templateId)
      progressPercent.value = 30
      return {
        id: result.id,
        original_filename: result.original_filename,
        file_size: 0,
        status: result.status,
        page_count: null,
        created_at: null,
        analysis_template_id: result.analysis_template_id || null,
        analysis_template_name: result.analysis_template_name || null,
        analysis_template_version: result.analysis_template_version || null,
      }
    } catch {
      processingStep.value = 'idle'
      progressPercent.value = 0
      return null
    }
  }

  function updateDocumentStatus(id: string, status: string) {
    const item = documents.value.find((document) => document.id === id)
    if (item) item.status = status
  }

  async function removeDocument(id: string) {
    await deleteDocument(id)
    documents.value = documents.value.filter((document) => document.id !== id)
    total.value = Math.max(0, total.value - 1)
  }

  return {
    documents,
    total,
    currentDocument,
    loading,
    processingStep,
    progressPercent,
    fetchDocuments,
    fetchDocument,
    uploadDocument,
    updateDocumentStatus,
    removeDocument,
  }
})
