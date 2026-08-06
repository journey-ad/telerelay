/**
 * Application-level download manager. Download tasks are submitted here and
 * run independently of the UI that started them; components subscribe to task
 * updates (by key) to render progress and pause/resume controls.
 */

import { openTelegramResourceSession, ResourceDownload } from '../api/telegramResource'
import { requestResourceInfo, type ResourceRef } from '../utils/resource'

export type DownloadStatus =
  'queued' | 'requesting' | 'downloading' | 'paused' | 'completed' | 'error'

export interface DownloadTask {
  /** Deterministic key derived from account + resource (dedupe/subscribe). */
  key: string
  accountId: string
  ref: ResourceRef
  filename: string
  status: DownloadStatus
  /** 0-100; -1 when the resource size is unknown. */
  progress: number
  error: string | null
}

export type DownloadListener = (task: DownloadTask) => void

export function downloadTaskKey(accountId: string, ref: ResourceRef): string {
  return `${accountId}:${JSON.stringify(ref)}`
}

const ACTIVE_STATUSES: DownloadStatus[] = ['queued', 'requesting', 'downloading', 'paused']

class DownloadManager {
  private tasks = new Map<string, DownloadTask>()
  private controllers = new Map<string, ResourceDownload>()
  private listeners = new Set<DownloadListener>()

  subscribe(listener: DownloadListener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  getTask(key: string): DownloadTask | undefined {
    return this.tasks.get(key)
  }

  /** Submit a download; reuses an active task for the same resource. */
  start(accountId: string, ref: ResourceRef, filename: string): string {
    const key = downloadTaskKey(accountId, ref)
    const existing = this.tasks.get(key)
    if (existing && ACTIVE_STATUSES.includes(existing.status)) return key
    const task: DownloadTask = {
      key,
      accountId,
      ref,
      filename,
      status: 'queued',
      progress: -1,
      error: null,
    }
    this.tasks.set(key, task)
    this.notify(task)
    void this.run(task)
    return key
  }

  pause(key: string): void {
    const task = this.tasks.get(key)
    const controller = this.controllers.get(key)
    if (!task || task.status !== 'downloading' || !controller) return
    controller.pause()
    this.update(task, { status: 'paused' })
  }

  resume(key: string): void {
    const task = this.tasks.get(key)
    const controller = this.controllers.get(key)
    if (!task || task.status !== 'paused' || !controller) return
    controller.resume()
    this.update(task, { status: 'downloading' })
  }

  private async run(task: DownloadTask): Promise<void> {
    this.update(task, { status: 'requesting' })
    let controller: ResourceDownload | null = null
    try {
      const info = await requestResourceInfo(task.accountId, task.ref)
      const session = await openTelegramResourceSession(task.accountId, info)
      controller = new ResourceDownload(session, task.filename, (transferred, total) => {
        this.update(task, {
          progress: total > 0 ? Math.min(100, (transferred / total) * 100) : -1,
        })
      })
      this.controllers.set(task.key, controller)
      this.update(task, { status: 'downloading' })
      const ok = await controller.run()
      this.update(task, ok ? { status: 'completed', progress: 100 } : { status: 'error' })
    } catch (error) {
      console.error('Telegram file download failed', error)
      this.update(task, {
        status: 'error',
        error: error instanceof Error ? error.message : String(error),
      })
    } finally {
      this.controllers.delete(task.key)
      controller?.close()
      // Keep the terminal state briefly for the UI, then drop it so a later
      // click starts a fresh task.
      window.setTimeout(() => {
        if (this.tasks.get(task.key) === task) this.tasks.delete(task.key)
      }, 10_000)
    }
  }

  private update(task: DownloadTask, patch: Partial<DownloadTask>): void {
    Object.assign(task, patch)
    this.notify(task)
  }

  private notify(task: DownloadTask): void {
    const snapshot = { ...task }
    for (const listener of this.listeners) listener(snapshot)
  }
}

export const downloadManager = new DownloadManager()
