export function $(selector: string): HTMLElement | null {
  return document.querySelector(selector);
}

export function $$(selector: string): NodeListOf<HTMLElement> {
  return document.querySelectorAll(selector);
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs?: Record<string, string | boolean | number>,
  ...children: (string | Node)[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);

  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'className') {
        element.className = String(value);
      } else if (key.startsWith('on') && typeof value === 'function') {
        element.addEventListener(key.slice(2).toLowerCase(), value as EventListener);
      } else if (typeof value === 'boolean') {
        if (value) element.setAttribute(key, '');
      } else {
        element.setAttribute(key, String(value));
      }
    }
  }

  for (const child of children) {
    if (typeof child === 'string') {
      element.appendChild(document.createTextNode(child));
    } else {
      element.appendChild(child);
    }
  }

  return element;
}

export function setHtml(element: HTMLElement | null, html: string): void {
  if (element) element.innerHTML = html;
}

export function setText(element: HTMLElement | null, text: string): void {
  if (element) element.textContent = text;
}

export function show(element: HTMLElement | null, display = 'flex'): void {
  if (element) element.style.display = display;
}

export function hide(element: HTMLElement | null): void {
  if (element) element.style.display = 'none';
}

export function toggleClass(
  element: HTMLElement | null,
  className: string,
  force?: boolean,
): void {
  if (element) element.classList.toggle(className, force);
}
