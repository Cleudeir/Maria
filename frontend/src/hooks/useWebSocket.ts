import { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { useApp } from '../context/AppContext';
import type { Task, TaskStatus, DashboardStats } from '../types';

let socket: Socket | null = null;

function getSocket(): Socket {
  if (!socket) {
    const url = window.location.origin;
    socket = io(url, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: Infinity,
    });
  }
  return socket;
}

export function useWebSocket() {
  const {
    currentTaskId,
    setTasksFromWS,
    setTaskDetailsFromWS,
    setDashboardFromWS,
    loadTasksList,
    fetchTaskDetails,
    refreshDashboard,
  } = useApp();

  const currentTaskIdRef = useRef(currentTaskId);
  currentTaskIdRef.current = currentTaskId;
  const subscribedTaskRef = useRef<string | null>(null);

  useEffect(() => {
    const s = getSocket();

    const onConnect = () => {
      loadTasksList();
      if (currentTaskIdRef.current) {
        fetchTaskDetails(currentTaskIdRef.current);
      } else {
        refreshDashboard();
      }
    };

    const onTasksListUpdate = (tasks: Array<{ task_id: string; task: string; status: string; step: number; created_at?: string }>) => {
      setTasksFromWS(tasks.map(t => ({ ...t, status: t.status as TaskStatus })));
    };

    const onTaskUpdate = (task: Task) => {
      const taskId = task.task_id;
      if (taskId === currentTaskIdRef.current) {
        setTaskDetailsFromWS(task);
      }
    };

    const onDashboardUpdate = (stats: DashboardStats) => {
      setDashboardFromWS(stats);
    };

    s.on('connect', onConnect);
    s.on('tasks_list_update', onTasksListUpdate);
    s.on('task_update', onTaskUpdate);
    s.on('dashboard_update', onDashboardUpdate);

    if (s.connected) {
      onConnect();
    }

    return () => {
      s.off('connect', onConnect);
      s.off('tasks_list_update', onTasksListUpdate);
      s.off('task_update', onTaskUpdate);
      s.off('dashboard_update', onDashboardUpdate);
    };
  }, [loadTasksList, fetchTaskDetails, refreshDashboard, setTasksFromWS, setTaskDetailsFromWS, setDashboardFromWS]);

  useEffect(() => {
    const s = getSocket();

    if (subscribedTaskRef.current) {
      s.emit('unsubscribe_task', { task_id: subscribedTaskRef.current });
      subscribedTaskRef.current = null;
    }

    if (currentTaskId) {
      s.emit('subscribe_task', { task_id: currentTaskId });
      subscribedTaskRef.current = currentTaskId;
    }

    return () => {
      if (subscribedTaskRef.current) {
        s.emit('unsubscribe_task', { task_id: subscribedTaskRef.current });
        subscribedTaskRef.current = null;
      }
    };
  }, [currentTaskId]);
}
