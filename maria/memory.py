import os
from datetime import datetime
from typing import List, Dict
from bs4 import BeautifulSoup

def load_system_prompt(memory_dir: str) -> str:
    path = os.path.join(memory_dir, "system_prompt.html")
    if not os.path.exists(path):
        raise FileNotFoundError(f"System prompt file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    pre_tag = soup.find(id="system-prompt")
    return pre_tag.text if pre_tag else ""

def save_system_prompt(memory_dir: str, new_prompt: str):
    path = os.path.join(memory_dir, "system_prompt.html")
    if not os.path.exists(path):
        raise FileNotFoundError(f"System prompt file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    pre_tag = soup.find(id="system-prompt")
    if pre_tag:
        pre_tag.string = new_prompt
    
    meta_div = soup.find(class_="meta")
    if meta_div:
        meta_div.string = f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
    with open(path, "w", encoding="utf-8") as f:
        # Write prettified or raw string
        f.write(str(soup))

def load_lessons(memory_dir: str) -> List[Dict[str, str]]:
    path = os.path.join(memory_dir, "lessons.html")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    lessons = []
    list_div = soup.find(id="lessons-list")
    if list_div:
        for item in list_div.find_all(class_="lesson"):
            title_el = item.find(class_="lesson-title")
            title = title_el.text if title_el else ""
            
            error_el = item.find(class_="lesson-error")
            error_msg = error_el.text if error_el else ""
            
            res_el = item.find(class_="lesson-resolution")
            resolution = res_el.text if res_el else ""
            
            lessons.append({
                "title": title.strip(),
                "error": error_msg.strip(),
                "resolution": resolution.replace("Lesson/Fix:", "").strip()
            })
    return lessons

def add_lesson(memory_dir: str, title: str, error_msg: str, resolution: str):
    path = os.path.join(memory_dir, "lessons.html")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Lessons file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    list_div = soup.find(id="lessons-list")
    if not list_div:
        return
        
    lesson_count = len(list_div.find_all(class_="lesson"))
    lesson_id = f"lesson-{lesson_count + 1}"
    lesson_div = soup.new_tag("div", attrs={"class": "lesson", "id": lesson_id})
    
    title_div = soup.new_tag("div", attrs={"class": "lesson-title"})
    title_div.string = title
    lesson_div.append(title_div)
    
    if error_msg:
        error_div = soup.new_tag("div", attrs={"class": "lesson-error"})
        error_div.string = error_msg
        lesson_div.append(error_div)
        
    res_div = soup.new_tag("div", attrs={"class": "lesson-resolution"})
    res_div.string = f"Lesson/Fix: {resolution}"
    lesson_div.append(res_div)
    
    date_div = soup.new_tag("div", attrs={"class": "lesson-date"})
    date_div.string = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lesson_div.append(date_div)
    
    list_div.append(lesson_div)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(soup))

def save_lessons(memory_dir: str, lessons: List[Dict[str, str]]):
    path = os.path.join(memory_dir, "lessons.html")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Lessons file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    list_div = soup.find(id="lessons-list")
    if not list_div:
        return
        
    # Clear existing lessons
    list_div.clear()
    
    # Append consolidated lessons
    for i, lesson in enumerate(lessons, 1):
        lesson_id = f"lesson-{i}"
        lesson_div = soup.new_tag("div", attrs={"class": "lesson", "id": lesson_id})
        
        title_div = soup.new_tag("div", attrs={"class": "lesson-title"})
        title_div.string = lesson["title"]
        lesson_div.append(title_div)
        
        if lesson.get("error"):
            error_div = soup.new_tag("div", attrs={"class": "lesson-error"})
            error_div.string = lesson["error"]
            lesson_div.append(error_div)
            
        res_div = soup.new_tag("div", attrs={"class": "lesson-resolution"})
        res_div.string = f"Lesson/Fix: {lesson['resolution']}"
        lesson_div.append(res_div)
        
        date_div = soup.new_tag("div", attrs={"class": "lesson-date"})
        date_div.string = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        lesson_div.append(date_div)
        
        list_div.append(lesson_div)
        
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(soup))

def add_task_history(memory_dir: str, task: str, status: str, details: str):
    path = os.path.join(memory_dir, "task_history.html")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Task history file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    list_div = soup.find(id="history-list")
    if not list_div:
        return
        
    card_div = soup.new_tag("div", attrs={"class": f"task-card {status.lower()}"})
    
    header = soup.new_tag("div", attrs={"class": "task-header"})
    title = soup.new_tag("div", attrs={"class": "task-title"})
    title.string = task
    header.append(title)
    
    status_span = soup.new_tag("span", attrs={"class": f"task-status status-{status.lower()}"})
    status_span.string = status
    header.append(status_span)
    card_div.append(header)
    
    details_div = soup.new_tag("div", attrs={"class": "task-details"})
    details_div.string = details
    card_div.append(details_div)
    
    meta = soup.new_tag("div", attrs={"class": "task-meta"})
    meta.string = f"Executed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    card_div.append(meta)
    
    list_div.append(card_div)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(soup))
