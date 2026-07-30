import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  Braces,
  CalendarClock,
  Database,
  Download,
  FileArchive,
  Globe2,
  Play,
  Plus,
  Table2,
  Trash2,
} from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { json, request } from '../api/client'
import { DownloadButton } from '../components/DownloadButton'
import {
  Badge,
  Button,
  ConfirmDialog,
  Dialog,
  EmptyState,
  fieldClass,
  IconButton,
  PageHeader,
  Panel,
  Select,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  tableClass,
  tableWrapClass,
  tabsListClass,
} from '../components/ui'
import type { ExportChat, ExportJob, ExportRun, ExportTask } from '../types'
import { cn } from '../utils/cn'
import { messageFrom, shortDate } from '../utils/format'

const formats = ['json', 'csv', 'html', 'sqlite'] as const
const formatIcons = {
  json: Braces,
  csv: Table2,
  html: Globe2,
  sqlite: Database,
}
const errorClass = cn(
  'rounded-[5px] border border-rose-100 bg-rose-50 p-2',
  'text-[9px] text-rose-700',
)
const formatOptionClass = cn(
  'flex h-10.5 items-center justify-center gap-1.5 rounded-[5px] border',
  'text-[9px] leading-none',
)

function downloadOption(file: string) {
  const filename = file.split('/').pop() ?? file
  return {
    url: `/api/v1/exports/file?path=${encodeURIComponent(file)}`,
    label: (filename.split('.').pop() ?? filename).toUpperCase(),
    filename,
  }
}

