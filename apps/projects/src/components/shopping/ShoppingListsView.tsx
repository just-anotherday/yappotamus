import { useCallback, useEffect, useState } from 'react'
import { DirectoryWorkspace } from '../directory/DirectoryWorkspace'
import { ShoppingListProject } from '../projects/ShoppingListProject'
import { useShoppingStores } from '../../hooks/useShoppingStores'
import { useShoppingTrip } from '../../hooks/useShoppingTrip'
import { useUserSettings } from '../../hooks/useUserSettings'
import { LoadingState } from '../shared/AsyncState'

interface ShoppingListsViewProps {
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
}

export function ShoppingListsView({
  selectedRecordId,
  onSelectedRecordChange,
}: ShoppingListsViewProps) {
  const { settings, loading: settingsLoading, updateSelectedId } = useUserSettings()
  const [initialSelectionResolved, setInitialSelectionResolved] = useState(false)
  const stores = useShoppingStores()
  const trip = useShoppingTrip()

  useEffect(() => {
    if (settingsLoading || initialSelectionResolved) return

    onSelectedRecordChange(settings?.selected_shopping_list_id ?? null)
    setInitialSelectionResolved(true)
  }, [initialSelectionResolved, onSelectedRecordChange, settings?.selected_shopping_list_id, settingsLoading])

  const handleSelectedRecordChange = useCallback((recordId: string | null) => {
    onSelectedRecordChange(recordId)
    if (recordId !== settings?.selected_shopping_list_id) {
      void updateSelectedId('shopping', recordId)
    }
  }, [onSelectedRecordChange, settings?.selected_shopping_list_id, updateSelectedId])

  if (!initialSelectionResolved) return <LoadingState label="Loading Shopping Listsâ€¦" />

  return (
    <DirectoryWorkspace
      boardType="shopping"
      selectedRecordId={selectedRecordId}
      onSelectedRecordChange={handleSelectedRecordChange}
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
