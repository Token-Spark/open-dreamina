import type { TaskStatus, TaskType } from '@/api/tasks'

export const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '排队中',
  queued: '已入队',
  running: '生成中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export const TASK_TYPE_LABEL: Record<TaskType, string> = {
  text2img: '文生图',
  img2img: '图生图',
  text2video: '文生视频',
  img2video: '图生视频',
}

type BadgeVariant = 'default' | 'success' | 'error' | 'outline'

export function statusBadgeVariant(status: TaskStatus): BadgeVariant {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'error'
    case 'cancelled':
      return 'outline'
    default:
      return 'default'
  }
}

export function isActiveStatus(status: TaskStatus): boolean {
  return status === 'pending' || status === 'queued' || status === 'running'
}
