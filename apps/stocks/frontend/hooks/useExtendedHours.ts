'use client';

import { useEffect, useState } from 'react';

export interface ExtendedHoursState {
  isExtendedHours: boolean;
  shouldPoll: boolean;
}

export function getExtendedHoursState(now = new Date()): ExtendedHoursState {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(now);
    const value = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find(part => part.type === type)?.value;

    const weekday = value('weekday');
    const hour = Number(value('hour'));
    const minute = Number(value('minute'));
    const isWeekday = weekday != null && !['Sat', 'Sun'].includes(weekday);
    const minutesSinceMidnight = hour * 60 + minute;
    const marketOpen = 9 * 60 + 30;
    const marketClose = 16 * 60;
    const isExtendedHours = isWeekday && (
      minutesSinceMidnight < marketOpen || minutesSinceMidnight >= marketClose
    );

    // Quotes can move from 4:00 AM through 8:00 PM ET. Outside that window,
    // retain the latest value without repeatedly refetching static data.
    const shouldPoll = isWeekday && (
      (minutesSinceMidnight >= 4 * 60 && minutesSinceMidnight < marketOpen) ||
      (minutesSinceMidnight >= marketClose && minutesSinceMidnight < 20 * 60)
    );

    return { isExtendedHours, shouldPoll };
  } catch {
    return { isExtendedHours: false, shouldPoll: false };
  }
}

export function useExtendedHours(): ExtendedHoursState {
  const [state, setState] = useState<ExtendedHoursState>(() => getExtendedHoursState());

  useEffect(() => {
    const update = () => setState(getExtendedHoursState());
    const id = setInterval(update, 60_000);
    return () => clearInterval(id);
  }, []);

  return state;
}