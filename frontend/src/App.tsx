import { Routes, Route, Navigate } from "react-router-dom";
import { useWebSocket } from "./hooks/useWebSocket";
import Sidebar from "./components/Sidebar";
import MobileTopbar from "./components/MobileTopbar";
import HomeView from "./components/HomeView";
import PipelineView from "./components/PipelineView";
import TaskView from "./components/TaskView";
import NewTaskModal from "./components/modals/NewTaskModal";
import SystemPromptModal from "./components/modals/SystemPromptModal";
import LessonsModal from "./components/modals/LessonsModal";
import FinishTaskModal from "./components/modals/FinishTaskModal";

export default function App() {
  useWebSocket();

  return (
    <div>
      <Sidebar />
      <div className="main-workspace">
        <MobileTopbar />
        <Routes>
          <Route path="/" element={<Navigate to="/pipeline" replace />} />
          <Route path="/pipeline" element={<PipelineView />} />
          <Route path="/task" element={<HomeView />} />
          <Route path="/task/:id" element={<TaskView />} />
        </Routes>
      </div>
      <NewTaskModal />
      <SystemPromptModal />
      <LessonsModal />
      <FinishTaskModal />
    </div>
  );
}
