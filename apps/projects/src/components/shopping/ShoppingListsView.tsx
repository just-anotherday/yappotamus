import { useCallback } from 'react'
import { DirectoryWorkspace } from '../directory/DirectoryWorkspace'
import { ShoppingListProject } from '../projects/ShoppingListProject'
import { useShoppingStores } from '../../hooks/useShoppingStores'
import { useShoppingTrip } from '../../hooks/useShoppingTrip'
import { useGeneralShoppingItems } from '../../hooks/useGeneralShoppingItems'
import { useUserSettings } from '../../hooks/useUserSettings'

interface ShoppingListsViewProps {
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
}

export function ShoppingListsView({
  selectedRecordId,
  onSelectedRecordChange,
}: ShoppingListsViewProps) {
  const { settings, patchSettings, updateSelectedId } = useUserSettings()
  const stores = useShoppingStores()
  const trip = useShoppingTrip()
  const generalItems = useGeneralShoppingItems()

  const handleSelectedRecordChange = useCallback((recordId: string | null) => {
    onSelectedRecordChange(recordId)
    if (recordId !== settings?.selected_shopping_list_id) {
      void updateSelectedId('shopping', recordId)
    }
  }, [onSelectedRecordChange, settings?.selected_shopping_list_id, updateSelectedId])

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
          generalItems={generalItems.items}
          generalLoading={generalItems.loading}
          generalError={generalItems.error}
          onAddGeneralItem={generalItems.addItem}
          onUpdateGeneralItem={generalItems.updateItem}
          onToggleGeneralItem={generalItems.toggleItem}
          onDeleteGeneralItem={generalItems.deleteItem}
          onClearCheckedGeneral={generalItems.clearChecked}
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
          hiddenShoppingCategories={settings?.hidden_shopping_categories ?? null}
          onHiddenShoppingCategoriesChange={hidden_shopping_categories => void patchSettings({ hidden_shopping_categories })}
        />
      )}
    />
  )
}
