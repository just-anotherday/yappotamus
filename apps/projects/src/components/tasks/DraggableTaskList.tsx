import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import type { UniqueIdentifier } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { Task } from '../../lib/types/database.types'

interface SortableTaskWrapperProps {
  id: string
  children: React.ReactNode
  disabled: boolean
}

function SortableTaskWrapper({ id, children, disabled }: SortableTaskWrapperProps) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div ref={setNodeRef} style={style} className="relative">
      {!disabled && (
        <button
          type="button"
          {...attributes}
          {...listeners}
          className="absolute right-2 top-2 z-10 grid size-11 cursor-grab place-items-center rounded-lg text-stone-400 touch-none hover:bg-stone-100 hover:text-stone-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 active:cursor-grabbing dark:hover:bg-stone-800 dark:hover:text-stone-200"
          aria-label="Drag to reorder task"
          title="Drag to reorder"
        >
          <span aria-hidden="true" className="text-xl leading-none">⠿</span>
        </button>
      )}
      {children}
    </div>
  )
}

interface DragEvent {
  active: { id: UniqueIdentifier }
  over: { id: UniqueIdentifier } | null
}

interface DraggableTaskListProps {
  tasks: Task[]
  children: (task: Task) => React.ReactNode
  onDragEnd: (event: DragEvent) => void
  dragEnabled: boolean
}

export function DraggableTaskList({ tasks, children, onDragEnd, dragEnabled }: DraggableTaskListProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor)
  )

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={(event) => {
        if (!dragEnabled || !event.over) return
        
        const { active, over } = event
        
        onDragEnd({ active, over })
      }}
    >
      <SortableContext items={tasks.map(t => t.id)} strategy={verticalListSortingStrategy}>
        <div className="space-y-2">
          {tasks.map(task => (
            <SortableTaskWrapper key={task.id} id={task.id} disabled={!dragEnabled}>
              {children(task)}
            </SortableTaskWrapper>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  )
}
