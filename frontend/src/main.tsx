import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DataSetup } from "./views/DataSetup";
import { ModelComparison } from "./views/ModelComparison";
import { WarningReplay } from "./views/WarningReplay";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <DataSetup /> },
      { path: "comparison", element: <ModelComparison /> },
      { path: "replay", element: <WarningReplay /> },
    ],
  },
]);

const root = document.getElementById("root");
if (!root) throw new Error("no #root element");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
