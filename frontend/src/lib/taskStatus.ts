// Copyright 2026 Open Dreamina Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
