import * as DialogPrimitive from '@radix-ui/react-dialog'
import { TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../utils/cn'
import { Button } from './button'

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  pending = false,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel?: string
  pending?: boolean
  onConfirm: () => void
}) {
  const { t } = useTranslation()
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!pending) onOpenChange(next)
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-110 bg-slate-900/45 backdrop-blur-[3px]',
            'data-[state=open]:animate-in data-[state=open]:fade-in',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed top-1/2 left-1/2 z-111 w-[calc(100%_-_24px)] max-w-105',
            '-translate-x-1/2 -translate-y-1/2 rounded-md border border-slate-200',
            'bg-white p-5 shadow-2xl outline-none',
            'data-[state=open]:animate-in data-[state=open]:fade-in data-[state=open]:zoom-in-95',
          )}
          onEscapeKeyDown={(event) => {
            if (pending) event.preventDefault()
          }}
          onPointerDownOutside={(event) => {
            if (pending) event.preventDefault()
          }}
        >
          <div className="flex items-start gap-3.5">
            <span className="grid size-10 shrink-0 place-items-center rounded-[5px] bg-rose-50 text-rose-600">
              <TriangleAlert size={20} />
            </span>
            <div className="min-w-0 pt-0.5">
              <DialogPrimitive.Title className="m-0 text-base font-bold text-slate-700">
                {title}
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="mt-1.5 text-xs leading-4.5 text-slate-500">
                {description}
              </DialogPrimitive.Description>
            </div>
          </div>
          <div className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <DialogPrimitive.Close asChild>
              <Button type="button" variant="secondary" disabled={pending}>
                {t('common.cancel')}
              </Button>
            </DialogPrimitive.Close>
            <Button type="button" variant="danger" disabled={pending} onClick={onConfirm}>
              {pending ? t('common.processing') : (confirmLabel ?? t('common.confirm'))}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
