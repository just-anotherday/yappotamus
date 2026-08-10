import { DirectoryWorkspace } from '../directory/DirectoryWorkspace'
import { ShoppingListProject } from '../projects/ShoppingListProject'
import { useShoppingStores } from '../../hooks/useShoppingStores'
import { useShoppingTrip } from '../../hooks/useShoppingTrip'

interface ShoppingListsViewProps {
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
}

export function ShoppingListsView({
  selectedRecordId,
  onSelectedRecordChange,
}: ShoppingListsViewProps) {
  const stores = useShoppingStores()
  const trip = useShoppingTrip()
  return (
    <DirectoryWorkspace
      boardType="shopping"
      selectedRecordId={selectedRecordId}
      onSelectedRecordChange={onSelectedRecordChange}
      renderContent={props => (
        <ShoppingListProject
          projectId={props.project.id}
          projectName={props.project.name}
          tasks={props.tasks}
          onAddTask={props.onAddTask}
          onToggleTask={props.onToggleTask}
          onUpdateTask={props.onUpdateTask}
          onDeleteTask={props.onDeleteTask}
          onDeleteTasks={props.onDeleteTasks}
          stores={stores.stores}
          storesError={stores.error}
          onCreateStore={stores.createStore}
          onRenameStore={stores.renameStore}
          onDeleteStore={stores.deleteStore}
          onMoveStore={stores.moveStore}
          onFinishTrip={trip.finishTrip}
          tripPending={trip.pending}
          tripError={trip.error}
          onClearTripError={trip.clearError}
        />
      )}
    />
  )
}
