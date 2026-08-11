import { useCallback, useEffect, useState } from 'react'
import { DirectoryWorkspace } from '../directory/DirectoryWorkspace'
import { LoadingState } from '../shared/AsyncState'
import { useUserSettings } from '../../hooks/useUserSettings'
import { BoardProject } from './BoardProject'

interface ProjectsViewProps {
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
  focusedTaskId: string | null
  onFocusedTaskHandled: () => void
}

export function ProjectsView({ selectedRecordId, onSelectedRecordChange, focusedTaskId, onFocusedTaskHandled }: ProjectsViewProps) {
  const { settings, loading: settingsLoading, updateSelectedId } = useUserSettings()
  const [initialSelectionResolved, setInitialSelectionResolved] = useState(false)

  useEffect(() => {
    if (settingsLoading || initialSelectionResolved) return

    onSelectedRecordChange(settings?.selected_task_board_id ?? null)
    setInitialSelectionResolved(true)
  }, [initialSelectionResolved, onSelectedRecordChange, settings?.selected_task_board_id, settingsLoading])

  const handleSelectedRecordChange = useCallback((recordId: string | null) => {
    onSelectedRecordChange(recordId)
    if (recordId !== settings?.selected_task_board_id) {
      void updateSelectedId('projects', recordId)
    }
  }, [onSelectedRecordChange, settings?.selected_task_board_id, updateSelectedId])

  if (!initialSelectionResolved) return <LoadingState label="Loading Task Boards…" />

  return (
    <DirectoryWorkspace
      boardType="projects"
      selectedRecordId={selectedRecordId}
      onSelectedRecordChange={handleSelectedRecordChange}
      renderContent={props => (
        <BoardProject
          tasks={props.tasks}
          focusedTaskId={focusedTaskId}
          onFocusedTaskHandled={onFocusedTaskHandled}
          onAddTask={props.onAddTask}
          onToggleTask={props.onToggleTask}
          onUpdateTask={props.onUpdateTask}
          onDeleteTask={props.onDeleteTask}
        />
      )}
    />
  )
}
