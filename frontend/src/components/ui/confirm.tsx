import { createRoot } from 'react-dom/client'
import { useState } from 'react'
import { I18nextProvider } from 'react-i18next'
import i18n from '../../i18n'
import { ConfirmDialog } from './confirm-dialog'

export interface ConfirmOptions {
  title: string
  description: string
  confirmLabel?: string
  onConfirm: () => Promise<unknown> | void
}

export function confirm(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const root = createRoot(host)
    const settle = (result: boolean) => {
      root.unmount()
      host.remove()
      resolve(result)
    }

    function ConfirmHost() {
      const [pending, setPending] = useState(false)
      return (
        <ConfirmDialog
          open
          onOpenChange={(next) => {
            if (!next && !pending) settle(false)
          }}
          title={options.title}
          description={options.description}
          confirmLabel={options.confirmLabel}
          pending={pending}
          onConfirm={() => {
            const promise = options.onConfirm() as Promise<void> | void
            if (promise && typeof promise.then === 'function') {
              setPending(true)
              promise.then(
                () => settle(true),
                () => settle(false),
              )
            } else {
              settle(true)
            }
          }}
        />
      )
    }

    root.render(
      <I18nextProvider i18n={i18n}>
        <ConfirmHost />
      </I18nextProvider>,
    )
  })
}
