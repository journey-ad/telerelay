import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '../../utils/cn'

export const Tabs = TabsPrimitive.Root
export const TabsList = TabsPrimitive.List
export const TabsTrigger = TabsPrimitive.Trigger
export const TabsContent = TabsPrimitive.Content

export const tabsListClass = cn(
  'mb-3 flex w-fit max-w-full gap-1 overflow-x-auto rounded-md bg-slate-200/70 p-1',
  '[&>button]:flex [&>button]:h-8.5 [&>button]:min-w-max [&>button]:items-center',
  '[&>button]:gap-2 [&>button]:rounded [&>button]:border-0 [&>button]:bg-transparent',
  '[&>button]:px-3 [&>button]:text-xs [&>button]:text-slate-500',
  '[&>button[data-state=active]]:bg-white [&>button[data-state=active]]:text-blue-700',
  '[&>button[data-state=active]]:shadow-sm',
)
