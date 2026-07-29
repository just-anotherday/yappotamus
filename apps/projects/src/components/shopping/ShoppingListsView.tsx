import { DirectoryWorkspace } from '../directory/DirectoryWorkspace'
import { ShoppingListProject } from '../projects/ShoppingListProject'

interface ShoppingListsViewProps {
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
}

export function ShoppingListsView({
  selectedRecordId,
  onSelectedRecordChange,
}: ShoppingListsViewProps) {
  return (
    <DirectoryWorkspace
      boardType="shopping"
      selectedRecordId={selectedRecordId}
      onSelectedRecordChange={onSelectedRecordChange}
      renderContent={props => (
        <ShoppingListProject
          tasks={props.tasks}
          onAddTask={props.onAddTask}
          onToggleTask={props.onToggleTask}
          onUpdateTask={props.onUpdateTask}
          onDeleteTask={props.onDeleteTask}
          onDeleteTasks={props.onDeleteTasks}
        />
      )}
    />
  )
}
