import type { InterventionAction } from '../types';
import { getState, resetTaskState } from '../state/store';
import { $ } from '../utils/dom';
import { api } from '../api/client';
import { fetchTaskDetails, loadTasksList, resetLastDetails } from './tasks';

export async function submitIntervention(action: InterventionAction): Promise<void> {
  const taskId = getState('currentTaskId');
  if (!taskId) return;

  const payload: Record<string, unknown> = { action };
  const consoleEl = $('#intervention-console');
  const buttons = consoleEl?.querySelectorAll<HTMLButtonElement>('.btn-intervention');

  if (action === 'modify') {
    const nameEl = $('#proposed-tool-name');
    const argsEl = $('#proposed-tool-args') as HTMLTextAreaElement | null;
    const toolName = nameEl?.textContent?.trim() ?? '';
    let toolArgs: Record<string, unknown> = {};

    try {
      toolArgs = argsEl ? JSON.parse(argsEl.value) : {};
    } catch {
      alert('Invalid JSON format in arguments.');
      return;
    }

    payload.modified_tool = { name: toolName, args: toolArgs };
  }

  if (action === 'continue') {
    payload.action = 'inject';
    payload.user_prompt = 'continue';
  }

  if (buttons) buttons.forEach(btn => { btn.disabled = true; });

  try {
    if (consoleEl) {
      consoleEl.style.opacity = '0.5';
      consoleEl.style.pointerEvents = 'none';
    }

    await api.taskAction(taskId, payload);
    resetTaskState();
    resetLastDetails();
    await fetchTaskDetails(taskId);
    await loadTasksList();
  } catch (err) {
    console.error('Error submitting intervention', err);
    alert(`Failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
  } finally {
    if (consoleEl) {
      consoleEl.style.opacity = '1';
      consoleEl.style.pointerEvents = 'all';
    }
    if (buttons) buttons.forEach(btn => { btn.disabled = false; });
  }
}

export async function sendChatPrompt(): Promise<void> {
  const taskId = getState('currentTaskId');
  if (!taskId) return;

  const input = $('#chat-bar-prompt') as HTMLTextAreaElement | null;
  const sendBtn = $('#btn-chat-send') as HTMLButtonElement | null;
  const prompt = input?.value.trim();

  if (!prompt) {
    input?.focus();
    return;
  }

  if (sendBtn) sendBtn.disabled = true;
  if (input) input.disabled = true;

  try {
    await api.taskAction(taskId, { action: 'inject', user_prompt: prompt });

    if (input) input.value = '';
    resetTaskState();
    resetLastDetails();
    await fetchTaskDetails(taskId);
    await loadTasksList();
  } catch (err) {
    console.error('Error sending prompt', err);
    alert(`Failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    if (input) {
      input.disabled = false;
      input.focus();
    }
  }
}

export function initIntervention(): void {
  $('#btn-approve-tool')?.addEventListener('click', () => submitIntervention('approve'));
  $('#btn-modify-tool')?.addEventListener('click', () => submitIntervention('modify'));
  $('#btn-intervene-continue')?.addEventListener('click', () => submitIntervention('continue'));
  $('#btn-chat-send')?.addEventListener('click', sendChatPrompt);

  const chatInput = $('#chat-bar-prompt') as HTMLTextAreaElement | null;
  chatInput?.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      sendChatPrompt();
    }
  });
}
