import { spawn, ChildProcess } from 'child_process'
import { existsSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'
import http from 'http'

export class PythonBridge {
  private process: ChildProcess | null = null
  private backendUrl: string = ''
  private port: number = Number(process.env.CONTRACT_ANALYZER_PORT) || 5768
  private stopping: boolean = false

  getUrl(): string {
    return this.backendUrl
  }

  getPort(): number {
    return this.port
  }

  async start(): Promise<string> {
    const isDev = !app.isPackaged

    let command: string
    let args: string[]
    let cwd: string

    if (isDev) {
      cwd = join(__dirname, '../../python_backend')
      const venvPython = process.platform === 'win32'
        ? join(cwd, '.venv', 'Scripts', 'python.exe')
        : join(cwd, '.venv', 'bin', 'python')

      command = process.env.CONTRACT_ANALYZER_PYTHON
        || (existsSync(venvPython) ? venvPython : 'python')
      args = ['main.py']
    } else {
      // Production: run PyInstaller executable (onedir output)
      const resourcesPath = process.resourcesPath
      command = join(resourcesPath, 'python_backend', 'main', 'main.exe')
      args = []
      cwd = join(resourcesPath, 'python_backend', 'main')
    }

    this.port = this.port || 5768
    this.backendUrl = `http://127.0.0.1:${this.port}`

    console.log(`[PythonBridge] Starting Python backend: ${command} ${args.join(' ')}`)
    console.log(`[PythonBridge] Working directory: ${cwd}`)

    this.process = spawn(command, args, {
      cwd,
      env: {
        ...process.env,
        CONTRACT_ANALYZER_PORT: String(this.port),
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    })

    this.process.stdout?.on('data', (data: Buffer) => {
      console.log(`[Python] ${data.toString().trim()}`)
    })

    this.process.stderr?.on('data', (data: Buffer) => {
      console.error(`[Python ERR] ${data.toString().trim()}`)
    })

    this.process.on('exit', (code, signal) => {
      console.log(`[PythonBridge] Python exited with code ${code}, signal ${signal}`)
      if (code !== 0 && code !== null && !this.stopping) {
        console.log('[PythonBridge] Unexpected exit. Restarting in 2s...')
        setTimeout(() => this.start(), 2000)
      }
    })

    this.process.on('error', (err) => {
      console.error(`[PythonBridge] Failed to start Python: ${err.message}`)
    })

    // Wait for backend to be ready
    await this.waitForReady()
    console.log(`[PythonBridge] Backend ready at ${this.backendUrl}`)
    return this.backendUrl
  }

  stop(): void {
    this.stopping = true
    if (this.process) {
      console.log('[PythonBridge] Stopping Python backend...')
      // Send graceful shutdown via HTTP
      if (this.backendUrl) {
        const req = http.request(`${this.backendUrl}/api/health`, { method: 'GET' }, () => {})
        req.on('error', () => {})
        req.end()
      }
      this.process.kill('SIGTERM')
      setTimeout(() => {
        if (this.process && !this.process.killed) {
          this.process.kill('SIGKILL')
        }
      }, 5000)
    }
  }

  private waitForReady(): Promise<void> {
    return new Promise((resolve, reject) => {
      const maxAttempts = 60
      const retryDelayMs = 500
      let attempts = 0
      let settled = false
      let retryTimer: ReturnType<typeof setTimeout> | null = null
      let activeRequest: http.ClientRequest | null = null

      const finish = (error?: Error) => {
        if (settled) return
        settled = true
        if (retryTimer) {
          clearTimeout(retryTimer)
          retryTimer = null
        }
        if (activeRequest) {
          activeRequest.destroy()
          activeRequest = null
        }
        if (error) {
          reject(error)
        } else {
          resolve()
        }
      }

      const scheduleRetry = () => {
        if (settled) return
        if (attempts >= maxAttempts) {
          finish(new Error('Backend health check timed out'))
          return
        }
        if (retryTimer) return
        retryTimer = setTimeout(() => {
          retryTimer = null
          check()
        }, retryDelayMs)
      }

      const check = () => {
        if (settled) return
        if (this.stopping) {
          finish(new Error('Bridge stopped while waiting'))
          return
        }

        attempts++
        let request: http.ClientRequest
        try {
          request = http.get(`${this.backendUrl}/api/health`, (res) => {
            if (settled || activeRequest !== request) {
              res.resume()
              return
            }
            activeRequest = null
            res.resume()
            if (res.statusCode === 200) {
              finish()
            } else {
              scheduleRetry()
            }
          })
        } catch {
          scheduleRetry()
          return
        }

        activeRequest = request
        const handleFailure = () => {
          if (settled || activeRequest !== request) return
          activeRequest = null
          scheduleRetry()
        }

        request.once('error', handleFailure)
        request.setTimeout(2000, () => {
          if (settled || activeRequest !== request) return
          // destroy() may emit an error; clear the active request first so it
          // cannot schedule a second retry.
          activeRequest = null
          request.destroy()
          scheduleRetry()
        })
      }

      check()
    })
  }
}
