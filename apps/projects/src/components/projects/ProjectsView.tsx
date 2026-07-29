import { DirectoryWorkspace } from '../directory/DirectoryWorkspace'
import { BoardProject } from './BoardProject'

interface ProjectsViewProps {
  selectedRecordId: string | null
  onSelectedRecordChange: (recordId: string | null) => void
}

export function ProjectsView({ selectedRecordId, onSelectedRecordChange }: ProjectsViewProps) {
  return (
    <DirectoryWorkspace
      boardType="projects"
      selectedRecordId={selectedRecordId}
      onSelectedRecordChange={onSelectedRecordChange}
      renderContent={props => (
        <BoardProject
          tasks={props.tasks}
          onAddTask={props.onAddTask}
          onToggleTask={props.onToggleTask}
          onUpdateTask={props.onUpdateTask}
          onDeleteTask={props.onDeleteTask}
        />
      )}
    />
  )
}
