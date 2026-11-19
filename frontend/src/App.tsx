import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AiAssistant } from "./pages/AiAssistant";
import { OperationsOverview } from "./pages/operations/Overview";
import { LiveIncidentMap } from "./pages/operations/LiveIncidentMap";
import { ReportsQueue } from "./pages/operations/ReportsQueue";
import { IncidentVerification } from "./pages/operations/IncidentVerification";
import { ResourceAllocation } from "./pages/operations/ResourceAllocation";
import { RoadClosures } from "./pages/operations/RoadClosures";
import { Timeline } from "./pages/operations/Timeline";
import { AnalyticsDashboard } from "./pages/operations/AnalyticsDashboard";
import { BriefingReview } from "./pages/operations/BriefingReview";
import { PlanningOverview } from "./pages/planning/Overview";
import { DistrictVulnerability } from "./pages/planning/DistrictVulnerability";
import { EncroachmentTrend } from "./pages/planning/EncroachmentTrend";
import { DrainPriority } from "./pages/planning/DrainPriority";
import { Exposure } from "./pages/planning/Exposure";
import { ScenarioSimulator } from "./pages/planning/ScenarioSimulator";
import { PluvialSimulator } from "./pages/planning/PluvialSimulator";
import { FloodView3D } from "./pages/planning/FloodView3D";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/operations" replace />} />

        <Route path="operations" element={<OperationsOverview />} />
        <Route path="operations/live-map" element={<LiveIncidentMap />} />
        <Route path="operations/reports-queue" element={<ReportsQueue />} />
        <Route path="operations/verification" element={<IncidentVerification />} />
        <Route path="operations/resource-allocation" element={<ResourceAllocation />} />
        <Route path="operations/road-closures" element={<RoadClosures />} />
        <Route path="operations/timeline" element={<Timeline />} />
        <Route path="operations/analytics" element={<AnalyticsDashboard />} />
        <Route path="operations/briefing-review" element={<BriefingReview />} />

        <Route path="planning" element={<PlanningOverview />} />
        <Route path="planning/vulnerability" element={<DistrictVulnerability />} />
        <Route path="planning/encroachment-trend" element={<EncroachmentTrend />} />
        <Route path="planning/drain-priority" element={<DrainPriority />} />
        <Route path="planning/exposure" element={<Exposure />} />
        <Route path="planning/scenario-simulator" element={<ScenarioSimulator />} />
        <Route path="planning/pluvial-simulator" element={<PluvialSimulator />} />
        <Route path="planning/flood-3d" element={<FloodView3D />} />

        <Route path="ai-assistant" element={<AiAssistant />} />

        <Route path="*" element={<Navigate to="/operations" replace />} />
      </Route>
    </Routes>
  );
}
