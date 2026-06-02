import { useEffect, useRef } from 'react';
import { useApp } from '../context/AppContext';

const _renderCount = { current: 0 };
const _intervalCount = { current: 0 };

export function usePolling() {
  const renderCount = ++_renderCount.current;
  const mountTime = useRef(Date.now());

  const {
    currentTaskId, activeTaskStatus,
    loadTasksList, fetchTaskDetails, refreshDashboard,
    lastDetailsJson,
  } = useApp();

  console.log(`[usePolling] render #${renderCount} elapsed=${Date.now()-mountTime.current}ms taskId=${currentTaskId} status=${activeTaskStatus} hasDetails=${!!lastDetailsJson}`);

  const refs = useRef({ activeTaskStatus, lastDetailsJson, loadTasksList, fetchTaskDetails, refreshDashboard });
  refs.current = { activeTaskStatus, lastDetailsJson, loadTasksList, fetchTaskDetails, refreshDashboard };

  useEffect(() => {
    const intervalId = ++_intervalCount.current;
    mountTime.current = Date.now();
    console.log(`[usePolling] INTERVAL START #${intervalId} taskId=${currentTaskId}`);

    const interval = setInterval(async () => {
      console.log(`[usePolling] POLL #${intervalId} fire taskId=${currentTaskId}`);
      const t0 = Date.now();
      const { activeTaskStatus, lastDetailsJson, loadTasksList, fetchTaskDetails, refreshDashboard } = refs.current;
      await loadTasksList();
      if (currentTaskId) {
        const needsPoll =
          activeTaskStatus === 'running' ||
          activeTaskStatus === 'processando' ||
          !lastDetailsJson;
        console.log(`[usePolling] POLL #${intervalId} needsPoll=${needsPoll} status=${activeTaskStatus} took=${Date.now()-t0}ms`);
        if (needsPoll) {
          await fetchTaskDetails(currentTaskId);
        }
      } else {
        await refreshDashboard();
      }
      console.log(`[usePolling] POLL #${intervalId} done took=${Date.now()-t0}ms`);
    }, 1200);
    return () => {
      console.log(`[usePolling] INTERVAL STOP #${intervalId} taskId=${currentTaskId}`);
      clearInterval(interval);
    };
  }, [currentTaskId]);
}
