import type { TaskNavigationTarget } from '../context/TaskNavigationContext'

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function readTaskDeepLink(search: string): TaskNavigationTarget | null {
  const params = new URLSearchParams(search)
  const projectId = params.get('project')
  const taskId = params.get('task')

  if (
    params.get('board') !== 'projects'
    || !projectId
    || !taskId
    || !uuidPattern.test(projectId)
    || !uuidPattern.test(taskId)
  ) return null

  return { projectId, taskId }
}
