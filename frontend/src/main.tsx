import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Start, NewExperiment, ExperimentHistory, ExperimentProgress } from "./views/Experiments";
import "@fontsource-variable/geist";
import "@fontsource-variable/inter";
import "@/registry/foundation.css";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Start /> },
      { path: "benchmark", lazy: async () => ({ Component: (await import("./views/DataSetup")).DataSetup }) },
      { path: "new", element: <NewExperiment /> },
      { path: "experiments", element: <ExperimentHistory /> },
      { path: "experiments/:experimentId", element: <ExperimentProgress /> },
      { path: "experiments/:experimentId/data", lazy: async () => ({ Component: (await import("./views/DataSetup")).DataSetup }) },
      { path: "experiments/:experimentId/comparison", lazy: async () => ({ Component: (await import("./views/ModelComparison")).ModelComparison }) },
      { path: "experiments/:experimentId/replay", lazy: async () => ({ Component: (await import("./views/WarningReplay")).WarningReplay }) },
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
