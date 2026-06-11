import { X } from 'lucide-react'
import { useStore } from '../../store'

const KIND_CLS = {
  info:    'border-blue-700   bg-blue-900/80   text-blue-200',
  success: 'border-green-700  bg-green-900/80  text-green-200',
  warn:    'border-yellow-700 bg-yellow-900/80 text-yellow-200',
  error:   'border-red-700    bg-red-900/80    text-red-200',
}

export function ToastContainer() {
  const toasts      = useStore(s => s.toasts)
  const removeToast = useStore(s => s.removeToast)

  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 items-end">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-sm
            shadow-lg max-w-xs animate-count-up ${KIND_CLS[t.kind]}`}
        >
          <span className="flex-1">{t.message}</span>
          <button onClick={() => removeToast(t.id)} className="opacity-60 hover:opacity-100 mt-0.5">
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  )
}
