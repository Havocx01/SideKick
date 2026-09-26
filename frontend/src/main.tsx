import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DataSetup } from "./views/DataSetup";
import { ModelComparison } from "./views/ModelComparison";
import { WarningReplay } from "./views/WarningReplay";
import { Start, NewExperiment, ExperimentHistory, ExperimentProgress } from "./views/Experiments";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Start /> },
      { path: "benchmark", element: <DataSetup /> },
      { path: "new", element: <NewExperiment /> },
      { path: "experiments", element: <ExperimentHistory /> },
      { path: "experiments/:experimentId", element: <ExperimentProgress /> },
      { path: "experiments/:experimentId/data", element: <DataSetup /> },
      { path: "experiments/:experimentId/comparison", element: <ModelComparison /> },
      { path: "experiments/:experimentId/replay", element: <WarningReplay /> },
      { path: "comparison", element: <ModelComparison /> },
      { path: "replay", element: <WarningReplay /> }
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
