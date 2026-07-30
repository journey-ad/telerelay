import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Check, ChevronDown, Download } from 'lucide-react'
import { useState } from 'react'
import { downloadFile } from '../api/downloads'
import { cn } from '../utils/cn'

interface FileOption {
  url: string
  label: string
  filename: string
}

export function DownloadButton({
  files,
  className = '',
}: {
  files: FileOption[]
  className?: string
}) {
  const [selectedUrl, setSelectedUrl] = useState(files[0]?.url ?? '')
  const selected = files.find((file) => file.url === selectedUrl) ?? files[0]

  if (files.length === 0) return null
  if (files.length === 1) {
    const file = files[0]
    return (
      <button
        type="button"
        onClick={() => void downloadFile(file.url, file.filename)}
        className={cn(
          'inline-flex min-h-9 items-center gap-2 rounded-[5px] border px-3.5',
          'border-slate-200 bg-white text-[11px] font-semibold text-slate-600',
          'transition hover:border-blue-200 hover:text-blue-600 active:translate-y-px',
          className,
        )}
      >
        <Download size={16} strokeWidth={2} />
        下载 {file.label}
      </button>
    )
  }
  return (
    <div className={cn('inline-flex', className)}>
      <button
        type="button"
        onClick={() => void downloadFile(selected.url, selected.filename)}
        className={cn(
          'inline-flex min-h-9 items-center gap-2 rounded-l-[5px] border border-r-0 px-3.5',
          'border-slate-200 bg-white text-[11px] font-semibold text-slate-600',
          'transition hover:border-blue-200 hover:text-blue-600 active:translate-y-px',
        )}
      >
        <Download size={16} strokeWidth={2} />
        下载 {selected.label}
      </button>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label="选择下载格式"
            className={cn(
              'inline-flex min-h-9 items-center rounded-r-[5px] border px-2',
              'border-slate-200 bg-white text-slate-500',
              'transition hover:border-blue-200 hover:text-blue-600',
            )}
          >
            <ChevronDown size={14} strokeWidth={2} />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className={cn(
              'z-100 min-w-36 rounded-md border border-slate-200 bg-white p-1 shadow-xl',
            )}
            sideOffset={5}
            align="end"
          >
            {files.map((file) => (
              <DropdownMenu.Item
                key={file.url}
                className={cn(
                  'flex h-8.5 items-center justify-between rounded px-2',
                  'text-[11px] text-slate-600 outline-none cursor-pointer',
                  'data-[highlighted]:bg-blue-50 data-[highlighted]:text-blue-700',
                )}
                onSelect={() => setSelectedUrl(file.url)}
              >
                {file.label}
                {file.url === selected.url ? <Check size={14} /> : null}
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  )
}
