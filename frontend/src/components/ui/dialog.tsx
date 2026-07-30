import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../utils/cn'
import { IconButton } from './button'

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-80 bg-slate-900/45 backdrop-blur-[3px]',
            'data-[state=open]:animate-in data-[state=open]:fade-in',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed top-0 right-0 z-81 h-dvh w-full max-w-155 overflow-y-auto',
            'bg-white p-5.5 shadow-2xl outline-none max-md:p-4',
            'data-[state=open]:animate-in data-[state=open]:slide-in-from-right-8',
          )}
        >
          <header
            className={cn(
              '-mx-5.5 -mt-5.5 mb-5.5 flex items-start justify-between gap-5',
              'border-b border-slate-200 p-5.5 max-md:-mx-4 max-md:-mt-4 max-md:p-4',
            )}
          >
            <div>
              <DialogPrimitive.Title className="mb-1 text-[17px] font-bold text-slate-700">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="m-0 text-xs leading-4 text-slate-500">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
            </div>
            <DialogPrimitive.Close asChild>
              <IconButton label={t('common.close')} icon={X} type="button" />
            </DialogPrimitive.Close>
          </header>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
