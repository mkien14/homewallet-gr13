import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import React from "react";
import ReactDOM from "react-dom";
import { renderToStaticMarkup } from "react-dom/server";

const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));

test("React and its renderer have exactly the same declared, locked and installed versions", () => {
  assert.equal(manifest.dependencies.react, manifest.dependencies["react-dom"]);
  assert.equal(lock.packages[""].dependencies.react, manifest.dependencies.react);
  assert.equal(lock.packages[""].dependencies["react-dom"], manifest.dependencies["react-dom"]);
  assert.equal(lock.packages["node_modules/react"].version, lock.packages["node_modules/react-dom"].version);
  assert.equal(React.version, ReactDOM.version);
  assert.equal(React.version, lock.packages["node_modules/react"].version);
});

test("the installed React renderer can render a component using hooks", () => {
  function Example() {
    const [label] = React.useState("HomeWallet · Bảo mật tài khoản");
    return React.createElement("p", null, label);
  }
  assert.equal(renderToStaticMarkup(React.createElement(Example)), "<p>HomeWallet · Bảo mật tài khoản</p>");
});
