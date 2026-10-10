import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Start } from "./views/Overview";
import "./fonts.css";
import "@/registry/foundation.css";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    hydrateFallbackElement: <div className="state" role="status">Loading workspace...</div>,
    children: [
      { index: true, element: <Start /> },
      { path: "walkthrough", element: <Start /> },
      { path: "benchmark", lazy: async () => ({ Component: (await import("./views/DataSetup")).DataSetup }) },
      { path: "new", lazy: async () => ({ Component: (await import("./views/Experiments")).NewExperiment }) },
      { path: "experiments", lazy: async () => ({ Component: (await import("./views/Experiments")).ExperimentHistory }) },
      { path: "experiments/:experimentId", lazy: async () => ({ Component: (await import("./views/Experiments")).ExperimentProgress }) },
      { path: "experiments/:experimentId/data", lazy: async () => ({ Component: (await import("./views/DataSetup")).DataSetup }) },
      { path: "experiments/:experimentId/comparison", lazy: async () => ({ Component: (await import("./views/ModelComparison")).ModelComparison }) },
      { path: "experiments/:experimentId/replay", lazy: async () => ({ Component: (await import("./views/WarningReplay")).WarningReplay }) },
      { path: "experiments/:experimentId/pilot", lazy: async () => ({ Component: (await import("./views/PilotReview")).PilotReview }) },
      { path: "comparison", lazy: async () => ({ Component: (await import("./views/ModelComparison")).ModelComparison }) },
      { path: "replay", lazy: async () => ({ Component: (await import("./views/WarningReplay")).WarningReplay }) }
    ]
  }
]);

const root = document.getElementById("root");
if (!root) throw new Error("no #root element");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