export function ExportsPage() {
  const client = useQueryClient()
  const [jobId, setJobId] = useState('')
  const [taskOpen, setTaskOpen] = useState(false)
  const [deletingTaskId, setDeletingTaskId] = useState<number | null>(null)
  const [messageForm, setMessageForm] = useState({
    chat_id: '',
    start_at: '',
    end_at: '',
    formats: ['json', 'html', 'sqlite'],
    subdirectory: 'messages',
    all_history: false,
  })
  const [taskForm, setTaskForm] = useState({
    name: '',
    chat_id: '',
    initial_start_at: '',
    formats: ['json', 'html', 'sqlite'],
    subdirectory: 'scheduled',
    schedule_type: 'daily',
    minute: 0,
    hour: 2,
    weekday: 0,
    timezone: 'Asia/Shanghai',
    all_history: false,
    enabled: true,
  })
  const chats = useQuery({
    queryKey: ['export-chats'],
    queryFn: () => request<ExportChat[]>('/api/v1/exports/chats'),
    retry: false,
  })
  const tasks = useQuery({
    queryKey: ['export-tasks'],
    queryFn: () => request<ExportTask[]>('/api/v1/exports/tasks'),
    refetchInterval: 10_000,
  })
  const runs = useQuery({
    queryKey: ['export-runs'],
    queryFn: () => request<ExportRun[]>('/api/v1/exports/runs?limit=30'),
    refetchInterval: 10_000,
  })
  const job = useQuery({
    queryKey: ['export-job', jobId],
    queryFn: () => request<ExportJob>(`/api/v1/exports/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      ['completed', 'failed', 'cancelled'].includes(
        (query.state.data as ExportJob | undefined)?.status ?? '',
      )
        ? false
        : 1000,
  })
  useEffect(() => {
    if (!messageForm.chat_id && chats.data?.[0])
      setMessageForm((form) => ({ ...form, chat_id: String(chats.data![0].chat_id) }))
  }, [chats.data, messageForm.chat_id])

  const startExport = useMutation({
    mutationFn: () =>
      request<{ job_id: string }>(
        '/api/v1/exports/jobs/messages',
        json('POST', {
          ...messageForm,
          chat_id: Number(messageForm.chat_id),
          start_at: messageForm.start_at || null,
          end_at: messageForm.end_at || null,
        }),
      ),
    onSuccess: (data) => setJobId(data.job_id),
  })
  const saveTask = useMutation({
    mutationFn: () =>
      request(
        '/api/v1/exports/tasks',
        json('POST', {
          ...taskForm,
          chat_id: Number(taskForm.chat_id),
          initial_start_at: taskForm.initial_start_at || null,
        }),
      ),
    onSuccess: () => {
      setTaskOpen(false)
      void client.invalidateQueries({ queryKey: ['export-tasks'] })
    },
  })
  const removeTask = useMutation({
    mutationFn: (id: number) => request(`/api/v1/exports/tasks/${id}`, json('DELETE')),
    onSuccess: () => {
      setDeletingTaskId(null)
      void client.invalidateQueries({ queryKey: ['export-tasks'] })
    },
  })
  async function runTask(id: number) {
    const result = await request<{ job_id: string }>(
      `/api/v1/exports/tasks/${id}/run`,
      json('POST'),
    )
    setJobId(result.job_id)
  }
  function selectFormat(name: string, selected: boolean, target: 'message' | 'task') {
    if (target === 'message')
      setMessageForm((form) => ({
        ...form,
        formats: selected
          ? [...form.formats, name]
          : form.formats.filter((value) => value !== name),
      }))
    else
      setTaskForm((form) => ({
        ...form,
        formats: selected
          ? [...form.formats, name]
          : form.formats.filter((value) => value !== name),
      }))
  }
  function submitTask(event: FormEvent) {
    event.preventDefault()
    saveTask.mutate()
  }
  function openTask() {
    setTaskForm((form) => ({
      ...form,
      chat_id: form.chat_id || String(chats.data?.[0]?.chat_id ?? ''),
    }))
    setTaskOpen(true)
  }

  return (
    <>
      <PageHeader
        eyebrow="ARCHIVE PIPELINE"
        title="导出中心"
        description="导出会话消息，管理定时归档任务与历史文件。"
        actions={
          <Button icon={Plus} onClick={openTask}>
            新建定时任务
          </Button>
        }
      />
      <Tabs defaultValue="instant">
        <TabsList className={tabsListClass}>
          <TabsTrigger value="instant">
            <FileArchive size={16} />
            即时导出
          </TabsTrigger>
          <TabsTrigger value="scheduled">
            <CalendarClock size={16} />
            定时任务 <span>{tasks.data?.length ?? 0}</span>
          </TabsTrigger>
          <TabsTrigger value="history">
            <Archive size={16} />
            运行记录
          </TabsTrigger>
        </TabsList>
        <TabsContent value="instant" className="outline-none">
          <div
            className={cn(
              'grid grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)] gap-3',
              'max-lg:grid-cols-1',
            )}
          >
            <Panel title="创建消息导出" meta={<span>{chats.data?.length ?? 0} 个可用会话</span>}>
              <form
                className="grid grid-cols-2 gap-4 max-md:grid-cols-1"
                onSubmit={(event) => {
                  event.preventDefault()
                  startExport.mutate()
                }}
              >
                <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                  <span>选择会话</span>
                  <Select
                    value={messageForm.chat_id}
                    onValueChange={(chat_id) => setMessageForm({ ...messageForm, chat_id })}
                    placeholder="选择需要导出的会话"
                    options={(chats.data ?? []).map((chat) => ({
                      value: String(chat.chat_id),
                      label: chat.label,
                    }))}
                  />
                </label>
                <label className={fieldClass}>
                  <span>开始时间</span>
                  <input
                    type="datetime-local"
                    value={messageForm.start_at}
                    disabled={messageForm.all_history}
                    onChange={(event) =>
                      setMessageForm({ ...messageForm, start_at: event.target.value })
                    }
                  />
                </label>
                <label className={fieldClass}>
                  <span>结束时间</span>
                  <input
                    type="datetime-local"
                    value={messageForm.end_at}
                    onChange={(event) =>
                      setMessageForm({ ...messageForm, end_at: event.target.value })
                    }
                  />
                </label>
                <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                  <span>保存目录</span>
                  <input
                    value={messageForm.subdirectory}
                    onChange={(event) =>
                      setMessageForm({ ...messageForm, subdirectory: event.target.value })
                    }
                  />
                </label>
                <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                  <span>导出格式</span>
                  <div className="grid grid-cols-4 gap-2 max-sm:grid-cols-2">
                    {formats.map((format) => {
                      const FormatIcon = formatIcons[format]

                      return (
                        <label
                          className={cn(
                            formatOptionClass,
                            messageForm.formats.includes(format)
                              ? 'border-blue-200 bg-blue-50 text-blue-700'
                              : 'border-slate-200 bg-slate-50 text-slate-500',
                          )}
                          key={format}
                        >
                          <input
                            className="sr-only"
                            type="checkbox"
                            checked={messageForm.formats.includes(format)}
                            onChange={(event) =>
                              selectFormat(format, event.target.checked, 'message')
                            }
                          />
                          <FormatIcon className="shrink-0" size={17} />
                          <strong className="inline-flex items-center leading-none">
                            {format.toUpperCase()}
                          </strong>
                        </label>
                      )
                    })}
                  </div>
                </div>
                <div className="col-span-2 max-md:col-span-1">
                  <Switch
                    checked={messageForm.all_history}
                    onCheckedChange={(all_history) =>
                      setMessageForm({ ...messageForm, all_history })
                    }
                    label="导出全部历史"
                    detail="忽略开始时间，从最早消息开始。"
                  />
                </div>
                {chats.error ? (
                  <p className={cn('col-span-2 max-md:col-span-1', errorClass)}>
                    请先在设置中连接 Telegram 会话。
                  </p>
                ) : null}
                {startExport.error ? (
                  <p className={cn('col-span-2 max-md:col-span-1', errorClass)}>
                    {messageFrom(startExport.error)}
                  </p>
                ) : null}
                <Button
                  type="submit"
                  icon={Download}
                  disabled={
                    startExport.isPending || !messageForm.chat_id || !messageForm.formats.length
                  }
                >
                  {startExport.isPending ? '正在创建...' : '开始导出'}
                </Button>
              </form>
            </Panel>
            <Panel
              title="当前任务"
              meta={
                <Badge
                  tone={job.data?.status === 'completed' ? 'green' : job.data ? 'blue' : 'gray'}
                >
                  {job.data?.status ?? '空闲'}
                </Badge>
              }
            >
              {job.data ? (
                <div
                  className={cn(
                    'grid grid-cols-[43px_1fr_auto] items-center gap-3',
                    'max-sm:grid-cols-[43px_1fr]',
                  )}
                >
                  <span
                    className={cn(
                      'grid size-11 place-items-center rounded-[5px]',
                      'bg-blue-50 text-blue-600',
                    )}
                  >
                    <Archive size={24} />
                  </span>
                  <div className="min-w-0">
                    <strong className="text-[11px] text-slate-700">
                      {job.data.phase || '正在处理消息'}
                    </strong>
                    <p className="mt-1 truncate text-[8px] text-slate-400">{job.data.id}</p>
                  </div>
                  <div className="max-sm:col-span-2">
                    <strong className="font-display text-[22px] text-slate-800">
                      {job.data.processed}
                    </strong>
                    {job.data.total ? (
                      <span className="text-[9px] text-slate-400">/ {job.data.total}</span>
                    ) : null}
                  </div>
                  <div className="col-span-full h-2 overflow-hidden rounded-sm bg-slate-100">
                    <i
                      className="block h-full min-w-1 bg-blue-600"
                      style={{
                        width: job.data.total
                          ? `${(job.data.processed / job.data.total) * 100}%`
                          : '18%',
                      }}
                    />
                  </div>
                  {job.data.error ? (
                    <p className={cn('col-span-full', errorClass)}>{job.data.error}</p>
                  ) : null}
                  <div className="col-span-full">
                    <DownloadButton files={job.data.files.map(downloadOption)} />
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon={Archive}
                  title="暂无运行中的导出"
                  detail="创建导出后，实时进度会显示在这里。"
                />
              )}
            </Panel>
          </div>
        </TabsContent>
        <TabsContent value="scheduled" className="outline-none">
          <section className={tableWrapClass}>
            <div className="overflow-x-auto">
              <table className={cn(tableClass, 'max-md:min-w-195')}>
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>会话</th>
                    <th>计划</th>
                    <th>格式</th>
                    <th>下次执行</th>
                    <th aria-label="操作" />
                  </tr>
                </thead>
                <tbody>
                  {(tasks.data ?? []).map((task) => (
                    <tr key={task.id}>
                      <td>
                        <strong className="block text-slate-700">{task.name}</strong>
                        <small className="mt-1 block">
                          <Badge tone={task.enabled ? 'green' : 'gray'}>
                            {task.enabled ? '启用' : '暂停'}
                          </Badge>
                        </small>
                      </td>
                      <td>
                        {task.chat_title || task.chat_id}
                        <small className="mt-1 block text-[8px] text-slate-400">
                          {task.chat_id}
                        </small>
                      </td>
                      <td>
                        {task.schedule_type}
                        <small className="mt-1 block text-[8px] text-slate-400">
                          {String(task.hour).padStart(2, '0')}:
                          {String(task.minute).padStart(2, '0')} · {task.timezone}
                        </small>
                      </td>
                      <td>{task.formats.join(', ')}</td>
                      <td className="min-w-32 font-mono text-slate-500">
                        {shortDate(task.next_run_at)}
                      </td>
                      <td>
                        <div className="flex justify-end gap-1">
                          <IconButton
                            label="立即运行"
                            icon={Play}
                            onClick={() => void runTask(task.id)}
                          />
                          <IconButton
                            label="删除任务"
                            icon={Trash2}
                            onClick={() => setDeletingTaskId(task.id)}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!tasks.data?.length ? (
              <EmptyState
                icon={CalendarClock}
                title="暂无定时任务"
                detail="新建任务后，归档会按计划自动执行。"
              />
            ) : null}
          </section>
        </TabsContent>
        <TabsContent value="history" className="outline-none">
          <section className={tableWrapClass}>
            <div className="overflow-x-auto">
              <table className={cn(tableClass, 'max-md:min-w-195')}>
                <thead>
                  <tr>
                    <th>开始时间</th>
                    <th>类型</th>
                    <th>会话</th>
                    <th>状态</th>
                    <th>消息数</th>
                    <th>文件</th>
                  </tr>
                </thead>
                <tbody>
                  {(runs.data ?? []).map((run) => (
                    <tr key={run.id}>
                      <td className="min-w-32 font-mono text-slate-500">
                        {shortDate(run.started_at)}
                      </td>
                      <td>{run.run_type}</td>
                      <td>{run.chat_title || run.chat_id || '-'}</td>
                      <td>
                        <Badge
                          tone={
                            run.status === 'completed'
                              ? 'green'
                              : run.status === 'failed'
                                ? 'red'
                                : 'blue'
                          }
                        >
                          {run.status}
                        </Badge>
                      </td>
                      <td>{run.message_count}</td>
                      <td>
                        <div className="flex justify-end gap-1">
                          <DownloadButton files={run.files.map(downloadOption)} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!runs.data?.length ? <EmptyState icon={Archive} title="暂无运行记录" /> : null}
          </section>
        </TabsContent>
      </Tabs>

      <Dialog
        open={taskOpen}
        onOpenChange={setTaskOpen}
        title="新建定时导出"
        description="按照本地时区周期性归档指定会话。"
      >
        <form onSubmit={submitTask}>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>任务名称</span>
              <input
                value={taskForm.name}
                onChange={(event) => setTaskForm({ ...taskForm, name: event.target.value })}
                required
              />
            </label>
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>会话</span>
              <Select
                value={taskForm.chat_id}
                onValueChange={(chat_id) => setTaskForm({ ...taskForm, chat_id })}
                options={(chats.data ?? []).map((chat) => ({
                  value: String(chat.chat_id),
                  label: chat.label,
                }))}
              />
            </label>
            <label className={fieldClass}>
              <span>执行周期</span>
              <Select
                value={taskForm.schedule_type}
                onValueChange={(schedule_type) => setTaskForm({ ...taskForm, schedule_type })}
                options={[
                  { value: 'hourly', label: '每小时' },
                  { value: 'daily', label: '每天' },
                  { value: 'weekly', label: '每周' },
                ]}
              />
            </label>
            <label className={fieldClass}>
              <span>时区</span>
              <input
                value={taskForm.timezone}
                onChange={(event) => setTaskForm({ ...taskForm, timezone: event.target.value })}
              />
            </label>
            <label className={fieldClass}>
              <span>小时</span>
              <input
                type="number"
                min="0"
                max="23"
                value={taskForm.hour}
                onChange={(event) => setTaskForm({ ...taskForm, hour: Number(event.target.value) })}
              />
            </label>
            <label className={fieldClass}>
              <span>分钟</span>
              <input
                type="number"
                min="0"
                max="59"
                value={taskForm.minute}
                onChange={(event) =>
                  setTaskForm({ ...taskForm, minute: Number(event.target.value) })
                }
              />
            </label>
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>保存目录</span>
              <input
                value={taskForm.subdirectory}
                onChange={(event) => setTaskForm({ ...taskForm, subdirectory: event.target.value })}
              />
            </label>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>导出格式</span>
              <div className="grid grid-cols-4 gap-2 max-sm:grid-cols-2">
                {formats.map((format) => {
                  const FormatIcon = formatIcons[format]

                  return (
                    <label
                      className={cn(
                        formatOptionClass,
                        taskForm.formats.includes(format)
                          ? 'border-blue-200 bg-blue-50 text-blue-700'
                          : 'border-slate-200 bg-slate-50 text-slate-500',
                      )}
                      key={format}
                    >
                      <input
                        className="sr-only"
                        type="checkbox"
                        checked={taskForm.formats.includes(format)}
                        onChange={(event) => selectFormat(format, event.target.checked, 'task')}
                      />
                      <FormatIcon className="shrink-0" size={17} />
                      <strong className="inline-flex items-center leading-none">
                        {format.toUpperCase()}
                      </strong>
                    </label>
                  )
                })}
              </div>
            </div>
          </div>
          <div
            className={cn(
              'mt-5 grid grid-cols-2 gap-2 border-t border-slate-100 pt-4',
              'max-md:grid-cols-1',
            )}
          >
            <Switch
              checked={taskForm.enabled}
              onCheckedChange={(enabled) => setTaskForm({ ...taskForm, enabled })}
              label="启用任务"
            />
            <Switch
              checked={taskForm.all_history}
              onCheckedChange={(all_history) => setTaskForm({ ...taskForm, all_history })}
              label="首次导出全部历史"
            />
          </div>
          {saveTask.error ? (
            <p
              className={cn(
                'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                'text-[9px] text-rose-700',
              )}
            >
              {messageFrom(saveTask.error)}
            </p>
          ) : null}
          <div className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button type="button" variant="secondary" onClick={() => setTaskOpen(false)}>
              取消
            </Button>
            <Button
              type="submit"
              disabled={saveTask.isPending || !taskForm.chat_id || !taskForm.formats.length}
            >
              保存任务
            </Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        open={deletingTaskId !== null}
        onOpenChange={(next) => {
          if (!next) setDeletingTaskId(null)
        }}
        title="删除定时任务"
        description={`确定删除“${tasks.data?.find((task) => task.id === deletingTaskId)?.name ?? '这个定时任务'}”？已有导出文件不会被删除。`}
        confirmLabel="删除任务"
        pending={removeTask.isPending}
        onConfirm={() => {
          if (deletingTaskId !== null) removeTask.mutate(deletingTaskId)
        }}
      />
    </>
  )
}
