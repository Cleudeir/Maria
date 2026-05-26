import type { TabName } from '../types';
import { $$ } from '../utils/dom';

export function switchTab(tab: TabName): void {
  $$('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });

  document.querySelectorAll<HTMLElement>('.tab-content').forEach(content => {
    content.classList.remove('active');
  });

  const target = document.getElementById(`tab-${tab}`);
  if (target) target.classList.add('active');
}

export function initTabs(): void {
  $$('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab as TabName;
      if (tab) switchTab(tab);
    });
  });
}
