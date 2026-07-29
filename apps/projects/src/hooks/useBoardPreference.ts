import { useCallback, useEffect, useState } from 'react'
import { isBoardType, type BoardType } from '../types/boards'

const preferencePrefix = 'yapvibes:organizer:board'
const defaultBoard: BoardType = 'projects'

interface BoardPreferenceState {
  userId: string
  boardType: BoardType
}

export function getBoardPreferenceKey(userId: string) {
  return `${preferencePrefix}:${userId}`
}

function readBoardPreference(userId: string): BoardType {
  try {
    const storedValue = window.localStorage.getItem(getBoardPreferenceKey(userId))
    return isBoardType(storedValue) ? storedValue : defaultBoard
  } catch {
    return defaultBoard
  }
}

export function useBoardPreference(userId: string) {
  const [preference, setPreference] = useState<BoardPreferenceState>(() => ({
    userId,
    boardType: readBoardPreference(userId),
  }))

  useEffect(() => {
    setPreference({
      userId,
      boardType: readBoardPreference(userId),
    })
  }, [userId])

  const boardType = preference.userId === userId ? preference.boardType : defaultBoard

  const setBoardType = useCallback((nextBoardType: BoardType) => {
    setPreference({ userId, boardType: nextBoardType })
    try {
      window.localStorage.setItem(getBoardPreferenceKey(userId), nextBoardType)
    } catch {
      // Storage can be unavailable in privacy modes. The session state still works.
    }
  }, [userId])

  return { boardType, setBoardType }
}
