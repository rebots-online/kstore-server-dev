import React from "react";
import { createRoot } from "react-dom/client";
import ThinkSpace from "./ThinkSpace";
import "quill/dist/quill.snow.css";
import "highlight.js/styles/github-dark.css";
import "./rich.css";

createRoot(document.getElementById("root")!).render(<ThinkSpace />);
